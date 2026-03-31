"""A DSL for NITF file specification.

## Overview

The NITF format is a flat list of values. The values are fixed-width, the
structure of the NITF file is implicit in the values, the structure is defined
in the NITF spec, and varies wildly.

One level of abstraction up, we can think of NITF files as a flat list of
key/value pairs ("fields") where the keys are implicit: they are defined in the
specs, but not present in the file.

In Python, we want to use composite data structures, such as vector or record
types, where it makes sense. But, we also want our Python ADTs and our
specifications to have different structures from each other, and of course from
the flat NITF format.

The classes in this modules comprise a domain-specific language (DSL) which
enables bidirectional conversion from NITF's flat structure to richer Python
types.


## The AST

The `Spec` classes are nodes in an abstract syntax tree, where `FieldSpec`
instances are leaves of the tree and `RuleSpec` instances are internal nodes.
The root of the tree will typically be a `DataclassRecord` or a `DictRecord`,
which gather the tree into a dataclass or dict, respectively.


## The Context Stack (`push_scope` / `pop_scope`)

NITF files can have complex logic and fields whose existence or interpretation
depends on earlier fields. To support this, the AST evaluation during parsing
or generation is not "pure;" it passes a shared `Context` between nodes. The
`Context` acts as a stacked symbol table:

- Flat Evaluation: By default, child specs read and write to the same scope as
  their parents.

- Nested Evaluation: Complex record types, `DictRecord` or `DataclassRecord`,
  call `push_scope()` before evaluating their children to isolate the
  children's variables. Once finished, they package those variables as a dict
  or Dataclass value, call `pop_scope()` to clear the child variables, then
  return the value.

- Hiearchical lookup: as you would expect, if a symbol isn't present in the
  current scope, the lookup will proceed to the containing scope, etc.


## Names and structure (`name`)

Every `Spec` has a `name` field. The name dictates *binding*, determining the
routing between Python objects, DSL nodes, and NITF fields. Anonymous specs
(with empty names) behave differently than named specs.

### Named Specs (`name != ""`)

- Parsing: The spec reads binary data, converts it to a Python value, injects
  the value into the current scope, AND returns it.

- Emitting: The parent node uses the child's name to extract specific data from
  the Python object (via a dictionary key or dataclass attribute) to pass down
  to the child for serialization:

        child_val = parent_dict.get(child_spec.name)

### Anonymous Specs (`name == ""`)

- Parsing: The spec reads binary data and returns the Python value, but does
  NOT save it to the context. The value is still returned, where it can be,
  e.g., gathered by the parent node into a list.

- Emitting: The parent node does not try to extract a sub-field. Instead, it
  passes its entire data context straight through to the anonymous child.

- Note that anonymous leaves only make sense as children of nodes like `Vector`
  which explicitly distribute values to their children. Otherwise, during
  serialization they are passed the entire context instead of a scalar value,
  and crash.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import ChainMap
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import KW_ONLY, dataclass, field, fields
from dataclasses import Field as DataclassField
from datetime import UTC, date, datetime, timezone
from decimal import Decimal
from enum import IntEnum, StrEnum
from typing import (
    Any,
    BinaryIO,
    ClassVar,
    Literal,
    Protocol,
    TypeGuard,
    cast,
    final,
    override,
)
from uuid import UUID

from nitful.core.errors import ParseError, SerializeError

from .validator import Validator


@dataclass
class Field:
    """A name and serializable value for a NITF field."""

    name: str
    value: bytes | StreamablePayload


def field_size(fields: list[Field]) -> int:
    """Get the serialized size of a list of Fields."""
    return sum(len(f.value) for f in fields)


class StreamablePayload(Protocol):
    """Generic interface for streamable byte data.

    For image data (pixels), this allows the data to be ignored or lazily
    read/copied as needed.
    """

    def __len__(self) -> int: ...
    def write(self, out_fd: BinaryIO) -> None: ...
    def read(self) -> bytes: ...


class Context:
    """A scoped evaluation context.

    This functions like a symbol table. Most fields just add their own value to
    the context, but some, e.g., use previous values to modify behavior.
    """

    is_parsing: ClassVar[bool] = False
    is_emitting: ClassVar[bool] = False

    def __init__(self, init: dict[str, Any] | None = None) -> None:
        # Stacked namespaces for evaluation contexts.
        self._contexts: ChainMap[str, Any] = ChainMap(init or {})

        # Stacked indices for tracking position inside lists.
        self._indices: list[int] = []

    def __getitem__(self, key: str) -> Any:
        return self._contexts[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._contexts[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._contexts

    def get(self, key: str, default: Any = None) -> Any:
        return self._contexts.get(key, default)

    def push_scope(self, init: dict[str, Any] | None = None) -> None:
        """Enter a new scope by pushing a dict to the front."""
        self._contexts.maps.insert(0, init or {})

    def pop_scope(self) -> dict[str, Any]:
        """Exit the current scope and return its exclusively local values."""
        if len(self._contexts.maps) <= 1:
            msg = "Cannot pop the root scope."
            raise RuntimeError(msg)

        return cast(dict[str, Any], self._contexts.maps.pop(0))

    @property
    def local_scope(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._contexts.maps[0])

    def iterate[V](self, iterable: Iterable[V]) -> Iterator[V]:
        """Iterate over a sequence while tracking the index for error paths.

        Using this instead of a standard loop allows the context to track
        repeated child specs, so that `ctx.subscripts` can accurately show
        indices like `[0][2]` during exceptions.
        """
        self._indices.append(0)

        try:
            for i, val in enumerate(iterable):
                self._indices[-1] = i
                yield val
        finally:
            self._indices.pop()

    @property
    def subscripts(self) -> str:
        if not self._indices:
            return ""

        return "".join(f"[{i}]" for i in self._indices)


class ParseContext(Context):
    """Context while reading binary data into Python objects.

    State is accumulated sequentially. Variables become available in the
    context only *after* their corresponding binary fields have been parsed.
    """

    is_parsing: ClassVar[bool] = True


class EmitContext(Context):
    """Context while serializing Python objects into binary fields.

    State is populated preemptively. Structural nodes push the attributes of
    the Python object into the context *before* evaluating their child specs.
    """

    is_emitting: ClassVar[bool] = True


@dataclass
class Spec[T](ABC):
    """A specification for NITF data.

    Instances of this class describe how to read binary data into Python
    objects, and how to serialize Python objects back into binary `Field`
    objects. They generate `Field` objects rather than writing binary output
    because it's useful to manipulate the fields before output.

    Child classes only need to define:

        - `_read` to produce a value from a bytestream
        - `_emit` to produce a number of `Field` objects from a value,

    Those methods shouldn't be called directly; `parse` and `to_fields` are
    their public equivalents, which handle context management and errors.
    """

    # See the module docstring for a discussion of how names are used.
    name: str

    @final
    def parse(self, fd: BinaryIO, ctx: ParseContext) -> T:
        start_offset = fd.tell()
        trace_name = self.display_name() + ctx.subscripts

        try:
            val = self._read(fd, ctx)
            if self.name:
                ctx[self.name] = val
        except ParseError as e:
            e.path.insert(0, trace_name)
            raise ParseError(e.base_msg, e.path, e.offset) from e.__cause__
        except Exception as e:
            raise ParseError(str(e), [trace_name], start_offset) from e
        else:
            return val

    @final
    def to_fields(self, value: T, ctx: EmitContext) -> list[Field]:
        trace_name = self.display_name() + ctx.subscripts

        try:
            return self._emit(value, ctx=ctx)
        except SerializeError as e:
            e.path.insert(0, trace_name)
            raise SerializeError(e.base_msg, e.path) from e.__cause__
        except Exception as e:
            raise SerializeError(str(e), [trace_name]) from e

    def display_name(self) -> str:
        """Used only for displaying the name in errors."""

        # Start with the DSL name of the AST node.
        cname = self.__class__.__name__

        # Decorate the name with the wrapped spec or implemented class. This
        # relies on the convention of using common names for these values.
        spec = getattr(self, "spec", None)
        body = getattr(self, "body", None)
        mcls = getattr(self, "model_cls", None)
        mname = f"({mcls.__name__})" if mcls else ""
        sname = f"({spec.name})" if spec and hasattr(spec, "name") and spec.name else ""
        bname = f"({body.name})" if body and hasattr(body, "name") and body.name else ""

        # Prefix with the assigned name, if this spec isn't anonymous.
        aname = f"{self.name}:" if self.name else ""

        return f"{aname}{cname}{mname}{sname}{bname}"

    @abstractmethod
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T: ...

    @abstractmethod
    def _emit(self, value: T, *, ctx: EmitContext) -> list[Field]: ...


@dataclass
class FieldSpec[T](Spec[T], ABC):
    """A specification for a single NITF field.

    These are the "leaves" of our syntax tree: they are responsible for actual
    reading and writing of binary data. They are usually a single scalar data
    element.

    They have an optional `validate` field to check if a value is allowed in
    the NITF spec before writing.
    """

    # The specified size in bytes of the field according to the NITF spec.
    size: int

    # An optional validation step before serialization.
    validate: Validator[T] | None = None

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T:
        b = fd.read(self.size)
        return self.decode(b)

    @override
    def _emit(self, value: T, *, ctx: EmitContext) -> list[Field]:
        if self.validate and not self.validate(value):
            msg = f"Invalid value {value} for '{self.name}'"
            raise RuntimeError(msg)

        encoded = self.encode(value)
        if len(encoded) != self.size:
            msg = (
                f"Encoding error in '{self.name}': Expected {self.size} bytes, "
                f"but got {len(encoded)} bytes (Payload: {encoded!r})"
            )
            raise RuntimeError(msg)

        full_name = self.name + ctx.subscripts
        return [Field(full_name, encoded)]

    @abstractmethod
    def encode(self, decoded: T) -> bytes:
        pass

    @abstractmethod
    def decode(self, encoded: bytes) -> T:
        pass


@dataclass
class RuleSpec[T](Spec[T], ABC):
    """A specification for one or more NITF fields.

    These are the "branches" of our syntax tree. They structure the FieldSpec
    nodes. RuleSpec nodes are anonymous by default; see the description in the
    module docstring above.
    """

    name: str = field(default="", kw_only=True)


@dataclass
class Nothing(FieldSpec[None]):

    name: str = ""
    size: int = 0

    @override
    def encode(self, decoded: None) -> bytes:
        return b""

    @override
    def decode(self, encoded: bytes) -> None:
        return None


@dataclass
class Marker(FieldSpec[None]):
    """A no-op added to the spec for later processing."""

    size: int = 0

    @override
    def encode(self, decoded: None) -> bytes:
        return b""

    @override
    def decode(self, encoded: bytes) -> None:
        return None


@dataclass
class Bool(FieldSpec[bool]):

    _: KW_ONLY

    false: bytes = b"0"
    true: bytes = b"1"
    size: int = field(default=1, kw_only=True)

    @override
    def encode(self, decoded: bool) -> bytes:
        return self.true if decoded else self.false

    @override
    def decode(self, encoded: bytes) -> bool:
        if encoded == self.false:
            return False
        if encoded == self.true:
            return True
        msg = (
            f"Decoding error: expected {self.false!r} or {self.true!r}, "
            f"read {encoded!r}"
        )
        raise RuntimeError(msg)


@dataclass
class Int(FieldSpec[int]):

    # Always show the sign, positive or negative.
    sign: bool = False

    @override
    def encode(self, decoded: int) -> bytes:
        plus = "+" if self.sign else ""
        return f"{decoded:{plus}0{self.size}d}".encode()

    @override
    def decode(self, encoded: bytes) -> int:
        return int(encoded.decode())


@dataclass
class BcsString(FieldSpec[str]):
    """A string with the BCS character set."""

    @override
    def encode(self, decoded: str) -> bytes:
        return format(decoded, f"<{self.size}s").encode("ascii")

    @override
    def decode(self, encoded: bytes) -> str:
        return encoded.decode("ascii").rstrip()


@dataclass
class EcsString(FieldSpec[str]):
    """A string with the ECS character set."""

    @override
    def encode(self, decoded: str) -> bytes:
        return format(decoded, f"<{self.size}s").encode("latin_1")

    @override
    def decode(self, encoded: bytes) -> str:
        return encoded.decode("latin_1").rstrip()


@dataclass
class BcsIntEnum[T: IntEnum](FieldSpec[T]):
    """An integer enumeration in the NITF spec.

    The `enum` argument is a Python `IntEnum` that defines the valid integers
    and their meanings.
    """

    _: KW_ONLY

    enum: type[T]

    @override
    def encode(self, decoded: T) -> bytes:
        return format(decoded.value, f"0{self.size}d").encode("ascii")

    @override
    def decode(self, encoded: bytes) -> T:
        return self.enum(int(encoded.decode("ascii")))


@dataclass
class EcsStringEnum[T: StrEnum](FieldSpec[T]):
    """A string enumeration with ECS characters in the NITF spec.

    The `enum` argument is a Python `StrEnum` that defines the valid strings
    and their meanings.
    """

    _: KW_ONLY

    enum: type[T]

    @override
    def encode(self, decoded: T) -> bytes:
        return format(decoded.value, f"<{self.size}s").encode("latin_1")

    @override
    def decode(self, encoded: bytes) -> T:
        return self.enum(encoded.decode("latin_1"))


@dataclass
class BcsStringEnum[T: StrEnum](FieldSpec[T]):
    """A string enumeration with BCS characters in the NITF spec.

    The `enum` argument is a Python `StrEnum` that defines the valid strings
    and their meanings.
    """

    _: KW_ONLY

    enum: type[T]

    @override
    def encode(self, decoded: T) -> bytes:
        return format(decoded.value, f"<{self.size}s").encode("ascii")

    @override
    def decode(self, encoded: bytes) -> T:
        return self.enum(encoded.decode("ascii"))


@dataclass
class Fixed(FieldSpec[float]):
    """A fixed-point number: 'nn.ddddd'."""

    _: KW_ONLY

    # Always show the sign for positive or negative numbers.
    sign: bool = False

    # The number of digits after the decimal point.
    ndigits: int = 2

    @override
    def encode(self, decoded: float) -> bytes:
        plus = "+" if self.sign else ""
        format_str = f"{plus}0{self.size}.{self.ndigits}f"
        return format(decoded, format_str).encode()

    @override
    def decode(self, encoded: bytes) -> float:
        return float(encoded.decode().strip())


@dataclass
class FixedDecimal(FieldSpec[Decimal]):
    """A fixed-point number return as a Decimal to maintain precision."""

    _: KW_ONLY

    # Always show the sign for positive or negative numbers.
    sign: bool = False

    # The number of digits after the decimal point.
    ndigits: int = 2

    @override
    def encode(self, decoded: Decimal) -> bytes:
        plus = "+" if self.sign else ""
        format_str = f"{plus}0{self.size}.{self.ndigits}f"
        return format(decoded, format_str).encode()

    @override
    def decode(self, encoded: bytes) -> Decimal:
        return Decimal(encoded.decode().strip())


@dataclass
class BcsFloat(FieldSpec[float]):
    """A floating-point number in scientific notation: ±i.nnnnnnE±ee

    Where the number of digits after the decimal point (n) is derived from the
    total width and number of exponent digits (e).
    """

    _: KW_ONLY

    edigits: int

    @property
    def precision(self) -> int:
        prec = self.size - self.edigits - len("±i.E±")

        if prec < 0:
            msg = f"Size {self.size} is too small for {self.edigits} exp digits."
            raise ValueError(msg)

        return prec

    @override
    def encode(self, decoded: float) -> bytes:
        raw = format(decoded, f"+.{self.precision}E")
        mantissa, exponent = raw.split("E")
        exp_val = int(exponent)

        max_exp = (10**self.edigits) - 1
        min_exp = -max_exp

        if exp_val > max_exp:
            msg = (
                f"Float exponent {exp_val} exceeds maximum allowed "
                f"for {self.edigits} digits ({max_exp})."
            )
            raise ValueError(msg)

        if exp_val < min_exp:
            msign = mantissa[0]
            zero_frac = "0" * self.precision
            zero_exp = "0" * self.edigits
            retval = f"{msign}0.{zero_frac}E+{zero_exp}"
        else:
            exp = format(exp_val, f"+0{self.edigits + 1}d")
            retval = f"{mantissa}E{exp}"

        return retval.encode("ascii")

    @override
    def decode(self, encoded: bytes) -> float:
        return float(encoded.decode("ascii"))


@dataclass
class HexColor(FieldSpec[tuple[int, int, int]]):

    size: int = field(default=3, init=False)

    @override
    def encode(self, decoded: tuple[int, int, int]) -> bytes:
        return bytes(decoded)

    @override
    def decode(self, encoded: bytes) -> tuple[int, int, int]:
        if len(encoded) != self.size:
            raise RuntimeError

        return encoded[0], encoded[1], encoded[2]


@dataclass
class IsoDate(FieldSpec[date]):
    """A date formatted CCYYMMDD"""

    size: int = field(default=8, init=False)
    format: str = field(default="%Y%m%d", init=False)

    @override
    def encode(self, decoded: date) -> bytes:
        return format(decoded, self.format).encode()

    @override
    def decode(self, encoded: bytes) -> date:
        return date.fromisoformat(encoded.decode())


@dataclass
class HMSeconds(FieldSpec[float]):
    """Seconds formatted hhmmss.nnnnnnnnn

    NOTE:
    - "123456.000000000" is not 123456 seconds, but 12 hours, 34 minutes, and
      56 seconds!
    - Python's datetime.timedelta does not have sufficient resolution to
      represent this number.
    """

    size: int = field(default=16, init=False)

    @override
    def encode(self, decoded: float) -> bytes:
        h = int(decoded // 3600)
        m = int((decoded % 3600) // 60)
        s = decoded % 60
        s_width = self.size - 4
        ndigits = s_width - 3
        return f"{h:02d}{m:02d}{s:0{s_width}.{ndigits}f}".encode("ascii")

    @override
    def decode(self, encoded: bytes) -> float:
        h = int(encoded[:2].decode())
        m = int(encoded[2:4].decode())
        s = float(encoded[4:].decode())
        return h * 3600 + m * 60 + s


@dataclass
class ConcatDatetime(FieldSpec[datetime]):
    """A date and time formatted CCYYMMDDhhmmss"""

    size: int = field(default=14, init=False)
    format: str = field(default="%Y%m%d%H%M%S", init=False)

    _: KW_ONLY

    tz: timezone = UTC

    @override
    def encode(self, decoded: datetime) -> bytes:
        return decoded.strftime(self.format).encode()

    @override
    def decode(self, encoded: bytes) -> datetime:
        return datetime.strptime(encoded.decode(), self.format).replace(tzinfo=self.tz)


@dataclass
class Uuid(FieldSpec[UUID]):
    """UUID in canonical form."""

    size: int = field(default=36, init=False)

    @override
    def encode(self, decoded: UUID) -> bytes:
        return str(decoded).encode()

    @override
    def decode(self, encoded: bytes) -> UUID:
        return UUID(encoded.decode())


@dataclass
class BinaryInt(FieldSpec[int]):
    """An integer represented in binary instead of ASCII."""

    _: KW_ONLY

    order: Literal["big", "little"] = "big"

    @override
    def encode(self, decoded: int) -> bytes:
        return decoded.to_bytes(self.size, byteorder=self.order)

    @override
    def decode(self, encoded: bytes) -> int:
        return int.from_bytes(encoded, byteorder=self.order)


@dataclass
class Constant[T](RuleSpec[T]):
    """A wrapper that both supplies and expects a specific value."""

    spec: FieldSpec[T]
    value: T
    name: str = field(default="", init=False)

    def __post_init__(self) -> None:
        # Get the inner spec's name in order to route it the correct value.
        self.name = self.spec.name

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T:
        parsed = self.spec.parse(fd, ctx)
        if parsed != self.value:
            msg = (
                f"Constant mismatch for '{self.spec.name}': "
                f"expected {self.value!r}, got {parsed!r}"
            )
            raise ValueError(msg)
        return self.value

    @override
    def _emit(self, value: T | None = None, *, ctx: EmitContext) -> list[Field]:
        if value is not None and value != self.value:
            msg = f"Cannot override constant '{self.spec.name}' with {value!r}."
            raise ValueError(msg)

        return self.spec.to_fields(self.value, ctx)


@dataclass
class Override[T, V](RuleSpec[T | V]):
    """Override specific byte patterns with a given value."""

    spec: FieldSpec[T]
    mapping: dict[bytes, V]
    name: str = field(default="", init=False)

    def __post_init__(self) -> None:
        # Get the inner spec's name in order to route it the correct value.
        self.name = self.spec.name

        for o_bytes in self.mapping:
            if len(o_bytes) != self.spec.size:
                msg = f"Override {o_bytes!r} is wrong size"
                raise ValueError(msg)

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T | V:
        start_pos = fd.tell()
        b = fd.read(self.spec.size)

        if b in self.mapping:
            return self.mapping[b]

        fd.seek(start_pos)

        # No overrides matched, use the default spec.
        return self.spec.parse(fd, ctx)

    @override
    def _emit(self, value: T | V, *, ctx: EmitContext) -> list[Field]:
        for o_bytes, o_value in self.mapping.items():
            if value == o_value:
                return [Field(self.spec.name + ctx.subscripts, o_bytes)]

        # No overrides matched, use the default spec.
        return self.spec.to_fields(cast(T, value), ctx)


@dataclass
class Blankable[T](Override[T, None]):
    """All spaces in a FieldSpec return None."""

    def __init__(self, spec: FieldSpec[T]) -> None:
        blank_bytes = b" " * spec.size
        super().__init__(spec, {blank_bytes: None})


@dataclass
class Computed[T](RuleSpec[T]):
    """A spec that derives its value from the context during emit."""

    spec: Spec[T]
    getter: Callable[[Context], T]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T:
        return self.spec.parse(fd, ctx)

    @override
    def _emit(self, value: Any, *, ctx: EmitContext) -> list[Field]:
        computed_val = self.getter(ctx)
        return self.spec.to_fields(computed_val, ctx)


@dataclass
class Vector[T](RuleSpec[list[T]]):
    """A list of specs translated to/from a list of values."""

    specs: Sequence[Spec[T]]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> list[T]:
        return [spec.parse(fd, ctx) for spec in self.specs]

    @override
    def _emit(self, value: list[T], *, ctx: EmitContext) -> list[Field]:
        fields: list[Field] = []

        for spec, v in zip(self.specs, value, strict=True):
            fields.extend(spec.to_fields(v, ctx))

        return fields


@dataclass
class VarString(RuleSpec[str]):
    """A string prefixed by a length field."""

    len_spec: FieldSpec[int]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> str:
        length = self.len_spec.parse(fd, ctx)
        if length == 0:
            return ""
        return BcsString("", length).parse(fd, ctx)

    @override
    def _emit(self, value: str, *, ctx: EmitContext) -> list[Field]:
        if not value:
            return self.len_spec.to_fields(0, ctx)

        fields = self.len_spec.to_fields(len(value), ctx)
        fields.extend(BcsString("", len(value)).to_fields(value, ctx))
        return fields


@dataclass
class SizedList[T](RuleSpec[list[T]]):
    """Repeat a body spec `count` times.

    The count is supplied as an argument or extracted from the context.
    """

    count: int | Callable[[Context], int]
    body: Spec[T]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> list[T]:
        count = self.count(ctx) if callable(self.count) else self.count
        return [self.body.parse(fd, ctx) for _ in ctx.iterate(range(count))]

    @override
    def _emit(self, value: list[T], *, ctx: EmitContext) -> list[Field]:
        count = self.count(ctx) if callable(self.count) else self.count

        if len(value) != count:
            msg = f"Expected {count} items, got {len(value)}"
            raise RuntimeError(msg)

        fields: list[Field] = []
        for v in ctx.iterate(value):
            fields.extend(self.body.to_fields(v, ctx))

        return fields


@dataclass
class PrefixedList[T](RuleSpec[list[T]]):
    """Repeat a spec based on an initial field with a count."""

    count: Spec[int]
    body: Spec[T]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> list[T]:
        n = self.count.parse(fd, ctx)
        return [self.body.parse(fd, ctx) for _ in ctx.iterate(range(n))]

    @override
    def _emit(self, value: list[T], *, ctx: EmitContext) -> list[Field]:
        fields = self.count.to_fields(len(value), ctx)
        for v in ctx.iterate(value):
            fields.extend(self.body.to_fields(v, ctx))

        return fields


@dataclass
class PrefixedArray[T](RuleSpec[list[list[T]]]):
    """A 2D array of specs prefixed by row and column counts."""

    rows_spec: Spec[int]
    cols_spec: Spec[int]
    body: Spec[T]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> list[list[T]]:
        rows = self.rows_spec.parse(fd, ctx)
        cols = self.cols_spec.parse(fd, ctx)

        return [
            [self.body.parse(fd, ctx) for _ in ctx.iterate(range(cols))]
            for _ in ctx.iterate(range(rows))
        ]

    @override
    def _emit(self, value: list[list[T]], *, ctx: EmitContext) -> list[Field]:
        rows = len(value)
        cols = len(value[0]) if rows > 0 else 0

        for row in value:
            if len(row) != cols:
                msg = f"Jagged arrays are not supported in '{self.name}'."
                raise ValueError(msg)

        fields = self.rows_spec.to_fields(rows, ctx)
        fields.extend(self.cols_spec.to_fields(cols, ctx))

        for row in ctx.iterate(value):
            for item in ctx.iterate(row):
                fields.extend(self.body.to_fields(item, ctx))

        return fields


@dataclass
class Optional[T](RuleSpec[T | None]):
    """A boolean determines if the following body should exist."""

    condition: Spec[bool]
    body: Spec[T]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T | None:
        if not self.condition.parse(fd, ctx):
            return None

        return self.body.parse(fd, ctx)

    @override
    def _emit(self, value: T | None, *, ctx: EmitContext) -> list[Field]:
        if value is None:
            return self.condition.to_fields(False, ctx)

        return [*self.condition.to_fields(True, ctx), *self.body.to_fields(value, ctx)]


@dataclass
class Conditional[T](RuleSpec[T | None]):
    """Determine if the body should exist based on context."""

    condition: Callable[[Context], bool]
    body: Spec[T]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T | None:
        if self.condition(ctx):
            return self.body.parse(fd, ctx)
        return None

    @override
    def _emit(self, value: T | None, *, ctx: EmitContext) -> list[Field]:
        if not self.condition(ctx):
            return []

        if value is None:
            msg = f"{self.display_name()} is True, but no value was provided."
            raise ValueError(msg)

        return self.body.to_fields(value, ctx)


class DataclassProtocol(Protocol):
    """A type protocol to identify dataclass instances/types."""

    __dataclass_fields__: ClassVar[dict[str, DataclassField[Any]]]


@dataclass
class DataclassRecord[T: DataclassProtocol](RuleSpec[T]):
    """Unpacks specs into a dataclass based on their names."""

    model_cls: type[T]
    specs: Sequence[Spec[Any]]

    def __post_init__(self) -> None:
        self.field_names: set[str] = {f.name for f in fields(self.model_cls)}

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T:
        ctx.push_scope()

        for spec in self.specs:
            spec.parse(fd, ctx)

        local_kwargs = ctx.pop_scope()
        valid_keys = local_kwargs.keys() & self.field_names
        filtered_kwargs = {k: local_kwargs[k] for k in valid_keys}
        return self.model_cls(**filtered_kwargs)

    @override
    def _emit(self, value: T, *, ctx: EmitContext) -> list[Field]:
        val_dict = vars(value)
        ctx.push_scope(val_dict)

        out_fields: list[Field] = []
        for spec in self.specs:
            child_val = val_dict.get(spec.name) if spec.name else val_dict
            out_fields.extend(spec.to_fields(child_val, ctx))

        ctx.pop_scope()
        return out_fields

    def matches(self, value: object) -> TypeGuard[T]:
        """Check if a Python object belongs to this record's dataclass."""
        return isinstance(value, self.model_cls)


@dataclass
class VariantRecord[TagType, PayloadType](RuleSpec[PayloadType]):
    """A discriminated union of `DataclassRecord` specs.

    The leading field is a tag that determines the form of the following
    fields.
    """

    tag_spec: FieldSpec[TagType]
    cases: dict[TagType, DataclassRecord[Any]]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> PayloadType:
        tag = self.tag_spec.parse(fd, ctx)

        if tag not in self.cases:
            msg = f"Unrecognized tag {tag!r} in VariantRecord '{self.name}'"
            raise ValueError(msg)

        parser = self.cases[tag]
        return cast(PayloadType, parser.parse(fd, ctx))

    @override
    def _emit(self, value: PayloadType, *, ctx: EmitContext) -> list[Field]:
        tag_to_write = None

        for tag, spec in self.cases.items():
            if spec.matches(value):
                tag_to_write = tag

        if tag_to_write is None:
            cname = type(value).__name__
            msg = f"Unexpected class {cname} for VariantRecord '{self.name}'"
            raise TypeError(msg)

        spec_to_use = self.cases[tag_to_write]
        fields = self.tag_spec.to_fields(tag_to_write, ctx)
        fields.extend(spec_to_use.to_fields(value, ctx))

        return fields


@dataclass
class DictRecord(RuleSpec[dict[str, Any]]):
    """A spec that returns its child specs as a dict."""

    specs: Sequence[Spec[Any]]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> dict[str, Any]:
        ctx.push_scope()

        for spec in self.specs:
            spec.parse(fd, ctx)

        return ctx.pop_scope()

    @override
    def _emit(self, value: dict[str, Any], *, ctx: EmitContext) -> list[Field]:
        ctx.push_scope(value)

        out_fields: list[Field] = []
        for spec in self.specs:
            child_val = value.get(spec.name) if spec.name else value
            out_fields.extend(spec.to_fields(child_val, ctx))

        ctx.pop_scope()
        return out_fields


@dataclass
class SizedBlock(RuleSpec[dict[str, Any]]):
    """A spec with a leading field containing the size of the body.

    Unlike DictRecord or DataclassRecord, SizedBlock doesn't push a new scope:
    it's meant to be a transparent "measuring tape" for the body.
    """

    length_spec: Spec[int]
    body: Sequence[Spec[Any]]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> dict[str, Any]:
        expected_size = self.length_spec.parse(fd, ctx)
        start_pos = fd.tell()

        for spec in self.body:
            spec.parse(fd, ctx)

        bytes_read = fd.tell() - start_pos
        if bytes_read != expected_size:
            msg = f"Expected {expected_size} bytes, but read {bytes_read} bytes."
            raise RuntimeError(msg)

        return ctx.local_scope

    @override
    def _emit(self, value: dict[str, Any], *, ctx: EmitContext) -> list[Field]:
        body_fields: list[Field] = []

        for spec in self.body:
            child_val = value.get(spec.name) if spec.name else value
            body_fields.extend(spec.to_fields(child_val, ctx))

        body_len = sum(len(f.value) for f in body_fields)
        len_fields = self.length_spec.to_fields(body_len, ctx)
        return len_fields + body_fields


@dataclass
class Switch[TagType, PayloadType](RuleSpec[PayloadType]):
    """Branches parsing logic based on a previously evaluated context value."""

    get_tag: Callable[[ParseContext], TagType]
    cases: dict[TagType, Spec[PayloadType]]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> PayloadType:
        tag = self.get_tag(ctx)

        if tag not in self.cases:
            msg = f"Unrecognized tag {tag!r} for Switch '{self.name}'."
            raise ValueError(msg)

        return self.cases[tag].parse(fd, ctx)

    @override
    def _emit(self, value: PayloadType, *, ctx: EmitContext) -> list[Field]:
        tag_to_write = None

        for tag, spec in self.cases.items():
            matches = getattr(spec, "matches", None)
            if matches and matches(value):
                tag_to_write = tag
                break

        if tag_to_write is None or tag_to_write not in self.cases:
            msg = f"Cannot map payload {value!r} to a Switch branch in '{self.name}'."
            raise ValueError(msg)

        return self.cases[tag_to_write].to_fields(value, ctx)


@dataclass
class ReservedExtensions(RuleSpec[dict[str, Any]]):
    """A transparent block for dynamic Reserved Field Areas (e.g., CSCSDB).

    Reads the global reserved length, the mask length, the boolean mask,
    and then selectively reads the payload for each active area.
    Unrecognized areas are preserved as raw bytes to allow round-tripping.
    """

    size_spec: Spec[int]
    msize_spec: Spec[int]

    # Maps a **1-based** area index to a Spec. The Spec must have a non-empty
    # name; each name will be written with None or the Spec value.
    cases: dict[int, Spec[Any]]

    # Unknown Reserved Field Areas can be parsed as raw bytes and stored for
    # correct round-tripping. `unknown_name` will be the name for the unknown
    # fields, stored as a dict[int, bytes].
    unknown_name: str = "unknown_extensions"

    def __post_init__(self) -> None:
        for i, spec in self.cases.items():
            if not spec.name:
                msg = f"Area specs must have a 'name', but area {i} does not."
                raise ValueError(msg)

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> dict[str, Any]:
        total_len = self.size_spec.parse(fd, ctx)

        # Initialize all defined areas to None in the parent scope.
        for spec in self.cases.values():
            if spec.name:
                ctx[spec.name] = None

        # Initialize the unknown entries.
        ctx[self.unknown_name] = {}

        if total_len == 0:
            return ctx.local_scope

        mask_len = self.msize_spec.parse(fd, ctx)
        mask = BcsString("RESERVED_FIELD_MASK", mask_len).parse(fd, ctx)

        unknowns: dict[int, bytes] = {}

        for i in range(1, mask_len + 1):
            if mask[i - 1] == "0":
                continue

            if i not in self.cases:
                area_len = Int(f"RESERVED_LEN_AREA{i}", 9).parse(fd, ctx)
                unknowns[i] = fd.read(area_len)
                continue

            spec = self.cases[i]
            SizedBlock(Int(f"RESERVED_LEN_AREA{i}", 9), [spec]).parse(fd, ctx)

        ctx[self.unknown_name] = unknowns
        return ctx.local_scope

    @override
    def _emit(self, value: dict[str, Any], *, ctx: EmitContext) -> list[Field]:
        unknowns: dict[int, bytes] = value.get(self.unknown_name) or {}

        active_indices = set(unknowns.keys())
        for i, spec in self.cases.items():
            if spec.name and value.get(spec.name) is not None:
                active_indices.add(i)

        if not active_indices:
            return self.size_spec.to_fields(0, ctx)

        mask_len = max(active_indices)
        mask_chars: list[str] = []
        area_fields: list[Field] = []

        for i in range(1, mask_len + 1):
            if i not in active_indices:
                mask_chars.append("0")
                continue

            mask_chars.append("1")

            if i in unknowns:
                payload_bytes = unknowns[i]
                size = len(payload_bytes)
                alen_field = Int(f"RESERVED_LEN_AREA{i}", 9).to_fields(size, ctx=ctx)
                area_fields.extend(alen_field)
                area_fields.append(Field(f"RESERVED_AREA_{i}_DATA", payload_bytes))
            else:
                spec = self.cases[i]
                block = SizedBlock(Int(f"RESERVED_LEN_AREA{i}", 9), body=[spec])
                area_fields.extend(block.to_fields(value, ctx))

        mask_str = "".join(mask_chars)
        mlen_field = self.msize_spec.to_fields(mask_len, ctx)
        mask_field = BcsString("RESERVED_FIELD_MASK", mask_len).to_fields(mask_str, ctx)
        header_fields = [*mlen_field, *mask_field]

        total_len = field_size(header_fields) + field_size(area_fields)
        rfa_len_field = self.size_spec.to_fields(total_len, ctx)

        return [*rfa_len_field, *header_fields, *area_fields]


@dataclass
class SpecNotImplemented(Spec[None]):

    name: str = ""

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> None:
        raise NotImplementedError

    @override
    def _emit(self, value: None, *, ctx: EmitContext) -> list[Field]:
        raise NotImplementedError
