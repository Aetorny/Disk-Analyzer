from get_size import SizeFinder
from disk_info import get_start_directories
from choose_disk_ui import choose_disk
from visualizer import DiskTreemapApp


def main() -> None:
    disks = get_start_directories()
    if len(disks) > 1:
        disks = choose_disk(disks)
    if len(disks) == 0:
        return print('Вы не выбрали никакого диска.')

    for disk in disks:
        size_finder = SizeFinder([disk])
        size_finder.run()

    app = DiskTreemapApp()
    app.mainloop() # pyright: ignore[reportUnknownMemberType]


if __name__ == '__main__':
    main()
