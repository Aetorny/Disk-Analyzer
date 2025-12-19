from get_size import SizeFinder
import visualizer


def main() -> None:
    size_finder = SizeFinder()
    size_finder.run()

    visualizer.main()


if __name__ == '__main__':
    main()
