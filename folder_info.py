from typing import TypedDict


class FolderInfo(TypedDict):
    used_size: float
    subfolders: list[str]
