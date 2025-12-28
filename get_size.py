from __future__ import annotations
from tqdm import tqdm

import os
import gc
import json
import threading
from queue import Queue
from typing import Optional, Any

from info import CURRENT_DIR, DATA_DIR, IGNORE_PATHS
from disk_info import get_start_directories, get_used_disk_size


class SizeFinder:
    def __init__(self, paths: Optional[list[str]] = None, num_threads: Optional[int] = None) -> None:
        self.starting_points = get_start_directories() if paths is None else paths
        
        if num_threads:
            self.num_threads = num_threads
        else:
            cpu_count = os.cpu_count() or 1
            
            self.num_threads = min(32, cpu_count * 4)

        print(f"Количество используемых потоков: {self.num_threads}")

        # Основное хранилище данных
        self.folders: dict[str, dict[str, Any]] = {}
        
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
                    
                    except PermissionError:
                        continue # Пропускаем файлы/папки без прав доступа
                    except Exception as e:
                        with self.pbar_lock:
                            if pbar: pbar.write(f"Ошибка при сканировании {entry.path}: {e}")
                        continue

        except PermissionError:
            with self.pbar_lock:
                if pbar: pbar.write(f"Недостаточно прав доступа: {path}")
        except Exception as e:
            with self.pbar_lock:
                if pbar: pbar.write(f"Ошибка при сканировании {path}: {e}")

        # Обновляем прогресс-бар
        if pbar and current_folder_files_size > 0:
            with self.pbar_lock:
                pbar.update(current_folder_files_size)

        # Записываем результаты в общий словарь под блокировкой
        with self.data_lock:
            self.folders[normalized_current_path] = {
                # Сохраняем "чистый" размер файлов отдельно для этапа агрегации
                "__files_size__": current_folder_files_size,
                "used_size": current_folder_files_size,
                "subfolders": subfolders
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

    def run(self) -> None:
        for start in self.starting_points:
            # Получаем общий размер диска для прогресс-бара (для красоты)
            try:
                disk_usage_total = get_used_disk_size(start)
                print(f"Сканирование: {start} (~ {disk_usage_total / (1024 ** 3):.2f} GB использовано)")
            except:
                disk_usage_total = 0
                print(f"Сканирование: {start}")

            self.folders = {}
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

            # Этап суммирования размеров
            self._aggregate_sizes()
            
            gc.enable()

            # Формирование имени файла и сохранение
            safe_name = start.replace(':', '').replace('/', '_').replace('\\', '_').strip('_')
            filename = f"disk_usage_{safe_name}.json"
            output_path = os.path.join(CURRENT_DIR, DATA_DIR, filename)
            
            # Создаем папку data, если её нет
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            print(f"Сохранение {output_path}...")
            with open(output_path, "w", encoding='utf-8') as f:
                json.dump(self.folders, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    finder = SizeFinder()
    finder.run()