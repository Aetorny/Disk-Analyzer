from ui import DiskVisualizerApp, DiskIndexingApp


def main() -> None:
    indexing_app = DiskIndexingApp()
    indexing_app.mainloop() # pyright: ignore[reportUnknownMemberType]

    visualizer_app = DiskVisualizerApp()
    visualizer_app.mainloop() # pyright: ignore[reportUnknownMemberType]


if __name__ == '__main__':
    main()