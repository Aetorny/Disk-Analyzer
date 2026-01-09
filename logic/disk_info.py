import os
import shutil
import logging
from config import PLATFORM


def get_drives_on_windows() -> list[str]:
    '''Возвращает диски, которые доступны в системе (только для Windows)'''
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
    '''Возвращает начальные директории'''
    if PLATFORM == "Windows":
        return get_drives_on_windows()
    else:
        return ["/"]


def get_used_disk_size(path: str) -> int:
    '''Возвращает используемый объем диска'''
    _, used, _ = shutil.disk_usage(path)
    logging.info(f'Получен объем диска {path}: {used}')
    return used


def is_root(path: str) -> bool:
    '''Проверяет является ли текущий путь корнем'''
    return path == os.path.dirname(path)
