"""A DSL for NITF file specification.

## Overview

The classes in this modules comprise a domain-specific language (DSL) which
enables bidirectional conversion from NITF's flat structure to richer Python
types.

The NITF format is a flat list of values. The values are fixed-width, the
structure of the NITF file is implicit in the values, the structure is defined
in the NITF spec, and varies wildly.

One level of abstraction up, we can think of NITF files as a flat list of
key/value pairs ("fields") where the keys are implicit: they are defined in the
specs, but not present in the file.

In Python, we use types like lists or dataclases where it makes sense. We want
both those types and the DSL to have useful structure that can differ from one
another, and of course from the flat NITF format.


## The AST

The `Rule` classes are nodes in an abstract syntax tree, where `Field`
instances are leaves of the tree and `Combinator` instances are internal nodes.
The root of the tree will typically be a `Struct` or a `Group`, which gather
the tree into a dataclass or dict, respectively.


## The Context Stack (`push_scope` / `pop_scope`)

NITF files can have complex logic and fields whose existence or interpretation
depends on earlier fields. To support this, the AST evaluation passes a shared
`Context` between nodes. The `Context` acts as a stacked symbol table:

- Flat Evaluation: By default, child rules read and write to the same scope as
  their parents.

- Nested Evaluation: Complex record types, `Struct` or `Group`, call
  `push_scope()` before evaluating their children to isolate the children's
  variables. Once finished, they package those variables as a dict or Dataclass
  value, call `pop_scope()` to clear the child variables, then return the
  value.

- Hiearchical lookup: as you would expect, if a symbol isn't present in the
  current scope, the lookup will proceed to the containing scope, etc.

In addition to the symbol table, the Context bundles various other impure
side-effects during evaluation: the path from the AST root to the current node,
as a history of reads/writes used for error reporting, and byte offset during
parsing.


## Names and structure (`name`)

Every `Rule` has a `name` field. The name dictates *binding*, determining the
routing between Python objects, DSL nodes, and NITF fields. Anonymous rules
(with empty names) behave differently than named rules.

### Named Rules (`name != ""`)

- Parsing: The rule reads binary data, converts it to a Python value, injects
  the value into the current scope, AND returns it.

- Emitting: The parent node uses the child's name to extract specific data from
  the Python object (via a dictionary key or dataclass attribute) to pass down
  to the child for serialization:

        child_val = parent_dict.get(child_rule.name)

### Anonymous Rules (`name == ""`)

- Parsing: The rule reads binary data and returns the Python value, but does
  NOT save it to the context. The value is still returned, where it can be,
  e.g., gathered by the parent node into a list.

- Emitting: The parent node does not try to extract a sub-field. Instead, it
  passes its entire data context straight through to the anonymous child.

- Note that anonymous leaves only make sense as children of nodes like `Vector`
  which explicitly distribute values to their children. Otherwise, during
  serialization they are passed the entire context instead of a scalar value,
  and crash.


## The `Struct` Class

`Struct` is the primary bridge between the AST and the "model" of nested Python
dataclases. It evaluates its child rules, and maps the resulting named values
into the attributes of a dataclass.

For example, imagine a contrived NITF spec where a point is defined:

- A (pointless) LENGTH field with total size of the X and Y fields.
- X is a four-digit integer.
- Y is a four-digit integer.

.. code-block:: python

    @dataclass
    class Point:
        X: int
        Y: int

    point_rule = Struct(
        model_cls=Point,
        rules=[
            # Anonymous rules execute, but their return value is not assigned
            # as a value. Note that there is no class "between" Point and its X
            # and Y attributes.
            SizedBlock(
                # Named rules that don't appear in the dataclass are dropped
                # while parsing, and must have some way of being created during
                # serialization. Here, SizedBlock will populate LENGTH.
                length_rule=Int("LENGTH", 2),

                # Named rules map directly to dataclass attributes
                body=[
                    Int("X", size=4),
                    Int("Y", size=4),
                ]
            ),
        ]
    )
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import ChainMap, deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import KW_ONLY, dataclass, field, fields
from dataclasses import Field as DataclassField
from datetime import UTC, date, datetime, timezone
from decimal import Decimal
from enum import IntEnum, StrEnum
from functools import cached_property
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


@dataclass
class Item:
    """A name and serializable value for a NITF field."""

    name: str
    value: bytes | StreamablePayload


def item_size(items: list[Item]) -> int:
    """Get the total size of the binary data in a list of Items."""
    return sum(len(item.value) for item in items)


class StreamablePayload(Protocol):
    """Generic interface for streamable byte data.

    For image data (pixels), this allows the data to be ignored or lazily
    read/copied as needed.
    """

    def __len__(self) -> int: ...
    def write(self, out_fd: BinaryIO) -> None: ...
    def read(self) -> bytes: ...


class Context(ABC):
    """A context maintained during parsing or serialization.

    See the description in the module docstring for more info.
    """

    is_parsing: ClassVar[bool] = False
    is_emitting: ClassVar[bool] = False

    def __init__(self, init: dict[str, Any] | None = None) -> None:
        # Stacked namespaces for evaluation contexts.
        self._contexts: ChainMap[str, Any] = ChainMap(init or {})

        # Stacked indices for tracking position inside lists.
        self.indices: list[int] = []

        # Current path from the root to the node, (node, indices).
        self.path: list[tuple[BaseRule[Any], tuple[int, ...]]] = []

    def __getitem__(self, key: str) -> Any:
        return self._contexts[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._contexts[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._contexts

    def get(self, key: str, default: Any = None) -> Any:
        return self._contexts.get(key, default)

    @contextmanager
    def scope(self, init: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        """Enter a new local scope and yield it."""
        local_scope = init if init is not None else {}
        self._contexts.maps.insert(0, local_scope)

        try:
            yield local_scope
        finally:
            self._contexts.maps.pop(0)

    def iterate[V](self, iterable: Iterable[V]) -> Iterator[V]:
        """Iterate over a sequence while tracking the index for error paths.

        Using this allows the context to track repeated child rules, so that
        `ctx.subscripts` can accurately show indices like `[0][2]` during
        exceptions and string dumps.
        """
        self.indices.append(0)

        try:
            for i, val in enumerate(iterable):
                self.indices[-1] = i
                yield val
        finally:
            self.indices.pop()

    def format_subscripts(self) -> str:
        """Get a string with the current indices, e.g. '[2][0]'."""
        if not self.indices:
            return ""

        return "".join(f"[{i}]" for i in self.indices)

    def format_path(self) -> str:
        path_strs: list[str] = []
        for node, indices in self.path:
            sub_str = "".join(f"[{i}]" for i in indices) if indices else ""
            path_strs.append(node.display_name() + sub_str)

        return "\n  -> ".join(path_strs)

    @abstractmethod
    def format_fields(self) -> str:
        """Get a string with the most recently processed fields."""

    def format_error(
        self, action: str, base_msg: str, offset: int | None = None
    ) -> str:
        """Get a error message desribing parsing/serialization state."""

        offset_str = "" if offset is None else f" at byte {offset} (0x{offset:04X})"

        return (
            f"Error {action}{offset_str}"
            f"\n\nCause: {base_msg}"
            f"\n\nWhere:\n  {self.format_path()}"
            f"{self.format_fields()}"
        )


class ParseContext(Context):
    """Context while reading binary data into Python objects.

    State is accumulated sequentially. Variables become available in the
    context only *after* their corresponding binary fields have been parsed.
    """

    is_parsing: ClassVar[bool] = True

    def __init__(self, init: dict[str, Any] | None = None) -> None:
        super().__init__(init)

        # Recently-processed fields (byte offset, name, value), to add context
        self.fields: deque[tuple[int | None, str, Any]] = deque(maxlen=5)

    @override
    def format_fields(self) -> str:
        if not self.fields:
            return ""

        return "\n\nRecent fields:\n" + "\n".join(
            f"  [{off} (0x{off:04X})] {name}: {val!r}" for off, name, val in self.fields
        )


@dataclass
class EmitContext(Context):
    """Context while serializing Python objects into binary fields.

    State is populated preemptively. Structural nodes push the attributes of
    the Python object into the context *before* evaluating their child rules.
    """

    is_emitting: ClassVar[bool] = True

    def __init__(self, init: dict[str, Any] | None = None) -> None:
        super().__init__(init)

        # Recently-processed fields (name, value).
        self.fields: deque[tuple[str, Any]] = deque(maxlen=5)

    @override
    def format_fields(self) -> str:
        if not self.fields:
            return ""

        return "\n\nRecent fields:\n" + "\n".join(
            f"  {name}: {val!r}" for name, val in self.fields
        )


class Rule[T](Protocol):
    """A rule for encoding and decoding NITF data.

    Instances of this class describe how to read binary data into Python
    objects, and how to serialize Python objects back into binary `Item`
    objects. They generate `Item` objects rather than writing binary output
    because it's useful to manipulate/examine the fields before output.
    """

    name: str

    def parse(self, fd: BinaryIO, ctx: ParseContext) -> T: ...
    def to_fields(self, value: T, ctx: EmitContext) -> list[Item]: ...


class MatchableRule[T](Rule[T], Protocol):
    """A Rule that defines a `matches` method, so you can ask it about type.

    Currently only used by `Variant`, which routes on _type_ rather than on
    _name_; this protocol verifies the existence of the `matches` method used
    to effect that.
    """

    def matches(self, value: Any) -> TypeGuard[T]: ...


@dataclass
class BaseRule[T](ABC):
    """Default behavior for Rule classes.

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
        ctx.path.append((self, tuple(ctx.indices)))

        try:
            val = self._read(fd, ctx)
        except ParseError:
            raise
        except Exception as e:
            msg = ctx.format_error("parsing", str(e), start_offset)
            raise ParseError(msg) from e
        else:
            if self.name:
                ctx[self.name] = val
            return val
        finally:
            ctx.path.pop()

    @final
    def to_fields(self, value: T, ctx: EmitContext) -> list[Item]:
        ctx.path.append((self, tuple(ctx.indices)))

        try:
            return self._emit(value, ctx=ctx)
        except SerializeError:
            raise
        except Exception as e:
            msg = ctx.format_error("serializing", str(e))
            raise SerializeError(msg) from e
        finally:
            ctx.path.pop()

    def display_name(self) -> str:
        """Used only for displaying the name in errors."""

        # Start with the DSL name of the AST node.
        cname = self.__class__.__name__

        # Decorate the name with the wrapped spec or implemented class. This
        # relies on the convention of using common names for these values.
        rule = getattr(self, "rule", None)
        body = getattr(self, "body", None)
        mcls = getattr(self, "model_cls", None)
        mname = f"({mcls.__name__})" if mcls else ""
        sname = f"({rule.name})" if rule and hasattr(rule, "name") and rule.name else ""
        bname = f"({body.name})" if body and hasattr(body, "name") and body.name else ""

        # Prefix with the assigned name, if this rule isn't anonymous.
        aname = f"{self.name}:" if self.name else ""

        return f"{aname}{cname}{mname}{sname}{bname}"

    @abstractmethod
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T: ...

    @abstractmethod
    def _emit(self, value: T, *, ctx: EmitContext) -> list[Item]: ...


@dataclass
class Field[T](BaseRule[T], ABC):
    """A description of a single NITF field.

    These are the "leaves" of our syntax tree: they are responsible for actual
    reading and writing of binary data. They are usually a single scalar data
    element.

    They have an optional `validate` field to check if a value is allowed in
    the NITF spec before writing.
    """

    # The specified size in bytes of the field according to the NITF spec.
    size: int

    # An optional validation step before serialization.
    validate: Callable[[T], bool] | None = None

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T:
        start = fd.tell()
        val = self.decode(fd.read(self.size))
        ctx.fields.append((start, self.name + ctx.format_subscripts(), val))
        return val

    @override
    def _emit(self, value: T, *, ctx: EmitContext) -> list[Item]:
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

        full_name = self.name + ctx.format_subscripts()
        ctx.fields.append((full_name, value))

        return [Item(full_name, encoded)]

    @abstractmethod
    def encode(self, decoded: T) -> bytes:
        pass

    @abstractmethod
    def decode(self, encoded: bytes) -> T:
        pass


@dataclass
class Combinator[T](BaseRule[T], ABC):
    """A rule for one or more NITF fields.

    These are the "branches" of our syntax tree. They structure the `Field`
    nodes. `Combinator` nodes are anonymous by default; see the description in
    the module docstring above.
    """

    name: str = field(default="", kw_only=True)


@dataclass
class Nothing(Field[None]):

    name: str = ""
    size: int = 0

    @override
    def encode(self, decoded: None) -> bytes:
        return b""

    @override
    def decode(self, encoded: bytes) -> None:
        return None

    def matches(self, value: object) -> TypeGuard[None]:
        return value is None


@dataclass
class Marker(Field[None]):
    """An empty value added to output for later processing."""

    size: int = 0

    @override
    def encode(self, decoded: None) -> bytes:
        return b""

    @override
    def decode(self, encoded: bytes) -> None:
        return None


@dataclass
class Bool(Field[bool]):

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
class Int(Field[int]):

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
class BcsString(Field[str]):
    """A string with the BCS character set."""

    @override
    def encode(self, decoded: str) -> bytes:
        return format(decoded, f"<{self.size}s").encode("ascii")

    @override
    def decode(self, encoded: bytes) -> str:
        return encoded.decode("ascii").rstrip()


@dataclass
class EcsString(Field[str]):
    """A string with the ECS character set."""

    @override
    def encode(self, decoded: str) -> bytes:
        return format(decoded, f"<{self.size}s").encode("latin_1")

    @override
    def decode(self, encoded: bytes) -> str:
        return encoded.decode("latin_1").rstrip()


@dataclass
class FixedBytes(Field[bytes]):
    """A fixed number of bytes."""

    @override
    def encode(self, decoded: bytes) -> bytes:
        return decoded

    @override
    def decode(self, encoded: bytes) -> bytes:
        return encoded


@dataclass
class BcsIntEnum[T: IntEnum](Field[T]):
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
class EcsStringEnum[T: StrEnum](Field[T]):
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
class BcsStringEnum[T: StrEnum](Field[T]):
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
class Fixed(Field[float]):
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
class FixedDecimal(Field[Decimal]):
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
class BcsFloat(Field[float]):
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
class IsoDate(Field[date]):
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
class HMSeconds(Field[float]):
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
class ConcatDatetime(Field[datetime]):
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
class Uuid(Field[UUID]):
    """UUID in canonical form."""

    size: int = field(default=36, init=False)

    @override
    def encode(self, decoded: UUID) -> bytes:
        return str(decoded).encode()

    @override
    def decode(self, encoded: bytes) -> UUID:
        return UUID(encoded.decode())


@dataclass
class BinaryInt(Field[int]):
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
class Constant[T](Field[T]):
    """A wrapper that both supplies and expects a specific value."""

    def __init__(self, rule: Field[T], value: T) -> None:
        super().__init__(name=rule.name, size=rule.size, validate=None)

        self.rule: Field[T] = rule
        self.value: T = value

    @override
    def decode(self, encoded: bytes) -> T:
        parsed = self.rule.decode(encoded)
        if parsed != self.value:
            msg = (
                f"Constant mismatch for '{self.rule.name}': "
                f"expected {self.value!r}, got {parsed!r}"
            )
            raise ValueError(msg)
        return self.value

    @override
    def encode(self, decoded: T) -> bytes:
        if decoded is not None and decoded != self.value:
            msg = f"Cannot override constant '{self.rule.name}' with {decoded}."
            raise ValueError(msg)

        return self.rule.encode(self.value)


@dataclass
class Override[T, V](Field[T | V]):
    """Override specific byte patterns with a given value."""

    def __init__(self, rule: Field[T], mapping: dict[bytes, V]) -> None:
        # Replicate the inner spec's name and size.
        super().__init__(name=rule.name, size=rule.size, validate=None)

        self.rule: Field[T] = rule
        self.mapping: dict[bytes, V] = mapping

        for o_bytes in self.mapping:
            if len(o_bytes) != self.size:
                msg = f"Override {o_bytes!r} is wrong size"
                raise ValueError(msg)

    @override
    def decode(self, encoded: bytes) -> T | V:
        if encoded in self.mapping:
            return self.mapping[encoded]

        return self.rule.decode(encoded)

    @override
    def encode(self, decoded: T | V) -> bytes:
        for o_bytes, o_value in self.mapping.items():
            if decoded == o_value:
                return o_bytes

        # No overrides matched, use the default rule.
        return self.rule.encode(cast(T, decoded))


@dataclass
class Blankable[T](Override[T, None]):
    """All spaces in a `Field` return None."""

    def __init__(self, rule: Field[T]) -> None:
        blank_bytes = b" " * rule.size
        super().__init__(rule, {blank_bytes: None})


@dataclass
class Computed[T](Combinator[T]):
    """A rule that derives its value from the context during emit."""

    rule: Rule[T]
    getter: Callable[[Context], T]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T:
        return self.rule.parse(fd, ctx)

    @override
    def _emit(self, value: Any, *, ctx: EmitContext) -> list[Item]:
        computed_val = self.getter(ctx)

        # Save the computed value to the scope so later rule evaluations can
        # use it in the same way as they can during parsing.
        if self.rule.name:
            ctx[self.rule.name] = computed_val

        return self.rule.to_fields(computed_val, ctx)


@dataclass
class Mapped[T, U](Combinator[U]):
    """Generic mapping between encoded values and Pythong types.

    An "escape hatch" rule for handling unique values without needing to write
    a new `Rule` subclass. A `Mapped(FixedBytes(...))` can handle any field
    format.
    """

    rule: Rule[T]
    decoder: Callable[[T], U]
    encoder: Callable[[U], T]

    name: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.name = self.rule.name

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> U:
        return self.decoder(self.rule.parse(fd, ctx))

    @override
    def _emit(self, value: U, *, ctx: EmitContext) -> list[Item]:
        return self.rule.to_fields(self.encoder(value), ctx)


@dataclass
class Vector[T](Combinator[list[T]]):
    """A list of rules translated to/from a list of values."""

    rules: Sequence[Rule[T]]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> list[T]:
        return [rule.parse(fd, ctx) for rule in self.rules]

    @override
    def _emit(self, value: list[T], *, ctx: EmitContext) -> list[Item]:
        fields: list[Item] = []

        for rule, v in zip(self.rules, value, strict=True):
            fields.extend(rule.to_fields(v, ctx))

        return fields


@dataclass
class VarString(Combinator[str]):
    """A string prefixed by a length field."""

    len_rule: Field[int]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> str:
        length = self.len_rule.parse(fd, ctx)
        if length == 0:
            return ""
        return BcsString("", length).parse(fd, ctx)

    @override
    def _emit(self, value: str, *, ctx: EmitContext) -> list[Item]:
        if not value:
            return self.len_rule.to_fields(0, ctx)

        fields = self.len_rule.to_fields(len(value), ctx)
        fields.extend(BcsString("", len(value)).to_fields(value, ctx))
        return fields


@dataclass
class SizedList[T](Combinator[list[T]]):
    """Repeat a body rule `count` times.

    The count is supplied as an argument or extracted from the context.
    """

    count: int | Callable[[Context], int]
    body: Rule[T]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> list[T]:
        count = self.count(ctx) if callable(self.count) else self.count
        return [self.body.parse(fd, ctx) for _ in ctx.iterate(range(count))]

    @override
    def _emit(self, value: list[T], *, ctx: EmitContext) -> list[Item]:
        count = self.count(ctx) if callable(self.count) else self.count

        if len(value) != count:
            msg = f"Expected {count} items, got {len(value)}"
            raise RuntimeError(msg)

        fields: list[Item] = []
        for v in ctx.iterate(value):
            fields.extend(self.body.to_fields(v, ctx))

        return fields


@dataclass
class PrefixedList[T](Combinator[list[T]]):
    """Repeat a rule based on an initial field with a count."""

    count: Rule[int]
    body: Rule[T]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> list[T]:
        n = self.count.parse(fd, ctx)
        return [self.body.parse(fd, ctx) for _ in ctx.iterate(range(n))]

    @override
    def _emit(self, value: list[T], *, ctx: EmitContext) -> list[Item]:
        fields = self.count.to_fields(len(value), ctx)
        for v in ctx.iterate(value):
            fields.extend(self.body.to_fields(v, ctx))

        return fields


@dataclass
class PrefixedArray[T](Combinator[list[list[T]]]):
    """A 2D array of rules prefixed by row and column counts."""

    rows_rule: Rule[int]
    cols_rule: Rule[int]
    body: Rule[T]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> list[list[T]]:
        rows = self.rows_rule.parse(fd, ctx)
        cols = self.cols_rule.parse(fd, ctx)

        return [
            [self.body.parse(fd, ctx) for _ in ctx.iterate(range(cols))]
            for _ in ctx.iterate(range(rows))
        ]

    @override
    def _emit(self, value: list[list[T]], *, ctx: EmitContext) -> list[Item]:
        rows = len(value)
        cols = len(value[0]) if rows > 0 else 0

        for row in value:
            if len(row) != cols:
                msg = f"Jagged arrays are not supported in '{self.name}'."
                raise ValueError(msg)

        fields = self.rows_rule.to_fields(rows, ctx)
        fields.extend(self.cols_rule.to_fields(cols, ctx))

        for row in ctx.iterate(value):
            for item in ctx.iterate(row):
                fields.extend(self.body.to_fields(item, ctx))

        return fields


@dataclass
class Optional[T](Combinator[T | None]):
    """A boolean determines if the following body should exist."""

    condition: Rule[bool]
    body: Rule[T]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T | None:
        if not self.condition.parse(fd, ctx):
            return None

        return self.body.parse(fd, ctx)

    @override
    def _emit(self, value: T | None, *, ctx: EmitContext) -> list[Item]:
        if value is None:
            return self.condition.to_fields(False, ctx)

        return [*self.condition.to_fields(True, ctx), *self.body.to_fields(value, ctx)]


@dataclass
class Conditional[T](Combinator[T | None]):
    """Determine if the body should exist based on context."""

    condition: Callable[[Context], bool]
    body: Rule[T]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T | None:
        if self.condition(ctx):
            return self.body.parse(fd, ctx)
        return None

    @override
    def _emit(self, value: T | None, *, ctx: EmitContext) -> list[Item]:
        if not self.condition(ctx):
            return []

        if value is None:
            msg = "Condition evaluated to True, but no value was provided."
            raise ValueError(msg)

        return self.body.to_fields(value, ctx)


class DataclassProtocol(Protocol):
    """A type protocol to identify dataclass instances/types."""

    __dataclass_fields__: ClassVar[dict[str, DataclassField[Any]]]


@dataclass
class Struct[T: DataclassProtocol](Combinator[T], MatchableRule[T]):
    """A structural node that routes child values to/from a dataclass.

    For a high-level overview of how `Struct` bridges the AST and Python
    models, see the module docstring.

    Note: `Struct` enforces a local scope. When this node finishes parsing, all
    values generated by its child rules are popped from the context stack and
    destroyed. If a subsequent rule _outside_ this `Struct` needs to reference
    a value parsed inside it, it cannot look up the raw child name.

    For example, this would not work after the `Struct` finishes:

        ctx["FOO"]  # KeyError!

    Instead, look up the `Struct` itself in the parent context, and access the
    attribute on the resulting dataclass:

        ctx["header_struct"].FOO
    """

    model_cls: type[T]
    rules: Sequence[Rule[Any]]

    @cached_property
    def _field_names(self) -> set[str]:
        """Avoid re-computing the set of fields names during read/write."""
        return {f.name for f in fields(self.model_cls)}

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T:
        with ctx.scope() as local_scope:
            for rule in self.rules:
                # Rely on the behavior of `BaseRule.parse`, which injects named
                # values into the local scope.
                rule.parse(fd, ctx)

        # Route the value from the child named `foo` to the dataclass attribute
        # `foo`, discarding values with no matching attribute name.
        valid_keys = local_scope.keys() & self._field_names
        filtered_kwargs = {k: local_scope[k] for k in valid_keys}
        return self.model_cls(**filtered_kwargs)

    @override
    def _emit(self, value: T, *, ctx: EmitContext) -> list[Item]:
        # Use `vars` here to unpack a single level of the dataclass, rather
        # than `dataclasses.asdict`, which is recursive.
        val_dict = vars(value)

        # Route the dataclass attribute `foo` to the rule with name `foo`. Give
        # anonymous rules the entire dict, assuming that they will do their own
        # routing. Also push the dict to the context, so that any descendant
        # node can reach into `ctx` if it needs non-local values.
        with ctx.scope(val_dict):
            out_fields: list[Item] = []
            for rule in self.rules:
                child_val = val_dict.get(rule.name) if rule.name else val_dict
                out_fields.extend(rule.to_fields(child_val, ctx))

        return out_fields

    @override
    def matches(self, value: object) -> TypeGuard[T]:
        """Check if a Python object belongs to this record's dataclass."""
        return isinstance(value, self.model_cls)


@dataclass
class Variant[TagType, ValueType](Combinator[ValueType]):
    """A discriminated union of rules.

    The leading field is a tag that determines the form of the following
    fields.
    """

    tag_rule: Field[TagType]
    cases: dict[TagType, MatchableRule[ValueType]]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> ValueType:
        tag = self.tag_rule.parse(fd, ctx)

        if tag not in self.cases:
            msg = f"Unrecognized tag {tag!r} in Variant '{self.name}'"
            raise ValueError(msg)

        parser = self.cases[tag]
        return parser.parse(fd, ctx)

    @override
    def _emit(self, value: ValueType, *, ctx: EmitContext) -> list[Item]:
        tag_to_write = None

        for tag, rule in self.cases.items():
            if rule.matches(value):
                tag_to_write = tag
                break

        if tag_to_write is None:
            cname = type(value).__name__
            msg = f"Unexpected class {cname} for Variant '{self.name}'"
            raise TypeError(msg)

        rule_to_use = self.cases[tag_to_write]
        fields = self.tag_rule.to_fields(tag_to_write, ctx)
        fields.extend(rule_to_use.to_fields(value, ctx))

        return fields


@dataclass
class Group(Combinator[dict[str, Any]]):
    """A rule that returns its child values as a dict.

    Mainly used to build and run a list of rules, e.g. for segment headers. It
    has the same scope behavior as `Struct` (see that class for more details),
    but that's mostly irrelevant, since `Group` is used at the top level.
    """

    rules: Sequence[Rule[Any]]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> dict[str, Any]:
        with ctx.scope() as local_scope:
            for rule in self.rules:
                rule.parse(fd, ctx)

            return local_scope

    @override
    def _emit(self, value: dict[str, Any], *, ctx: EmitContext) -> list[Item]:
        with ctx.scope(value):
            out_fields: list[Item] = []
            for rule in self.rules:
                child_val = value.get(rule.name) if rule.name else value
                out_fields.extend(rule.to_fields(child_val, ctx))

        return out_fields


@dataclass
class SizedBlock(Combinator[Any]):
    """A rule with a leading value containing the size of the body.

    Unlike `Struct` or `Group`, `SizedBlock` isn't structural: it doesn't
    doesn't push a new scope, and it doesn't produce a value. It simply passes
    the context through to its child rules.
    """

    name: str = field(default="", init=False)
    length_rule: Rule[int]
    body: Sequence[Rule[Any]]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> None:
        expected_size = self.length_rule.parse(fd, ctx)
        start_pos = fd.tell()

        for rule in self.body:
            # Children inject their values directly into the parent scope.
            rule.parse(fd, ctx)

        bytes_read = fd.tell() - start_pos
        if bytes_read != expected_size:
            msg = f"Expected {expected_size} bytes, but read {bytes_read} bytes."
            raise RuntimeError(msg)

    @override
    def _emit(self, value: dict[str, Any], *, ctx: EmitContext) -> list[Item]:
        body_fields: list[Item] = []

        for rule in self.body:
            child_val = value.get(rule.name) if rule.name else value
            body_fields.extend(rule.to_fields(child_val, ctx))

        body_len = sum(len(f.value) for f in body_fields)
        len_fields = self.length_rule.to_fields(body_len, ctx)
        return len_fields + body_fields


@dataclass
class Switch[TagType, T](Combinator[T], MatchableRule[T]):
    """Branches parsing logic based on a previously evaluated context value."""

    get_tag: Callable[[ParseContext], TagType]
    cases: dict[TagType, MatchableRule[T]]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T:
        tag = self.get_tag(ctx)

        if tag not in self.cases:
            msg = f"Unrecognized tag {tag!r} for Switch '{self.name}'."
            raise ValueError(msg)

        return self.cases[tag].parse(fd, ctx)

    @override
    def _emit(self, value: T, *, ctx: EmitContext) -> list[Item]:
        tag_to_write = None

        for tag, rule in self.cases.items():
            if rule.matches(value):
                tag_to_write = tag
                break

        if tag_to_write is None or tag_to_write not in self.cases:
            msg = f"Cannot map payload {value!r} to a Switch branch."
            raise ValueError(msg)

        return self.cases[tag_to_write].to_fields(value, ctx)

    @override
    def matches(self, value: object) -> TypeGuard[T]:
        return any(rule.matches(value) for rule in self.cases.values())


@dataclass
class Alias[T](BaseRule[T]):
    """Wraps a rule to change its routing name in the AST.

    Allows you to assign a rule with a given name to a different attribute.
    """

    rule: Rule[T]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T:
        return self.rule.parse(fd, ctx)

    @override
    def _emit(self, value: T, *, ctx: EmitContext) -> list[Item]:
        # If the child rule has a name, it (or further descendants) might look
        # for the value based on that name in the context.
        if self.rule.name:
            with ctx.scope({self.rule.name: value}):
                return self.rule.to_fields(value, ctx)

        return self.rule.to_fields(value, ctx)


@dataclass
class Segment[T: DataclassProtocol](Struct[T]):
    """Splits a dataclass into header and data fields.

    NITF measures the length of the segment subheader and segment data
    separately.
    """

    model_cls: type[T]
    subheader: list[Rule[Any]]
    data: list[Rule[Any]]

    rules: Sequence[Rule[Any]] = field(init=False)

    def __post_init__(self) -> None:
        # Collect the subheader and data rules into `self.rules` so the
        # `Struct` logic works unchanged.
        self.rules = self.subheader + self.data

    def emit_segment(self, value: T, ctx: EmitContext) -> tuple[list[Item], list[Item]]:
        """As _emit, but return the fields split into subheader and data fields."""
        val_dict = vars(value)

        with ctx.scope(val_dict):
            sub_fields: list[Item] = []
            for rule in self.subheader:
                child_val = val_dict.get(rule.name) if rule.name else val_dict
                sub_fields.extend(rule.to_fields(child_val, ctx))

            data_fields: list[Item] = []
            for rule in self.data:
                child_val = val_dict.get(rule.name) if rule.name else val_dict
                data_fields.extend(rule.to_fields(child_val, ctx))

            return sub_fields, data_fields


@dataclass
class ReservedExtensions(Combinator[Any]):
    """A transparent block for dynamic Reserved Field Areas (e.g., CSCSDB).

    Reads the global reserved length, the mask length, the boolean mask,
    and then selectively reads the payload for each active area.
    Unrecognized areas are preserved as raw bytes to allow round-tripping.

    Each Rule in cases must have a name. When parsing, if that reserved area is
    present, it will be assigned to that name, which will otherwise be None.
    When emitting, a reserved area will be generated for each of the items with
    non-None values.
    """

    name: str = field(default="", init=False)
    size: Rule[int]
    mask_size: Rule[int]

    # Maps a **1-based** area index to a `Rule`.
    cases: dict[int, Rule[Any]]

    # Unknown Reserved Field Areas can be parsed as raw bytes and stored for
    # correct round-tripping. `unknown_name` will be the name for the unknown
    # fields, stored as a dict[int, bytes].
    unknown_name: str = "unknown_extensions"

    def __post_init__(self) -> None:
        for i, rule in self.cases.items():
            if not rule.name:
                msg = f"Area rules must have a 'name', but area {i} does not."
                raise ValueError(msg)

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> None:
        total_len = self.size.parse(fd, ctx)

        # Initialize all defined areas to None in the parent scope.
        for rule in self.cases.values():
            if rule.name:
                ctx[rule.name] = None

        # Initialize the unknown entries.
        ctx[self.unknown_name] = {}

        if total_len == 0:
            return

        mask_len = self.mask_size.parse(fd, ctx)
        mask = BcsString("RESERVED_FIELD_MASK", mask_len).parse(fd, ctx)

        unknowns: dict[int, bytes] = {}

        for i in range(1, mask_len + 1):
            if mask[i - 1] == "0":
                continue

            if i not in self.cases:
                area_len = Int(f"RESERVED_LEN_AREA{i}", 9).parse(fd, ctx)
                unknowns[i] = fd.read(area_len)
                continue

            rule = self.cases[i]
            SizedBlock(Int(f"RESERVED_LEN_AREA{i}", 9), [rule]).parse(fd, ctx)

        ctx[self.unknown_name] = unknowns
        return

    @override
    def _emit(self, value: dict[str, Any], *, ctx: EmitContext) -> list[Item]:
        unknowns: dict[int, bytes] = value.get(self.unknown_name) or {}

        active_indices = set(unknowns.keys())
        for i, rule in self.cases.items():
            if rule.name and value.get(rule.name) is not None:
                active_indices.add(i)

        if not active_indices:
            return self.size.to_fields(0, ctx)

        mask_len = max(active_indices)
        mask_chars: list[str] = []
        area_fields: list[Item] = []

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
                area_fields.append(Item(f"RESERVED_AREA_{i}_DATA", payload_bytes))
            else:
                rule = self.cases[i]
                block = SizedBlock(Int(f"RESERVED_LEN_AREA{i}", 9), body=[rule])
                area_fields.extend(block.to_fields(value, ctx))

        mask_str = "".join(mask_chars)
        mlen_field = self.mask_size.to_fields(mask_len, ctx)
        mask_field = BcsString("RESERVED_FIELD_MASK", mask_len).to_fields(mask_str, ctx)
        header_fields = [*mlen_field, *mask_field]

        total_len = item_size(header_fields) + item_size(area_fields)
        rfa_len_field = self.size.to_fields(total_len, ctx)

        return [*rfa_len_field, *header_fields, *area_fields]


@dataclass
class RuleNotImplemented(BaseRule[None]):

    name: str = ""

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> None:
        raise NotImplementedError

    @override
    def _emit(self, value: None, *, ctx: EmitContext) -> list[Item]:
        raise NotImplementedError
