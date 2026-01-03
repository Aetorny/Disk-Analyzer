from __future__ import annotations
from tqdm import tqdm

import os
import gc
import pickle
import logging
import threading
import compression.zstd
from queue import Queue
from typing import Optional, Any

from config import CURRENT_DIR, DATA_DIR, IGNORE_PATHS
from logic import get_start_directories, get_used_disk_size


class SizeFinder:
    def __init__(self, paths: Optional[list[str]] = None, num_threads: Optional[int] = None) -> None:
        self.starting_points = get_start_directories() if paths is None else paths
        logging.info(f'Директории для обхода: {self.starting_points}')
        
        if num_threads:
            self.num_threads = num_threads
        else:
            cpu_count = os.cpu_count() or 1
            
            self.num_threads = min(32, cpu_count * 4)

        logging.info(f"Количество используемых потоков: {self.num_threads}")

        # Основное хранилище данных
        self.folders: dict[str, dict[str, Any]] = {}
        self.to_change: dict[str, str] = {}
        
        # Настройки многопоточности
        self.queue: Queue[str | None] = Queue()
        
        # Блокировки
        self.data_lock = threading.Lock()
        self.pbar_lock = threading.Lock()

    def _normalize(self, path: str) -> str:
        """Приводит путь к стандартному виду для данной ОС."""
        return os.path.normpath(path)

    def _process_directory(self, path: str, pbar: Optional[tqdm[Any]]) -> None:
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
                    try:
                        # Обработка директорий
                        if entry.is_dir(follow_symlinks=False):
                            if entry.is_symlink() or os.path.ismount(entry.path):
                                continue
                            
                            # Проверка игнорируемых путей
                            if entry.path.rstrip('/\\') in IGNORE_PATHS:
                                continue

                            # Важно: нормализуем путь подпапки перед добавлением
                            child_path = self._normalize(entry.path)
                            subfolders.append(child_path)
                            self.queue.put(child_path)

                        # Обработка файлов
                        elif entry.is_file(follow_symlinks=False):
                            # st_size дает реальный размер в байтах
                            file_size = entry.stat(follow_symlinks=False).st_size
                            current_folder_files_size += file_size
                            files[entry.name] = file_size
                    
                    except PermissionError:
                        logging.warning(f"Недостаточно прав доступа: {entry.path}")
                        continue
                    except Exception as e:
                        logging.error(f"Ошибка при сканировании {entry.path}: {e}")
                        with self.pbar_lock:
                            if pbar: pbar.write(f"Ошибка при сканировании {entry.path}: {e}")
                        continue

        except PermissionError:
            logging.warning(f"Недостаточно прав доступа: {path}")
            with self.pbar_lock:
                if pbar: pbar.write(f"Недостаточно прав доступа: {path}")
        except Exception as e:
            logging.error(f"Ошибка при сканировании {path}: {e}")
            with self.pbar_lock:
                if pbar: pbar.write(f"Ошибка при сканировании {path}: {e}")

        # Обновляем прогресс-бар
        if pbar and current_folder_files_size > 0:
            with self.pbar_lock:
                pbar.update(current_folder_files_size)

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

    def _worker(self, pbar: Optional[tqdm[Any]]) -> None:
        """Поток-обработчик."""
        while True:
            path = self.queue.get()
            if path is None: # Сигнал остановки
                self.queue.task_done()
                break
            
            self._process_directory(path, pbar)
            self.queue.task_done()

    def _aggregate_sizes(self) -> None:
        """
        Считает полные размеры папок снизу вверх.
        """
        print("Aggregating folder sizes...")

        # Сортируем пути по длине строки (от длинных к коротким).
        # Самые длинные пути — это самые глубокие папки.
        # Мы гарантированно обработаем детей до их родителей.
        sorted_paths = sorted(
            self.folders.keys(), 
            key=len, 
            reverse=True
        )

        for path in tqdm(sorted_paths, desc="Calculating totals", unit="dir"):
            if path == '__root__':
                continue
            folder_data = self.folders[path]
            
            total_size = folder_data["__files_size__"]
            
            for subpath in folder_data["subfolders"]:
                # Ищем подпапку в уже обработанных данных
                if subpath in self.folders:
                    total_size += self.folders[subpath]["used_size"]
                else:
                    # Если подпапки нет в ключах (например, ошибка доступа при сканировании),
                    # мы просто игнорируем её размер, так как он равен 0 или неизвестен.
                    pass

            folder_data["used_size"] = total_size
            
            # Удаляем временное поле, чтобы не засорять JSON
            del folder_data["__files_size__"]

    def _collapse_folders(self) -> None:
        '''
        Объединяет папки, которые содержат только 1 подпапку
        И удаляет из данных пустые папки (папки, весящие 0 байт)
        '''
        to_change = set(sorted(self.to_change))
        to_remove: set[str] = set()
        for path in self.folders:
            if path == '__root__':
                continue
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
        for path in to_change | to_remove:
            if path in self.folders:
                del self.folders[path]
        for path in self.folders:
            if path == '__root__':
                continue
            i = 0
            while i < len(self.folders[path]["subfolders"]):
                subfolder = self.folders[path]["subfolders"][i]
                if subfolder in to_remove:
                    self.folders[path]["subfolders"].remove(subfolder)
                else:
                    i += 1

    def _form_final_data(self) -> dict[str, dict[str, Any]]:
        '''
        Предобрабатывает данные в формат, который использует визуализатор
        '''
        data: dict[str, dict[str, Any]] = {}
        subfolders: set[str] = set()
        for path in self.folders:
            if path == '__root__':
                continue
            data[path] = {
                'childrens': [],
                'used_size': self.folders[path]['used_size'],
            }
            for subfolder in self.folders[path]['subfolders']:
                subfolders.add(subfolder)
                data[path]['childrens'].append({
                    'path': subfolder,
                    'size': self.folders[subfolder]['used_size'],
                    'is_file': False,
                    'name': subfolder[len(path):].lstrip(os.sep) if subfolder.startswith(path) else os.path.basename(subfolder),
                })
            for filename, size in self.folders[path]['files'].items():
                data[path]['childrens'].append({
                    'path': os.path.join(path, filename),
                    'size': size,
                    'is_file': True,
                    'name': filename,
                })
            data[path]['childrens'].sort(key=lambda x: x['size'], reverse=True) # type: ignore
            childrens = compression.zstd.compress(pickle.dumps(data[path]['childrens']))
            data[path]['childrens'] = childrens
        data['__root__'] = self.folders['__root__']
        return data

    def run(self) -> None:
        for start in self.starting_points:
            logging.info(f'Начало сканирования {start}')
            # Получаем общий размер диска для прогресс-бара (для красоты)
            disk_usage_total = get_used_disk_size(start)
            print(f"Сканирование: {start} (~ {disk_usage_total / (1024 ** 3):.2f} GB использовано)")

            self.folders = {
                '__root__': {'path': self._normalize(start)}
            }
            self.queue = Queue()
            
            # Добавляем начальную точку (нормализованную)
            self.queue.put(self._normalize(start))

            gc.disable() # Отключаем GC для скорости при создании миллионов объектов

            with tqdm(total=disk_usage_total, unit='B', unit_scale=True, unit_divisor=1024, desc="Сканирование") as pbar:
                threads: list[threading.Thread] = []
                # Запуск потоков
                for _ in range(self.num_threads):
                    t = threading.Thread(target=self._worker, args=(pbar,))
                    t.start()
                    threads.append(t)

                # Блокируем главный поток, пока очередь не опустеет
                self.queue.join()

                # Останавливаем потоки
                for _ in range(self.num_threads):
                    self.queue.put(None)
                for t in threads:
                    t.join()

            logging.info(f'Сканирование {start} завершено. Получено {len(self.folders)-1} папок. Данные о корне: {self.folders["__root__"]} | {self.folders[self.folders["__root__"]['path']]}')
            
            self._aggregate_sizes()

            logging.info(f'Размеры папок подсчитаны. Данные о корне: {self.folders["__root__"]} | {self.folders[self.folders["__root__"]['path']]}')

            self._collapse_folders()

            logging.info(f'Коллапс папок завершён. Получено {len(self.folders)-1} папок')

            data = self._form_final_data()

            logging.info(f'Конечный данные сформированы. Получено {len(self.folders)-1} папок. Данные о корне: {self.folders["__root__"]} | {self.folders[self.folders["__root__"]['path']]}')
            
            gc.enable()

            # Формирование имени файла и сохранение
            safe_name = start.replace(':', '').replace('/', '_').replace('\\', '_').strip('_')
            filename = f"disk_{safe_name}_usage.data"
            output_path = os.path.join(CURRENT_DIR, DATA_DIR, filename)

            # Создаем папку data, если её нет
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            logging.info(f"Сжатие данных...")
            compr = compression.zstd.compress(pickle.dumps(data), level=3)
            logging.info(f"Сохранение {output_path}...")
            try:
                with open(output_path, 'wb') as f:
                    f.write(compr)
            except Exception as e:
                logging.error(f"Не удалось сохранить данные в {output_path}. Ошибка {e}")
                continue

            logging.info(f'Сканирование {start} завершено. Данные успешно сохранены')
        
        logging.info(f'Все сканирования завершены')


if __name__ == "__main__":
    finder = SizeFinder()
    finder.run()
