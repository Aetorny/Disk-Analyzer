import os
import gc
import pickle
import logging
import threading
import compression.zstd
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
        self.to_change: dict[str, str] = {}
        self.total = 0
        self.current = 0
        self.is_running = False
        
        # Настройки многопоточности
        self.queue: Queue[str | None] = Queue()
        
        # Блокировки
        self.data_lock = threading.Lock()
        self.size_calc_lock = threading.Lock()

    def _normalize(self, path: str) -> str:
        """Приводит путь к стандартному виду для данной ОС."""
        return os.path.normpath(path)

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
            with os.scandir(path) as it:
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
            if len(files) == 0 and len(subfolders) == 1:
                self.to_change[normalized_current_path] = subfolders[0]
            self.folders[normalized_current_path] = {
                "__files_size__": current_folder_files_size,
                "used_size": current_folder_files_size,
                "subfolders": subfolders,
                "files": files
            }

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

    def _aggregate_sizes(self) -> None:
        """
        Считает полные размеры папок снизу вверх.
        """
        # Сортируем пути по длине строки (от длинных к коротким).
        # Это позволяет гарантированно обработать детей до их родителей.
        sorted_paths = sorted(
            self.folders.keys(), 
            key=len, 
            reverse=True
        )

        for path in sorted_paths:
            if path != '__root__':
                folder_data = self.folders[path]
                
                total_size = folder_data["__files_size__"]
                
                for subpath in folder_data["subfolders"]:
                    if subpath in self.folders:
                        total_size += self.folders[subpath]["used_size"]

                folder_data["used_size"] = total_size
                
                # Удаляем временное поле, чтобы не засорять JSON
                del folder_data["__files_size__"]

    def _collapse_folders(self) -> None:
        '''
        Объединяет папки, которые содержат только 1 подпапку
        И удаляет из данных пустые папки (папки, весящие 0 байт)
        '''
        to_change = set(self.to_change.keys())
        to_remove: set[str] = set()
        
        # Определяем какие папки нужно удалить
        # Изменяем необходимые папки из self.to_change
        for path in self.folders:
            if path != '__root__':
                if self.folders[path]["used_size"] == 0:
                    to_remove.add(path)
                i = 0
                while i < len(self.folders[path]["subfolders"]):
                    subfolder = self.folders[path]["subfolders"][i]
                    if subfolder in to_change:
                        self.folders[path]["subfolders"].remove(subfolder)
                        self.folders[path]["subfolders"].append(self.to_change[subfolder])
                    else:
                        i += 1

        # Удаляем папки весящие 0 байт и объединённые папки
        for path in to_change | to_remove:
            if path in self.folders:
                del self.folders[path]

        # Убираем из списков подпапок все удалённые папки
        for path in self.folders:
            if path != '__root__':
                i = 0
                while i < len(self.folders[path]["subfolders"]):
                    subfolder = self.folders[path]["subfolders"][i]
                    if subfolder in to_remove:
                        self.folders[path]["subfolders"].remove(subfolder)
                    else:
                        i += 1

    def _form_final_data(self) -> dict[str, Any]:
        '''
        Предобрабатывает данные в формат, который использует визуализатор
        '''
        data: dict[str, Any] = {}
        data['__root__'] = self.folders['__root__']['path']
        del self.folders['__root__']

        for path in self.folders.keys():
            path = self._normalize(path)
            data[path] = {
                'subfolders': [],
                'files': [],
                's': self.folders[path]['used_size']
            }
            for subfolder in self.folders[path]['subfolders']:
                if subfolder in self.folders:
                    data[path]['subfolders'].append({
                        'p': subfolder,
                        'n': subfolder[len(path):].lstrip(os.sep) if subfolder.startswith(path) else os.path.basename(subfolder),
                        's': self.folders[subfolder]['used_size']
                    })
            for filename, size in self.folders[path]['files'].items():
                data[path]['files'].append({
                    'p': os.path.join(path, filename),
                    'n': filename,
                    's': size
                })
            data[path]['subfolders'].sort(key=lambda x: x['s'], reverse=True) # type: ignore
            data[path]['files'].sort(key=lambda x: x['s'], reverse=True) # type: ignore

            data[path]['subfolders'] = compression.zstd.compress(pickle.dumps(data[path]['subfolders']))
            data[path]['files'] = compression.zstd.compress(pickle.dumps(data[path]['files']))

        data['__date__'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return data

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
        
        self._aggregate_sizes()

        logging.info(f'Размеры папок подсчитаны. Данные о корне: {self.folders["__root__"]} | {self.folders[self.folders["__root__"]['path']]}')

        self._collapse_folders()

        logging.info(f'Коллапс папок завершён. Получено {len(self.folders)-1} папок')

        data = self._form_final_data()

        logging.info(f'Конечный данные сформированы. Получено {len(data)} папок. Данные о корне: {data["__root__"]} | {data[data["__root__"]]}')
        
        self.database.create_db(data)

        logging.info(f'Сканирование {self.starting_point} завершено. Данные успешно сохранены')
        
        return True
