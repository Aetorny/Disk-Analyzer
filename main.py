from glob import glob
import os

from get_size import SizeFinder
import visualizer


def main() -> None:
    size_finder = SizeFinder()
    size_finder.run()

    visualizer.main()

    print('Visualization complete.')
    files = glob('*.html', root_dir=visualizer.DATA_DIR)
    print('Generated visualization files:')
    for idx, file in enumerate(files):
        print(f'{idx+1}: {os.path.join(visualizer.DATA_DIR, file)}')

if __name__ == '__main__':
    main()
