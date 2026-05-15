import os
import gc
import logging
import threading
from datetime import datetime
from queue import Queue, ShutDown
from typing import Optional, Any

from config import IGNORE_PATHS
from logic import Database, get_used_disk_size, is_root


class SizeFinder:
    def __init__(self, database: Database, path: str, num_threads: Optional[int] = None) -> None:
        self.database = database
        self.starting_point = path
        logging.info(f'Директория для обхода: {self.starting_point}')

        if num_threads:
            self.num_threads = num_threads
        else:
            cpu_count = os.cpu_count() or 1
            
            self.num_threads = min(32, cpu_count * 4)

        logging.info(f"Количество используемых потоков: {self.num_threads}")

        # Основное хранилище данных
        self.folders: dict[str, dict[str, Any]] = {}
        self.total_elements = 0
        self.total = 0
        self.current = 0
        self.current_task: Optional[str] = None
        self.is_running = False
        
        # Настройки многопоточности
        self.queue: Queue[str | None] = Queue()
        
        # Блокировки
        self.data_lock = threading.Lock()
        self.size_calc_lock = threading.Lock()

    def _normalize(self, path: str) -> str:
        """Приводит путь к стандартному виду для данной ОС."""
        return os.path.normpath(path).strip(os.sep)

    def _is_directory_skip(self, entry: os.DirEntry[str]) -> bool:
        """
        Проверяет, нужно ли пропустить директорию.
        Пропускает директории, если выполняется одно из условий:
        - Это символическая ссылка
        - Это точка монтирования
        - Путь находится в списке игнорируемых путей
        """
        # Проверка символической ссылки
        if entry.is_symlink():
            return True
        
        # Проверка точки монтирования
        if os.path.ismount(entry.path):
            return True

        # Проверка игнорируемых путей
        if entry.path.rstrip('/\\') in IGNORE_PATHS:
            return True

        return False

    def _process_directory(self, path: str) -> None:
        """
        Сканирует одну директорию, считает файлы и собирает пути к подпапкам.
        """
        subfolders: list[str] = []
        files: dict[str, int] = {}
        current_folder_files_size = 0
        
        # Нормализуем текущий путь, чтобы он совпадал с ключом в self.folders
        normalized_current_path = self._normalize(path)

        try:
            with os.scandir(path+os.sep) as it:
                for entry in it:
                    if not self.is_running:
                        return

                    # Обработка директорий
                    if entry.is_dir(follow_symlinks=False) and not self._is_directory_skip(entry):
                        normalized_path = self._normalize(entry.path)
                        subfolders.append(normalized_path)
                        self.queue.put(normalized_path)

                    # Обработка файлов
                    elif entry.is_file(follow_symlinks=False):
                        # st_size дает реальный размер в байтах
                        file_size = entry.stat(follow_symlinks=False).st_size
                        current_folder_files_size += file_size
                        files[entry.name] = file_size
        except PermissionError:
            logging.warning(f'Недостаточно прав для доступа {path}')
            return
        except Exception as e:
            logging.error(f'Ошибка при сканировании {path}: {e}', exc_info=True)
            return

        # Обновляем прогресс-бар
        if current_folder_files_size > 0:
            with self.size_calc_lock:
                self.current += current_folder_files_size

        # Записываем результаты в общий словарь под блокировкой
        with self.data_lock:
            self.folders[normalized_current_path] = {
                "subfolders": subfolders,
                "files": files,
                "name": os.path.basename(normalized_current_path) or normalized_current_path,
            }
            self.total_elements += len(files) + 1

    def _worker(self) -> None:
        """Поток-обработчик."""
        while True:
            if not self.is_running:
                self.queue.shutdown(immediate=True)
                break
            try:
                path = self.queue.get()
            except ShutDown:
                break
            if path is None: # Сигнал остановки
                self.queue.task_done()
                break
            
            self._process_directory(path)
            self.queue.task_done()

    def _form_final_data(self) -> None:
        '''
        Преобразует полученные данные в используемую базу данных
        '''
        root: str = self.folders['__root__']['path']
        del self.folders['__root__']
        self.database.build_from_dict(
            self.folders,
            root,
            self.total_elements
        )
        self.database.save_metadata(
            root,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        self.folders.clear()
        del self.folders

    def run(self) -> bool:
        self.is_running = True
        logging.info(f'Начало сканирования {self.starting_point}')
        if not is_root(self.starting_point):
            # Если текущая директория не корень системы, то определить заранее размер нельзя
            total_usage = 0
        else:
            # Получаем общий размер диска для прогресс-бара в UI
            total_usage = get_used_disk_size(self.starting_point)

        self.folders = {
            '__root__': {'path': self._normalize(self.starting_point)}
        }
        self.queue = Queue()
        
        # Добавляем начальную точку (нормализованную)
        self.queue.put(self._normalize(self.starting_point))

        self.total = total_usage
        self.current = 0
        self.current_task = 'Scanning'

        gc.disable() # Отключаем GC для скорости при создании миллионов объектов

        threads: list[threading.Thread] = []
        # Запуск потоков
        for _ in range(self.num_threads):
            t = threading.Thread(target=self._worker)
            t.start()
            threads.append(t)

        # Блокируем главный поток, пока очередь не опустеет
        self.queue.join()

        # Останавливаем потоки
        for _ in range(self.num_threads):
            self.queue.put(None)
        for t in threads:
            t.join()

        gc.enable()

        if not self.is_running:
            logging.info('Сканирование прервано')
            return False

        logging.info(f'Сканирование {self.starting_point} завершено. Получено {len(self.folders)-1} папок. Данные о корне: {self.folders["__root__"]} | {self.folders[self.folders["__root__"]['path']]}')

        self.current_task = 'Formating data'

        self._form_final_data()

        self.database.save_to_disk()

        logging.info(f'Сканирование {self.starting_point} завершено. Данные успешно сохранены')

        gc.collect()
        
        return True
