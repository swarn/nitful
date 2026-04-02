from collections.abc import Iterable
from typing import BinaryIO, cast

from .rules import Item


def write_fields(fields: Iterable[Item], out_fd: BinaryIO) -> None:
    """Write fields to a binary stream."""
    for field in fields:
        if isinstance(field.value, bytes):
            out_fd.write(field.value)
        else:
            field.value.write(out_fd)


WIDTH = 60


def dump_fields(
    fields: Iterable[Item],
    *,
    header: bool = False,
    image_nums: list[int] | None = None,
    tre_names: list[str] | None = None,
    des_names: list[str] | None = None,
) -> str:
    """Convert fields to a human-readable string, with optional filtering."""
    field_list = list(fields)

    # Inclusion lists if filtering.
    included_tre = set(tre_names or [])
    included_des = set(des_names or [])
    included_image = set(image_nums or [])
    filtering = bool(included_tre or included_des or included_image or header)

    image_num = 0
    tre_num = 0
    des_num = 0

    # If filtering, switch between kept and omitted lines.
    output: list[str] = []
    filtered: list[str] = []
    lines: list[str] = output if not filtering or header else filtered

    lines.append(format(" FILE HEADER ", f"=^{WIDTH}"))

    for i, f in enumerate(field_list):
        if f.name == "IM":
            tre_num = 0
            image_num += 1

            keep = not filtering or image_num in included_image
            lines = output if keep else filtered

            lines.append(format(f" IMAGE SEGMENT {image_num} ", f"=^{WIDTH}"))

        if f.name == "IMAGE DATA":
            keep = not filtering or image_num in included_image
            lines = output if keep else filtered

            title = f" IMAGE {image_num} DATA: {len(f.value)} bytes "
            lines.extend([
                "/" * WIDTH,
                format(title, f"/^{WIDTH}"),
                "/" * WIDTH,
            ])
            continue

        if not isinstance(f.value, bytes):
            val_str = f"<{len(f.value)} bytes>"
            lines.append(f"{f.name}: {val_str}")
            continue

        if f.name == "CETAG":
            tre_num += 1
            tre_name = f.value.decode().strip()

            keep = (
                not filtering
                or (image_num == 0 and header)
                or image_num in included_image
                or tre_name in included_tre
            )
            lines = output if keep else filtered

            location = "HEADER" if image_num == 0 else f"IMAGE {image_num}"
            title = f" {location} TRE {tre_num}: {f.value.decode()} "
            lines.append(format(title, f"=^{WIDTH}"))

        if f.name == "DE":
            des_num += 1
            desname = cast(bytes, field_list[i + 1].value).decode().strip()

            keep = not filtering or desname in included_des
            lines = output if keep else filtered

            title = format(f" DES {des_num}: {desname} ", f"=^{WIDTH}")
            lines.append(title)

        if len(f.value) == 0:
            continue

        val_str = repr(f.value)[1:]
        lines.append(f"{f.name}: {val_str}")

    return "\n".join(output)
