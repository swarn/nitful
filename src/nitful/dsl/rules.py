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

import io
from abc import ABC, abstractmethod
from collections import ChainMap
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import KW_ONLY, InitVar, dataclass, field, fields
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

from nitful.core.errors import DefinitionError, ParseError, SerializeError


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

    action: ClassVar[str] = ""

    def __init__(self, init: dict[str, Any] | None = None) -> None:
        # Stacked namespaces for evaluation contexts.
        self._contexts: ChainMap[str, Any] = ChainMap(init or {})

        # Stacked indices for tracking position inside lists.
        self.indices: list[int] = []

        # Current path from the root to the node, (node, indices).
        self.path: list[tuple[Rule[Any], tuple[int, ...]]] = []

    def __getitem__(self, key: str) -> Any:
        return self._contexts[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._contexts[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._contexts

    def get(self, key: str, default: Any = None) -> Any:
        return self._contexts.get(key, default)

    @contextmanager
    def scope(self, init: dict[str, Any] | None = None) -> Generator[dict[str, Any]]:
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

    def format_error(self, base_msg: str, offset: int | None = None) -> str:
        """Get a error message desribing parsing/serialization state."""

        offset_str = "" if offset is None else f" at byte {offset} (0x{offset:04X})"

        return (
            f"Error {self.action}{offset_str}"
            f"\n\nCause: {base_msg}"
            f"\n\nWhere:\n  {self.format_path()}"
            f"{self.format_fields()}"
        )


class ParseContext(Context):
    """Context while reading binary data into Python objects.

    State is accumulated sequentially. Variables become available in the
    context only *after* their corresponding binary fields have been parsed.
    """

    action: ClassVar[str] = "parsing"

    def __init__(self, init: dict[str, Any] | None = None) -> None:
        super().__init__(init)

        # All processed fields as (Item, offset).
        self.fields: list[tuple[Item, int]] = []

    @override
    def format_fields(self) -> str:
        if not self.fields:
            return ""

        return "\n\nRecent fields:\n" + "\n".join(
            f"  [{offset} (0x{offset:04X})] {item.name}: {item.value!r}"
            for item, offset in self.fields[-5:]
        )


@dataclass
class EmitContext(Context):
    """Context while serializing Python objects into binary fields.

    State is populated preemptively. Structural nodes push the attributes of
    the Python object into the context *before* evaluating their child rules.
    """

    action: ClassVar[str] = "serializing"

    def __init__(self, init: dict[str, Any] | None = None) -> None:
        super().__init__(init)

        # Recently-processed fields (name, value).
        self.fields: list[Item] = []

    @override
    def format_fields(self) -> str:
        if not self.fields:
            return ""

        return "\n\nRecent fields:\n" + "\n".join(
            f"  {item.name}: {item.value!r}" for item in self.fields[-5:]
        )


@dataclass
class Rule[T](ABC):
    """A rule for encoding and decoding NITF data.

    Rule classes describe how to read binary data into Python objects, and how
    to serialize Python objects back into binary `Item` objects. They generate
    `Item` objects rather than directly writing binary output because it's
    useful to manipulate/examine the fields before output.

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
            msg = ctx.format_error(str(e), start_offset)
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
            msg = ctx.format_error(str(e))
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
class Field[T](Rule[T], ABC):
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
        read_bytes = fd.read(self.size)
        val = self.decode(read_bytes)
        full_name = self.name + ctx.format_subscripts()
        ctx.fields.append((Item(full_name, read_bytes), start))
        return val

    @override
    def _emit(self, value: T, *, ctx: EmitContext) -> list[Item]:
        if self.validate and not self.validate(value):
            msg = f"Invalid value {value} for '{self.name}'"
            raise ValueError(msg)

        encoded = self.encode(value)
        if len(encoded) != self.size:
            payload_str = repr(encoded)
            max_len = 100
            if len(payload_str) > max_len:
                payload_str = payload_str[: max_len - 3] + "...'"
            msg = (
                f"Encoding error in '{self.name}': Expected {self.size} bytes, "
                f"but got {len(encoded)} bytes (Payload: {payload_str})"
            )
            raise ValueError(msg)

        full_name = self.name + ctx.format_subscripts()
        item = Item(full_name, encoded)
        ctx.fields.append(item)

        return [item]

    @abstractmethod
    def encode(self, decoded: T) -> bytes:
        pass

    @abstractmethod
    def decode(self, encoded: bytes) -> T:
        pass


@dataclass
class Combinator[T](Rule[T], ABC):
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
        return int(encoded)


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
class FixedFloat(Field[float]):
    """A fixed-format decimal-form rational number returned as a Python float.

    Used where the standard specifies a format with a fixed number of decimal
    places, e.g. "NN.NNN" or "±NN.NNN". When serializing, this formats the
    value to exactly `ndigits` decimal places, padding the left side to fit the
    required byte size.

    Examples:

        With size=8 and ndigits=2:

        -  12.3456 -> "00012.35"
        -  12.3    -> "00012.30"
        -  -12.3   -> "-0012.30"

        With size 8, ndigits=2, and sign=True:

        -  12.3456 -> "+0012.35"
        -  12.3    -> "+0012.30"
        -  -12.3   -> "-0012.30"
    """

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
        return float(encoded)


@dataclass
class DecimalFloat(Field[float]):
    """A decimal-form rational number returned as a Python float.

    Used where the standard doesn't specify a format for a rational number, but
    does specify the BCS-N character set, which implicitly forbids scientific
    notation.

    Examples with size=6:

    - 123       -> "000123"
    - 12.345    -> "12.345"
    - -12.345   -> "-12.35"
    - 12.3456   -> "12.346"
    - 12345.6   -> "012346"
    - 999.999   -> "001000"
    - 999999.9  -> error

    Notes:

    - There is no single canonical format, so "round-tripping" values using
      `DecimalFloat` may not create byte-identical files.
    - This ignores any concept of "significant digits" in the representation.

    """

    _: KW_ONLY
    pad_char: Literal[" ", "0"] = "0"

    @override
    def decode(self, encoded: bytes) -> float:
        return float(encoded)

    @override
    def encode(self, decoded: float) -> bytes:

        # The Python format spec doesn't support formatting as decimal-form
        # number of arbitrary precision in a fixed width, so we must. Start
        # with the maximum possible precision and return the first
        # representation that fits when removing trailing zeroes.
        for precision in range(15, -1, -1):
            s = f"{decoded:.{precision}f}"

            # Strip trailing zeros (and the decimal if it is hanging).
            if "." in s:
                s = s.rstrip("0").rstrip(".")

            # If it fits within the allowed byte size, pad and return.
            if len(s) <= self.size:
                # If zero padding, make sure the sign stays at the front.
                if self.pad_char == "0" and s.startswith("-"):
                    padded = "-" + s[1:].rjust(self.size - 1, "0")
                else:
                    padded = s.rjust(self.size, self.pad_char)

                return padded.encode("ascii")

        msg = f"Can not encode {decoded} in width {self.size}."
        raise ValueError(msg)


@dataclass
class ExpFloat(Field[float]):
    """A number formatted in scientific notation: ±i.nnnnnnE±ee

    Where the number of digits after the decimal point (n) is derived from the
    total width and number of exponent digits (e).
    """

    _: KW_ONLY

    edigits: int

    _precision: int = field(init=False)

    def __post_init__(self) -> None:
        # Where size = len("±i.nnnnnnE±ee"), the number of n digits is
        # calculated as precision = size - len("ee") - len("±i.E±")
        self._precision = self.size - self.edigits - 5

        if self._precision < 0:
            msg = f"Size {self.size} is too small for {self.edigits} exp digits."
            raise DefinitionError(msg)

    @override
    def encode(self, decoded: float) -> bytes:
        raw = format(decoded, f"+.{self._precision}E")
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

        # If the value is too small, round it to zero with the same sign.
        if exp_val < min_exp:
            msign = mantissa[0]
            zero_frac = "0" * self._precision
            zero_exp = "0" * self.edigits
            retval = f"{msign}0.{zero_frac}E+{zero_exp}"
        else:
            exp = format(exp_val, f"+0{self.edigits + 1}d")
            retval = f"{mantissa}E{exp}"

        return retval.encode("ascii")

    @override
    def decode(self, encoded: bytes) -> float:
        return float(encoded)


@dataclass
class FlexFloat(Field[float]):
    """A number with multiple possible representations.

    Used where the standard allows a numeric field to be represented as either
    of decimal-form or scientific notation. When serializing, this class uses a
    format that maximizes precision:

    Examples:

        - With size 12, 12.3456789    -> "0012.3456789"
        - With size 12, 12.3456789e12 -> "1.2345678e+13"

    Notes:

    - There is no single canonical format, so "round-tripping" values using
      `FlexFloat` may not create byte-identical files.
    - This ignores any concept of "significant digits" in the representation.

    Defaults to zero-padding, which natively satisfies both BCS-N requirements
    and BCS-A allowances without risking string misalignment.
    """

    _: KW_ONLY

    pad_char: str = "0"

    @override
    def decode(self, encoded: bytes) -> float:
        return float(encoded)

    @override
    def encode(self, decoded: float) -> bytes:
        align = "=" if self.pad_char == "0" else ">"

        # Start with the maximum precision possible for a float and reduce it
        # until the number fits in the specified width.
        for precision in range(15, 0, -1):
            format_spec = f"{self.pad_char}{align}{self.size}.{precision}g"
            formatted = format(decoded, format_spec)

            if len(formatted) <= self.size:
                return formatted.encode("ascii")

        msg = f"Cannot encode {decoded} into {self.size} bytes."
        raise ValueError(msg)


@dataclass
class FixedDecimal(Field[Decimal]):
    """A decimal-form number returned as a `Decimal` to maintain precision."""

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
    """Seconds formatted hhmmss.ddd

    NOTE:
    - "123456.78" is not 123456.78 seconds, but 12 hours, 34 minutes, and 56.78
      seconds!
    - Python's datetime.timedelta does not have sufficient resolution to
      represent this number for all uses in NITF.
    """

    @override
    def encode(self, decoded: float) -> bytes:
        h = int(decoded // 3600)
        m = int((decoded % 3600) // 60)
        s = decoded % 60

        if self.size == 6:  # noqa: PLR2004
            return f"{h:02d}{m:02d}{int(s):02d}".encode("ascii")

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
class Accept[T](Field[T]):
    """Map bytes to a value during parsing only.

    This is for handling values which are known to be generated by a vendor,
    but that are not compliant with the NITF spec.

    During parsing, map those byte sequences directly to valid values. If
    serialized later, the value will be written with a spec-compliant value.
    """

    def __init__(self, rule: Field[T], mapping: dict[bytes, T]) -> None:
        # Replicate the inner spec's name, size, and validation.
        super().__init__(name=rule.name, size=rule.size, validate=rule.validate)

        self.rule: Field[T] = rule
        self.mapping: dict[bytes, T] = mapping

        for o_bytes in self.mapping:
            if len(o_bytes) != self.size:
                msg = f"Canonicalize override {o_bytes!r} is wrong size"
                raise DefinitionError(msg)

    @override
    def decode(self, encoded: bytes) -> T:
        if encoded in self.mapping:
            return self.mapping[encoded]

        return self.rule.decode(encoded)

    @override
    def encode(self, decoded: T) -> bytes:
        return self.rule.encode(decoded)


@dataclass
class Check[T](Field[T]):
    """Validates a field during parsing.

    The default behavior of a field is to run the validator during
    serialization only; parsing errors only occur if the parsed value can't be
    converted to the expected type. This wrapper runs the field validator
    during parsing.
    """

    def __init__(self, rule: Field[T]) -> None:
        if rule.validate is None:
            msg = f"Cannot use Require on rule '{rule.name}': it has no validator."
            raise DefinitionError(msg)

        # Replicate the inner rule's metadata.
        super().__init__(name=rule.name, size=rule.size, validate=rule.validate)

        self.rule: Field[T] = rule

    @override
    def decode(self, encoded: bytes) -> T:
        val = self.rule.decode(encoded)

        if self.validate and not self.validate(val):
            msg = f"Parse validation failed: read {val!r}"
            raise ValueError(msg)

        return val

    @override
    def encode(self, decoded: T) -> bytes:
        return self.rule.encode(decoded)


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
                raise DefinitionError(msg)

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
class Dashable[T](Override[T, None]):
    """All '-' chars in a `Field` return None."""

    def __init__(self, rule: Field[T]) -> None:
        dash_bytes = b"-" * rule.size
        super().__init__(rule, {dash_bytes: None})


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
    """Generic mapping between encoded values and Python types.

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
    """A list of rules translated to/from a list of values.

    Unlike `SizedList` or `PrefixedList`, which repeat one rule `n` times to
    return a list of `n` items, a `Vector` uses `n` rules to return a list of
    `n` items.
    """

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
        count = self.count if isinstance(self.count, int) else self.count(ctx)
        return [self.body.parse(fd, ctx) for _ in ctx.iterate(range(count))]

    @override
    def _emit(self, value: list[T], *, ctx: EmitContext) -> list[Item]:
        count = self.count if isinstance(self.count, int) else self.count(ctx)

        if len(value) != count:
            msg = f"Expected {count} items, got {len(value)}"
            raise ValueError(msg)

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
class Struct[T: DataclassProtocol](Combinator[T]):
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
        # Unpack the dataclass into a dict. Don't use `dataclasses.asdict`: it
        # is recursive, but we want attributes to remain as dataclasses. Don't
        # use `vars`: it will fail on slotted dataclasses.
        val_dict = {name: getattr(value, name) for name in self._field_names}

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


@dataclass
class Packed[T](Combinator[T]):
    """Reads a chunk of bytes as a single field, then parses its internal structure.

    This is useful for several NITF fields that pack together multiple values
    in a single field, allowing us to maintain the packed field on the NITF
    side and use more structure on the Python side.
    """

    outer_rule: Field[bytes]
    inner_rule: Rule[T]

    def __post_init__(self) -> None:
        self.name = self.outer_rule.name

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> T:
        # Read the bytes and log the outer field (e.g., Item("ILOC", b"..."))
        # to the context's `fields`.
        raw_bytes = self.outer_rule.parse(fd, ctx)
        inner_fd = io.BytesIO(raw_bytes)

        start_fields = len(ctx.fields)

        try:
            # If it fails to parse, we'll get the correct path from the root,
            # and the packed field is just an offset inside the outer field.
            return self.inner_rule.parse(inner_fd, ctx)
        finally:
            # If it succeeds, leave only the outer field in the context.
            del ctx.fields[start_fields:]

    @override
    def _emit(self, value: T, *, ctx: EmitContext) -> list[Item]:
        start_fields = len(ctx.fields)

        try:
            inner_items = self.inner_rule.to_fields(value, ctx)
        finally:
            del ctx.fields[start_fields:]

        raw_bytes = b"".join(
            item.value for item in inner_items if isinstance(item.value, bytes)
        )

        return self.outer_rule.to_fields(raw_bytes, ctx)


type _Condition = type | tuple[type, ...] | Callable[[Any, EmitContext], bool]


@dataclass(frozen=True)
class Case[TagType, ValueType]:
    """One option for a Variant.

    Args:
        tag: the tag value for this option.
        condition: how to select this option during serialization, either by
            matching the value to a type, or with a predicate.
        rule: a rule to produce the value for this option.
    """

    tag: TagType
    condition: _Condition
    rule: Rule[ValueType]


@dataclass
class Variant[TagType, ValueType](Combinator[ValueType]):
    """A discriminated union.

    The first field is a tag that determines the form of the following fields.
    During parsing, `Variant` simply reads the tag, then parses using the
    `rule` from the `Case` with the matching tag.

    During serialization, `Variant` determines which `Case` to use by checking
    their `condition` fields. Most commonly `condition` is a type or list of
    types, and the `Case` is used if the value matches the given types. The
    condition can be also be a predicate that evaluates the value and the
    `EmitContext`.

    Args:
        tag_rule: The rule used to read/write the tag from/to the stream.
        cases: An iterable of `Case` objects defining the union.
    """

    tag_rule: Field[TagType]

    cases: InitVar[Iterable[Case[TagType, Any]]]

    _rule_for_tag: dict[TagType, Rule[Any]] = field(init=False)
    _conditions: list[tuple[TagType, _Condition]] = field(init=False)

    def __post_init__(self, cases: Iterable[Case[TagType, Any]]) -> None:
        self._rule_for_tag = {}
        self._conditions = []

        for case in cases:
            if case.tag in self._rule_for_tag:
                msg = f"Duplicate tag {case.tag!r} in Variant branches."
                raise DefinitionError(msg)

            self._rule_for_tag[case.tag] = case.rule
            self._conditions.append((case.tag, case.condition))

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> ValueType:
        tag = self.tag_rule.parse(fd, ctx)

        if tag not in self._rule_for_tag:
            msg = f"Unrecognized tag {tag!r}"
            raise ValueError(msg)

        return cast(ValueType, self._rule_for_tag[tag].parse(fd, ctx))

    @override
    def _emit(self, value: ValueType, *, ctx: EmitContext) -> list[Item]:
        tag_to_write = None

        for tag, condition in self._conditions:
            if isinstance(condition, type):
                if type(value) is condition:
                    tag_to_write = tag
                    break
            elif isinstance(condition, tuple):
                if type(value) in condition:
                    tag_to_write = tag
                    break
            elif callable(condition) and condition(value, ctx):
                tag_to_write = tag
                break

        if tag_to_write is None:
            cname = type(value).__name__
            msg = f"Cannot map {cname} to a Variant branch."
            raise TypeError(msg)

        fields = self.tag_rule.to_fields(tag_to_write, ctx)
        fields.extend(self._rule_for_tag[tag_to_write].to_fields(value, ctx))

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
class Switch[TagType, ValueType](Combinator[ValueType]):
    """Branches parsing logic based on a previously evaluated context value.

    This differs from `Variant` by:

    - not requiring that the discriminating value be a Field at the beginning
      of the block of Rules, and
    - requiring that the value be present in the model, rather than inferring
      it from the type of the value.
    """

    get_tag: Callable[[Context], TagType]
    cases: Mapping[TagType, Rule[Any]]

    @override
    def _read(self, fd: BinaryIO, ctx: ParseContext) -> ValueType:
        tag = self.get_tag(ctx)

        if tag not in self.cases:
            msg = f"Unrecognized tag {tag!r} for Switch."
            raise ValueError(msg)

        return cast(ValueType, self.cases[tag].parse(fd, ctx))

    @override
    def _emit(self, value: ValueType, *, ctx: EmitContext) -> list[Item]:
        tag = self.get_tag(ctx)

        if tag not in self.cases:
            msg = f"Unrecognized tag {tag!r} for Switch."
            raise ValueError(msg)

        return self.cases[tag].to_fields(value, ctx)


@dataclass
class Alias[T](Rule[T]):
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
