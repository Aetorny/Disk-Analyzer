import logging

from ui import DiskVisualizerApp, DiskIndexingApp
from utils import load_all_databases
from config import set_default_values


def main() -> None:
    databases = load_all_databases()
    logging.info(f'Получено {len(databases)} баз данных')
    logging.info(f'Ключи баз данных: {list(databases.keys())}')
    try:
        while True:
            set_default_values()

            for db in databases.values():
                db.open()

            indexing_app = DiskIndexingApp(databases)
            indexing_app.mainloop() # pyright: ignore[reportUnknownMemberType]

            from config import is_should_run_visualizer
            if is_should_run_visualizer:
                visualizer_app = DiskVisualizerApp(databases)
                visualizer_app.mainloop() # pyright: ignore[reportUnknownMemberType]
            
            from config import is_should_run_analyzer
            if not is_should_run_analyzer:
                break
    finally:
        logging.info(f'Закрытие {len(databases)} баз данных')
        for db in databases.values():
            db.close()

    logging.info('Программа завершена')


if __name__ == '__main__':
    main()
