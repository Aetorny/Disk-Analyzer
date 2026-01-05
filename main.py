from ui import DiskVisualizerApp, DiskIndexingApp
from utils import load_all_databases


def main() -> None:
    databases = load_all_databases()
    try:
        for db in databases.values():
            db.open()

        indexing_app = DiskIndexingApp(databases)
        indexing_app.mainloop() # pyright: ignore[reportUnknownMemberType]

        from config import is_should_run_visualizer
        if is_should_run_visualizer:
            visualizer_app = DiskVisualizerApp(databases)
            visualizer_app.mainloop() # pyright: ignore[reportUnknownMemberType]
    finally:
        for db in databases.values():
            db.close()


if __name__ == '__main__':
    main()
