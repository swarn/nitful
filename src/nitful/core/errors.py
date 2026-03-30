class NitfError(Exception):
    """Base exception for all errors raised by BIIF."""


class ParseError(NitfError):

    def __init__(self, msg: str, path: list[str], offset: int) -> None:
        self.base_msg: str = msg
        self.path: list[str] = path
        self.offset: int = offset
        super().__init__(self._format_msg())

    def _format_msg(self) -> str:
        path_str = " -> ".join(self.path)
        return (
            f"Parse failed at byte {self.offset} in [{path_str}]"
            f"\nReason: {self.base_msg}"
        )


class SerializeError(NitfError):

    def __init__(self, msg: str, path: list[str]) -> None:
        self.base_msg: str = msg
        self.path: list[str] = path
        super().__init__(self._format_msg())

    def _format_msg(self) -> str:
        path_str = " -> ".join(self.path)
        return f"Serialization failed at [{path_str}]\nReason: {self.base_msg}"
