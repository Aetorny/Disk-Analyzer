from glob import glob
import os
import webbrowser

from get_size import SizeFinder
from info import DATA_DIR
from disk_info import get_start_directories
from choose_disk_ui import choose_disk
import visualizer


def main() -> None:
    disks = get_start_directories()
    if len(disks) > 1:
        disks = choose_disk(disks)
    if len(disks) == 0:
        return print('Вы не выбрали никакого диска.')

    for disk in disks:
        size_finder = SizeFinder([disk])
        size_finder.run()

        visualizer.main(disk.replace('\\', '').replace('/', '').replace(':', ''))

    print('Визуализация завершена.')
    files = glob('*.html', root_dir=DATA_DIR)
    print('Сгенерированные файлы:')
    idx = 1
    for file in files:
        if file.endswith('.html'):
            print(f'\t{idx}: {os.path.join(DATA_DIR, file)}')
            idx += 1
    
    input('Нажмите Enter для открытия сгенерированных файлов...')

    for file in files:
        webbrowser.open(os.path.join(DATA_DIR, file))


if __name__ == '__main__':
    main()
