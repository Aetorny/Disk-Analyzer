import os

from logic import Database, get_start_directories
from utils import format_disk_name
from config import DATA_DIR


def load_all_databases() -> dict[str, Database]:
    disks = get_start_directories()
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    databases: dict[str, Database] = {}
    for disk in disks:
        name = f'disk_{format_disk_name(disk)}_usage.db'
        databases[disk] = Database(os.path.join(DATA_DIR, name))

    return databases
