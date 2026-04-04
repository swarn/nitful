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


WIDTH = 68


def dump_fields(
    items: Iterable[Item],
    *,
    header: bool = False,
    image_nums: list[int] | None = None,
    tre_names: list[str] | None = None,
    des_names: list[str] | None = None,
) -> str:
    """Convert fields to a human-readable string, with optional filtering."""
    item_list = list(items)

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

    for i, item in enumerate(item_list):
        if item.name == "IM":
            tre_num = 0
            image_num += 1

            keep = not filtering or image_num in included_image
            lines = output if keep else filtered

            lines.append(format(f" IMAGE SEGMENT {image_num} ", f"=^{WIDTH}"))

        if item.name == "IMAGE DATA":
            keep = not filtering or image_num in included_image
            lines = output if keep else filtered

            title = f" IMAGE {image_num} DATA: {len(item.value)} bytes "
            lines.extend([
                "/" * WIDTH,
                format(title, f"/^{WIDTH}"),
                "/" * WIDTH,
            ])
            continue

        if not isinstance(item.value, bytes):
            val_str = f"<{len(item.value)} bytes>"
            lines.append(f"{item.name}: {val_str}")
            continue

        if item.name == "CETAG":
            tre_num += 1
            tre_name = item.value.decode().strip()

            keep = (
                not filtering
                or (image_num == 0 and header)
                or image_num in included_image
                or tre_name in included_tre
            )
            lines = output if keep else filtered

            location = "HEADER" if image_num == 0 else f"IMAGE {image_num}"
            title = f" {location} TRE {tre_num}: {item.value.decode()} "
            lines.append(format(title, f"=^{WIDTH}"))

        if item.name == "DE":
            des_num += 1
            desname = cast(bytes, item_list[i + 1].value).decode().strip()

            keep = not filtering or desname in included_des
            lines = output if keep else filtered

            title = format(f" DES {des_num}: {desname} ", f"=^{WIDTH}")
            lines.append(title)

        lines.extend(_format_item(item, WIDTH))

    return "\n".join(output)


def _format_item(item: Item, width: int) -> list[str]:
    if type(item.value) is not bytes:
        raise ValueError

    if len(item.value) == 0:
        return []

    val_str = f"{item.name}: {repr(item.value)[1:]}"

    if len(val_str) <= width:
        return [val_str]

    lines: list[str] = []
    lines.append(f"{item.name}:")

    chunk = bytearray()
    line_without_byte = "''"
    line_with_byte = "''"
    for byte in item.value:
        line_without_byte = line_with_byte
        chunk.append(byte)
        line_with_byte = f"  {repr(bytes(chunk))[1:]}"
        if len(line_with_byte) > width:
            lines.append(line_without_byte)
            chunk = chunk[-1:]
            line_with_byte = f"  {repr(bytes(chunk))[1:]}"

    lines.append(line_with_byte)
    return lines
