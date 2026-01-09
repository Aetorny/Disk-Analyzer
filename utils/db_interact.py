import os
import glob

from logic import Database, get_start_directories
from utils import format_path
from config import DATA_DIR


def create_database(path: str) -> Database:
    name = f'usage_of_{format_path(path)}.db'
    db = Database(os.path.join(DATA_DIR, name))
    return db


def delete_database(path: str) -> None:
    os.remove(path)


def load_all_databases() -> dict[str, Database]:
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    dbs = glob.glob(os.path.join(DATA_DIR, '*.db'))
    databases: dict[str, Database] = {}
    for path in dbs:
        db = Database(path)
        try:
            db.open()
            root = db.get('__root__')
            assert isinstance(root, str)
            databases[root] = db
        except:
            delete_database(path)
        finally:
            db.close()
            
    disks = get_start_directories()
    for disk in disks:
        if disk not in databases:
            databases[disk] = create_database(disk)

    return databases
