"""A DSL for NITF file specification.

The NITF format is a flat list of values. The values are fixed-width, and the
structure of the NITF file is implicit in the values.

One level of abstraction up, we can think of NITF files as a flat list of
key/value pairs where the keys are implicit: they are defined in the specs, but
not present in the file.

In Python, we want to use composite data structures, such as vector or record
types, where it makes sense. But, we want our Python ADTs and our
specifications to have different structures from each other, and of course from
the flat NITF format.

The classes in this modules comprise a domain-specific language (DSL) which
enables bidirectional conversion from NITF's flat structure to richer Python
types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import KW_ONLY, dataclass, field, fields
from dataclasses import Field as DataclassField
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, BinaryIO, ClassVar, Literal, Protocol, cast, override
from uuid import UUID

from .validator import Validator


@dataclass
class Field:
    """A name and serializable value for a NITF field."""

    name: str
    value: bytes | StreamablePayload


class StreamablePayload(Protocol):
    """Generic interface for streamable byte data.

    For image data (pixels), this allows the data to be ignored or lazily
    read/copied as needed.
    """

    def __len__(self) -> int: ...
    def write(self, out_fd: BinaryIO) -> None: ...
    def read(self) -> bytes: ...


class Spec[T](ABC):
    """A specification for NITF data.

    Instances of this class describe how to read binary data into Python
    objects, and how to serialize Python objects back into binary `Field`
    objects. They generate `Field` objects rather than writing binary output
    because it's useful to manipulate the fields before output.

    The specs can operate in a pure way (`read` and `to_fields`), or by reading
    to/from a dict (`read_into` and `fields_from`). This enables various
    structural groups and helps ease the friction between the flat NITF
    structure and nested Python ADTs.
    """

    # A spec name is used to describe the NITF field represented by the spec,
    # the name of the attribute where the result will be placed, or both.
    name: str

    @abstractmethod
    def read(self, fd: BinaryIO) -> T: ...

    @abstractmethod
    def to_fields(self, value: T) -> list[Field]: ...

    def read_into(self, fd: BinaryIO, kwargs: dict[str, Any]) -> None:
        """Read from the stream and the place the result in `kwargs`."""
        val = self.read(fd)
        if self.name:
            kwargs[self.name] = val

    def fields_from(self, values: dict[str, Any]) -> list[Field]:
        """Generate fields from values in the `values` dict."""
        val = values.get(self.name) if self.name else None
        return self.to_fields(cast(T, val))


@dataclass
class FieldSpec[T](Spec):
    """A specification for a single NITF field.

    These are the "leaves" of our syntax tree: they are responsible for actual
    reading and writing of binary data. They are usually a single scalar data
    element.

    They have an optional `validate` field to check if a value is allowed in
    the NITF spec before writing.
    """

    name: str

    # The specified size in bytes of the field according to the NITF spec.
    size: int

    # An optional validation step before serialization.
    validate: Validator[T] | None = None

    @override
    def read(self, fd: BinaryIO) -> T:
        b = fd.read(self.size)
        return self.decode(b)

    @override
    def to_fields(self, value: T) -> list[Field]:
        if self.validate and not self.validate(value):
            raise RuntimeError()

        encoded = self.encode(value)
        if len(encoded) != self.size:
            raise RuntimeError()

        return [Field(self.name, encoded)]

    @abstractmethod
    def encode(self, decoded: T) -> bytes:
        pass

    @abstractmethod
    def decode(self, encoded: bytes) -> T:
        pass


@dataclass
class Bool(FieldSpec[bool]):

    @override
    def encode(self, decoded: bool) -> bytes:
        return format(decoded).encode()

    @override
    def decode(self, encoded: bytes) -> bool:
        return bool(encoded.decode())


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
class IntWithStrSentinel(FieldSpec[int]):
    """An integer with a non-numeric sentinel value.

    When `sentinels[i]` is read from the binary data, it is translated to
    `values[i]` in Python. The reverse is also true.
    """

    sign: bool = False

    _: KW_ONLY

    sentinels: list[str]
    values: list[int]

    @override
    def encode(self, decoded: int) -> bytes:
        if decoded in self.values:
            idx = self.values.index(decoded)
            sentinel = self.sentinels[idx]
            return sentinel.encode()

        plus = "+" if self.sign else ""
        return f"{decoded:{plus}0{self.size}d}".encode()

    @override
    def decode(self, encoded: bytes) -> int:
        decoded = encoded.decode()
        if decoded in self.sentinels:
            idx = self.sentinels.index(decoded)
            return self.values[idx]

        return int(decoded)


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
class BcsIntEnum[T: Enum](FieldSpec[T]):
    """An integer enumeration in the NITF spec.

    The `enum` argument is a Python `Enum` that defines the valid integers and
    their meanings.
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
class EcsStringEnum[T: Enum](FieldSpec[T]):
    """A string enumeration with ECS characters in the NITF spec.

    The `enum` argument is a Python `Enum` that defines the valid strings and
    their meanings.
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
class BcsStringEnum[T: Enum](FieldSpec[T]):
    """A string enumeration with BCS characters in the NITF spec.

    The `enum` argument is a Python `Enum` that defines the valid strings and
    their meanings.
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
class Fixed[T: float | Decimal](FieldSpec[T]):
    """A fixed-point float."""

    _: KW_ONLY

    # Always show the sign for positive or negative numbers.
    sign: bool = False

    # The number of digits after the decimal point.
    ndigits: int = 2

    # The Python representation: float or Decimal.
    kind: type[T] = cast(type[T], float)

    @override
    def encode(self, decoded: T) -> bytes:
        plus = "+" if self.sign else ""
        format_str = f"{plus}0{self.size}.{self.ndigits}f"
        return format(decoded, format_str).encode()

    @override
    def decode(self, encoded: bytes) -> T:
        return self.kind(encoded.decode().strip())


@dataclass
class HexColor(FieldSpec[tuple[int, int, int]]):

    size: int = field(default=3, init=False)

    @override
    def encode(self, decoded: tuple[int, int, int]) -> bytes:
        return bytes(decoded)

    @override
    def decode(self, encoded: bytes) -> tuple[int, int, int]:
        result = tuple(encoded)

        if len(result) != 3:
            raise RuntimeError()

        return result


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

    @override
    def encode(self, decoded: datetime) -> bytes:
        return decoded.strftime(self.format).encode()

    @override
    def decode(self, encoded: bytes) -> datetime:
        return datetime.strptime(encoded.decode(), self.format)


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
class Constant[T](Spec[None]):
    """A wrapper that supplies and expects a specific value."""

    spec: FieldSpec[T]
    value: T

    @property
    def name(self) -> str:
        return self.spec.name

    @override
    def read(self, fd: BinaryIO) -> None:
        parsed = self.spec.read(fd)
        if parsed != self.value:
            raise ValueError(
                f"Constant mismatch for '{self.name}': "
                f"expected {self.value!r}, got {parsed!r}"
            )
        return None

    @override
    def to_fields(self, value: Any = None) -> list[Field]:
        return self.spec.to_fields(self.value)


@dataclass
class Marker(Spec[None]):
    """A no-op added to the spec for later processing."""

    name: str

    @override
    def read(self, fd: BinaryIO) -> None:
        return None

    @override
    def to_fields(self, value: Any = None) -> list[Field]:
        return [Field(self.name, b"")]


@dataclass
class ListRecord[T](Spec[list[T]]):
    """A list of varying specs with the same type."""

    specs: list[FieldSpec[T]]

    @override
    def read(self, fd: BinaryIO) -> list[T]:
        return [spec.read(fd) for spec in self.specs]

    @override
    def to_fields(self, value: list[T]) -> list[Field]:
        if len(value) != len(self.specs):
            msg = (
                f"ListRecord expects {len(self.specs)} values, "
                f"but got {len(value)}."
            )
            raise ValueError(msg)

        fields = []

        for spec, v in zip(self.specs, value):
            fields.extend(spec.to_fields(v))

        return fields


@dataclass
class FixedLengthList[T](Spec[list[T]]):
    """A fixed count of identical specs."""

    name: str = field(default="", init=False)
    count: int
    kind: Spec[T]

    @override
    def read(self, fd: BinaryIO) -> list[T]:
        return [self.kind.read(fd) for _ in range(self.count)]

    @override
    def to_fields(self, value: list[T]) -> list[Field]:
        if len(value) != self.count:
            raise RuntimeError(f"Expected {self.count} items, got {len(value)}")

        fields = []

        for i, val in enumerate(value):
            for f in self.kind.to_fields(val):
                f.name += f"[{i}]"
                fields.append(f)

        return fields


@dataclass
class VariableLengthList[T](Spec[list[T]]):
    """A variable count of identical specs.

    The count is specified in a leading field `num_field`.
    """

    name: str
    num_field: Spec[int]
    kind: Spec[T]

    @override
    def read(self, fd: BinaryIO) -> list[T]:
        n = self.num_field.read(fd)
        return [self.kind.read(fd) for _ in range(n)]

    @override
    def to_fields(self, value: list[T]) -> list[Field]:
        fields = self.num_field.to_fields(len(value))

        for i, v in enumerate(value):
            for f in self.kind.to_fields(v):
                f.name += f"[{i}]"
                fields.append(f)

        return fields


class DataclassProtocol(Protocol):
    """A type protocol to satisfy LSP checks for dataclass instances/types."""

    __dataclass_fields__: ClassVar[dict[str, DataclassField[Any]]]


@dataclass
class DataclassRecord[T: DataclassProtocol](Spec[T]):
    """Unpacks specs into a dataclass based on their names."""

    name: str
    model_cls: type[T]
    specs: Sequence[Spec[Any]]

    @override
    def read(self, fd: BinaryIO) -> T:
        kwargs = {}

        for spec in self.specs:
            spec.read_into(fd, kwargs)

        valid_model_fields = {f.name for f in fields(self.model_cls)}
        kwargs = {k: v for k, v in kwargs.items() if k in valid_model_fields}

        return self.model_cls(**kwargs)

    @override
    def to_fields(self, value: T) -> list[Field]:
        val_dict = vars(value)

        out_fields = []
        for spec in self.specs:
            out_fields.extend(spec.fields_from(val_dict))

        return out_fields

    def matches(self, value: Any) -> bool:
        return isinstance(value, self.model_cls)


@dataclass
class VariantRecord[TagType, PayloadType](Spec[PayloadType]):
    """A discriminated union of `DataclassRecord` specs."""

    name: str
    tag_spec: FieldSpec[TagType]
    cases: dict[TagType, DataclassRecord[Any]]

    @override
    def read(self, fd: BinaryIO) -> PayloadType:
        tag = self.tag_spec.read(fd)

        if tag not in self.cases:
            raise ValueError(f"Unrecognized tag {tag!r} in VariantRecord '{self.name}'")

        parser = self.cases[tag]
        return parser.read(fd)

    @override
    def to_fields(self, value: PayloadType) -> list[Field]:

        tag_to_write = None

        for tag, spec in self.cases.items():
            if spec.matches(value):
                tag_to_write = tag
                spec_to_use = spec
                break

        if tag_to_write is None:
            raise TypeError(
                f"Could not map payload of type {type(value).__name__} to a known tag "
                f"in VariantRecord '{self.name}'. Did you pass the wrong dataclass instance?"
            )

        fields = self.tag_spec.to_fields(tag_to_write)
        fields.extend(spec_to_use.to_fields(value))

        return fields


class InlineGroup(Spec[dict[str, Any]]):
    """Parse specs into a dict rather than a single value.

    Mostly used as a structural element to bring elements into a parent spec.
    """

    name: str = ""

    @override
    def read(self, fd: BinaryIO) -> dict[str, Any]:
        kwargs: dict[str, Any] = {}
        self.read_into(fd, kwargs)
        return kwargs

    @override
    def to_fields(self, value: dict[str, Any]) -> list[Field]:
        return self.fields_from(value)

    @abstractmethod
    @override
    def read_into(self, fd: BinaryIO, kwargs: dict[str, Any]) -> None: ...

    @abstractmethod
    @override
    def fields_from(self, values: dict[str, Any]) -> list[Field]: ...


@dataclass
class Block(InlineGroup):
    """A list of specs read as a dict."""

    specs: list[Spec[Any]]

    @override
    def read_into(self, fd: BinaryIO, kwargs: dict[str, Any]) -> None:
        for spec in self.specs:
            spec.read_into(fd, kwargs)

    @override
    def fields_from(self, values: dict[str, Any]) -> list[Field]:
        fields = []

        for spec in self.specs:
            fields.extend(spec.fields_from(values))

        return fields


@dataclass
class SizedBlock(InlineGroup):
    """A spec with a leading field with the size of the body spec."""

    length_spec: FieldSpec[int]
    body_spec: InlineGroup

    @override
    def read_into(self, fd: BinaryIO, kwargs: dict[str, Any]) -> None:
        _ = self.length_spec.read(fd)
        self.body_spec.read_into(fd, kwargs)

    @override
    def fields_from(self, values: dict[str, Any]) -> list[Field]:
        body_fields = self.body_spec.fields_from(values)
        body_len = sum(len(f.value) for f in body_fields)
        len_fields = self.length_spec.to_fields(body_len)
        return len_fields + body_fields
