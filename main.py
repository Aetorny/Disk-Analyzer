from logic import SizeFinder, get_start_directories
from ui import choose_disk, DiskTreemapApp


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
