from glob import glob
import os

from get_size import SizeFinder
from info import DATA_DIR
from disk_info import get_start_directories
import visualizer


def main() -> None:
    disks = get_start_directories()
    for disk in disks:
        size_finder = SizeFinder([disk])
        size_finder.run()

        visualizer.main(disk.replace('\\', '').replace('/', '').replace(':', ''))

    print('Визуализация завершена.')
    files = glob('*.html', root_dir=DATA_DIR)
    print('Сгенерированные файлы:')
    for idx, file in enumerate(files):
        print(f'\t{idx+1}: {os.path.join(DATA_DIR, file)}')
    
    input('Нажмите Enter для открытия сгенерированных файлов...')

    for file in files:
        os.startfile(os.path.join(DATA_DIR, file))


if __name__ == '__main__':
    main()
