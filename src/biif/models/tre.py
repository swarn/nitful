from dataclasses import dataclass


class TRE:
    """Base class for all Tagged Record Extensions."""

    pass


@dataclass(kw_only=True)
class UnknownTRE(TRE):
    """Fallback for TREs without specifications."""

    tag: str
    raw_data: bytes
