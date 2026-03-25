# Trigger registration of all extensions.
from ._format import extensions
from .api import dump, load, read, save, write
from .models.file import BIIF

__all__ = [
    "BIIF",
    "dump",
    "load",
    "read",
    "save",
    "write",
]
