from glob import glob
import os


from get_size import SizeFinder
import visualizer
from info import DATA_DIR, PLATFORM


def main() -> None:
    size_finder = SizeFinder()
    size_finder.run()

    visualizer.main()

    print('Visualization complete.')
    files = glob('*.html', root_dir=DATA_DIR)
    print('Generated visualization files:')
    for idx, file in enumerate(files):
        print(f'{idx+1}: {os.path.join(DATA_DIR, file)}')
    
    if PLATFORM == 'Windows' and files:
        os.startfile(DATA_DIR)
    input('Press Enter to exit...')


if __name__ == '__main__':
    main()
