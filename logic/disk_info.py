import shutil
import logging
from config import PLATFORM


def get_drives_on_windows() -> list[str]:
    import string
    import ctypes
    drives: list[str] = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    for letter in string.ascii_uppercase:
        if bitmask & 1:
            drives.append(f"{letter}:\\")
        bitmask >>= 1
    logging.info(f'Получены диски: {drives}')
    return drives


def get_start_directories() -> list[str]:
    if PLATFORM == "Windows":
        return get_drives_on_windows()
    else:
        return ["/"]


def get_used_disk_size(path: str) -> int:
    _, used, _ = shutil.disk_usage(path)
    logging.info(f'Получен объем диска {path}: {used}')
    return used
