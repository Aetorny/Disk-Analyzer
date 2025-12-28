from glob import glob
import os

from get_size import SizeFinder
import visualizer
from info import DATA_DIR


def main() -> None:
    size_finder = SizeFinder()
    size_finder.run()

    visualizer.main()

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
