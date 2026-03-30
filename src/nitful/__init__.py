"""A DSL and parser for NITF (National Imagery Transmission Format) files."""

# Expose public namespaces.
from . import core, extensions

# Trigger registration of extensions.
from ._format import extensions as _

# Expose primary API functions.
from .api import dump, load, read, save, write

# Expose core exceptions and root file model.
from .core.errors import NitfError, ParseError, SerializeError
from .core.file import NitfFile

__all__ = [
    "NitfError",
    "NitfFile",
    "ParseError",
    "SerializeError",
    "core",
    "dump",
    "extensions",
    "load",
    "read",
    "save",
    "write",
]
