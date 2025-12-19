from typing import Any, Iterator, Optional


class Folder:
    def __init__(self, path: str, parent: Optional["Folder"] = None) -> None:
        self.path = path
        self.subfolders_size: dict[str, int] = {}
        self.used_size: int = 0
        self.parent: Folder | None = parent
        if parent:
            parent.subfolders_size[self.path] = 0

    def __iter__(self) -> Iterator[tuple[str, Any]]:
        return iter({
            "path": self.path,
            "used_size": self.used_size,
            "subfolders_size": self.subfolders_size
        }.items())
