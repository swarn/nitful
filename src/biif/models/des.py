from dataclasses import dataclass


class DES:
    pass


@dataclass(kw_only=True)
class UnknownDES(DES):
    """Fallback class for unrecognized DES types."""

    desid: str
    desver: int
    raw_header: bytes
    raw_data: bytes
