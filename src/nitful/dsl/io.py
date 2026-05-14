import itertools
import re
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

SEGMENT_MARKERS = {
    "IM": "IMAGE",
    "SY": "GRAPHIC",
    "TE": "TEXT",
    "DE": "DES",
}


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

    section = "HEADER"
    current_des = ""
    section_count = 0
    tre_count = 0

    # If filtering, switch between kept and omitted lines.
    output: list[str] = []
    filtered: list[str] = []
    lines: list[str] = output if not filtering or header else filtered

    lines.append(format(" FILE HEADER ", f"=^{WIDTH}"))

    for i, item in enumerate(item_list):

        if item.name in SEGMENT_MARKERS:
            new_section = SEGMENT_MARKERS[item.name]

            if section != new_section:
                section = new_section
                section_count = 1
            else:
                section_count += 1

            tre_count = 0

            if section == "DES":
                current_des = cast(bytes, item_list[i + 1].value).decode().strip()
                title = f" {section} {section_count}: {current_des} "
                keep = not filtering or current_des in included_des
            elif section == "IMAGE":
                title = f" {section} {section_count} "
                keep = not filtering or section_count in included_image
            else:
                title = f" {section} {section_count} "
                keep = not filtering

            lines = output if keep else filtered
            lines.append(format(title, f"=^{WIDTH}"))

        elif item.name == "CETAG":
            tre_count += 1
            tre_name = cast(bytes, item.value).decode().strip()

            keep = (
                not filtering
                or (section == "HEADER" and header)
                or (section == "IMAGE" and section_count in included_image)
                or (section == "DES" and current_des in included_des)
                or tre_name in included_tre
            )
            lines = output if keep else filtered

            location = f"{section} {section_count}" if section_count > 0 else section
            title = f" {location} TRE {tre_count}: {tre_name} "
            lines.append(format(title, f"=^{WIDTH}"))

        lines.extend(_format_item(item, WIDTH))

    return "\n".join(itertools.chain(output, [""]))


def _format_item(item: Item, width: int) -> list[str]:

    if item.name == "IMAGE DATA":
        title = f" IMAGE DATA: {len(item.value)} bytes "
        return ["/" * width, format(title, f"/^{width}"), "/" * width]

    if not isinstance(item.value, bytes):
        val_str = f"<{len(item.value)} bytes>"
        return [f"{item.name}: {val_str}"]

    if len(item.value) == 0:
        return []

    return _format_bytes(item.name, item.value, width)


# Eagerly matches 4-char hex escapes, 2-char standard escapes, then single chars.
_REPR_TOKENIZER = re.compile(r"\\x[0-9a-fA-F]{2}|\\.|.")


def _format_bytes(name: str, data: bytes, width: int) -> list[str]:
    """Split a byte repr into multiple lines based on max width."""
    raw_repr = repr(data)

    val_str = f"{name}: {raw_repr[1:]}"
    if len(val_str) <= width:
        return [val_str]

    lines = [f"{name}:"]

    # Use the same quotes that Python uses for this string.
    quote = raw_repr[-1]
    inner_repr = raw_repr[2:-1]

    # Leave room for two leading spaces and surrounding quotes.
    inner_width = width - 4
    current_line_parts: list[str] = []
    current_len = 0

    for match in _REPR_TOKENIZER.finditer(inner_repr):
        token = match.group()
        token_len = len(token)

        if current_len + token_len > inner_width:
            lines.append(f"  {quote}{''.join(current_line_parts)}{quote}")
            current_line_parts.clear()
            current_len = 0

        current_line_parts.append(token)
        current_len += token_len

    if current_line_parts:
        lines.append(f"  {quote}{''.join(current_line_parts)}{quote}")

    return lines
