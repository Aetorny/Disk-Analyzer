import threading
import logging

from utils import load_all_databases, update_language
from config import set_default_values, SETTINGS, LANGUAGE, TRANSLATOR, path_to_resource
from ui import DiskVisualizerApp, DiskIndexingApp
import ui.loader_animation as loader_animation


def check_language():
    if not SETTINGS['is_first_run']:
        return
    if LANGUAGE != SETTINGS['language']['current']:
        threading.Thread(target=loader_animation.run_app, daemon=True).start()
        if update_language(LANGUAGE):
            SETTINGS['language']['current'] = LANGUAGE
            SETTINGS['is_first_run'] = False
            SETTINGS.save()
            TRANSLATOR.change_language(LANGUAGE)
        loader_animation.close = True

def main() -> None:
    check_language()

    databases = load_all_databases()
    logging.info(f'Получено {len(databases)} баз данных')
    logging.info(f'Ключи баз данных: {list(databases.keys())}')
    icon_path = path_to_resource("icon.ico")
    try:
        while True:
            set_default_values()

            for db in databases.values():
                db.open()

            indexing_app = DiskIndexingApp(databases, icon_path)
            indexing_app.iconbitmap(icon_path) # pyright: ignore[reportUnknownMemberType]
            indexing_app.mainloop() # pyright: ignore[reportUnknownMemberType]

            from config import is_should_run_visualizer
            if is_should_run_visualizer:
                visualizer_app = DiskVisualizerApp(databases, icon_path)
                visualizer_app.iconbitmap(icon_path) # pyright: ignore[reportUnknownMemberType]
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
