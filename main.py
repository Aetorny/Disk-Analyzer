import logging

from utils import load_all_databases, update_language
from config import set_default_values, SETTINGS, LANGUAGE, TRANSLATOR
from ui import DiskVisualizerApp, DiskIndexingApp


def check_language():
    if not SETTINGS['is_first_run']:
        return
    if LANGUAGE != SETTINGS['language']['current']:
        if update_language(LANGUAGE):
            SETTINGS['language']['current'] = LANGUAGE
            SETTINGS['is_first_run'] = False
            SETTINGS.save()
            TRANSLATOR.change_language(LANGUAGE)


def main() -> None:
    check_language()

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
