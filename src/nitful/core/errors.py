class NitfError(Exception):
    """Base exception for all nitful library errors."""


class ParseError(NitfError):
    """Base exception for any error encountered while reading a file."""


class SerializeError(NitfError):
    """Base exception for any error encountered while writing a file."""


class DefinitionError(NitfError):
    """An error in specification with the DSL."""
