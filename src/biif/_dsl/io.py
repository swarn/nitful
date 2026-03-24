from typing import BinaryIO, Iterable

from biif._dsl.spec import Field


def write_fields(fields: Iterable[Field], out_fd: BinaryIO) -> None:
    """Write fields to a binary stream."""
    for field in fields:
        if isinstance(field.value, bytes):
            out_fd.write(field.value)
        else:
            field.value.write(out_fd)


def dump_fields(fields: Iterable[Field]) -> str:
    """Convert fields to a human-readable string."""
    field_list = list(fields)
    if not field_list:
        return ""

    width = 60

    image_num = 0
    tre_num = 0
    des_num = 0

    lines = [format(" FILE HEADER ", f"=^{width}")]

    for f in field_list:
        if f.name == "IMAGE START":
            tre_num = 0
            image_num += 1
            lines.append(format(f" IMAGE SEGMENT {image_num} ", f"=^{width}"))
            continue

        if f.name == "IMAGE DATA":
            title = f" IMAGE {image_num} DATA: {len(f.value)} bytes "
            lines.append("/" * width)
            lines.append(format(title, f"/^{width}"))
            lines.append("/" * width)
            continue

        if not isinstance(f.value, bytes):
            val_str = f"<{len(f.value)} bytes>"
            lines.append(f"{f.name}: {val_str}")
            continue

        if f.name == "CETAG":
            tre_num += 1
            if image_num == 0:
                location = "HEADER"
            else:
                location = f"IMAGE {image_num}"
            title = f" {location} TRE {tre_num}: {f.value.decode()} "
            lines.append(format(title, f"=^{width}"))

        if f.name.startswith("DES START"):
            des_num += 1
            desname = f.name.split()[-1]
            line = format(f" DES {des_num}: {desname} ", f"=^{width}")
            lines.append(line)
            continue

        if len(f.value) == 0:
            continue

        if isinstance(f.value, bytes):
            val_str = repr(f.value)[1:]
        else:
            val_str = f"<{len(f.value)} bytes>"

        lines.append(f"{f.name}: {val_str}")

    return "\n".join(lines)
