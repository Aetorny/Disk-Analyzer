import os
import pickle
import logging
import compression.zstd
from typing import Any
from functools import lru_cache

import numpy as np
import xxhash


class Database:
    def __init__(self, save_path: str):
        self.path = save_path

        self.data_path = save_path + ".npz"
        self.meta_path = save_path + ".meta.pkl"

        self.dtype = np.dtype([
            ('parent_idx', np.int32),
            ('is_dir', np.uint8),
            ('size', np.uint64),
            ('name_idx', np.uint32),
            ('last_descendant_idx', np.uint32)
        ])

        # --- Структуры для фазы СБОРКИ (живут в ОЗУ) ---
        self.node_count: int = 0
        self.unique_names: list[str] = []
        self.unique_names_lower: list[str] = []
        self.name_to_idx: dict[str, int] = {}  # Нужно только при сборке
        self.path_hash_to_idx: dict[int, int] = {}

        # --- Структуры для фазы ЧТЕНИЯ (маппируются с диска) ---
        self._npz_file = None
        self._data: np.ndarray | None = None
        self._names_blob: np.ndarray | None = None
        self._names_offsets: np.ndarray | None = None
        self._names_lower_blob: np.ndarray | None = None
        self._names_lower_offsets: np.ndarray | None = None
        self._paths: np.ndarray | None = None

        self._meta_loaded: bool = False

        self.root_path: str | None = None
        self.last_scan_time: str | None = None
        self.root_display_cache: dict[tuple[str, int, int], Any] | None = None

        self.stop_search_signal = False

    def _ensure_npz_loaded(self):
        """Ленивая подгрузка .npz архива при первом обращении к данным"""
        if self._npz_file is None and os.path.exists(self.data_path):
            self._npz_file = np.load(self.data_path, mmap_mode='r')

    def close(self):
        if self._npz_file is not None:
            self._npz_file.close()
            self._npz_file = None

    @property
    def data(self) -> np.ndarray:
        self._ensure_npz_loaded()
        if self._data is None:
            if self._npz_file is not None:
                self._data = self._npz_file['data']
            else:
                return np.array([], dtype=self.dtype)
        return self._data # pyright: ignore[reportReturnType]

    @property
    def names_blob(self) -> np.ndarray:
        self._ensure_npz_loaded()
        if self._names_blob is None:
            if self._npz_file is not None:
                self._names_blob = self._npz_file['names_blob']
            else:
                return np.array([], dtype=np.uint8)
        return self._names_blob  # pyright: ignore[reportReturnType]

    @property
    def names_offsets(self) -> np.ndarray:
        self._ensure_npz_loaded()
        if self._names_offsets is None:
            if self._npz_file is not None:
                self._names_offsets = self._npz_file['names_offsets']
            else:
                return np.array([0], dtype=np.uint64)
        return self._names_offsets  # pyright: ignore[reportReturnType]

    @property
    def names_lower_blob(self) -> np.ndarray:
        self._ensure_npz_loaded()
        if self._names_lower_blob is None:
            if self._npz_file is not None:
                self._names_lower_blob = self._npz_file['names_lower_blob']
            else:
                return np.array([], dtype=np.uint8)
        return self._names_lower_blob # pyright: ignore[reportReturnType]

    @property
    def names_lower_offsets(self) -> np.ndarray:
        self._ensure_npz_loaded()
        if self._names_lower_offsets is None:
            if self._npz_file is not None:
                self._names_lower_offsets = self._npz_file['names_lower_offsets']
            else:
                return np.array([0], dtype=np.uint64)
        return self._names_lower_offsets  # pyright: ignore[reportReturnType]

    @property
    def paths(self) -> np.ndarray:
        self._ensure_npz_loaded()
        if self._paths is None:
            if self._npz_file is not None:
                self._paths = self._npz_file['paths']
            else:
                return np.array([], dtype=[('hash', np.uint64), ('idx', np.uint32)])
        return self._paths  # pyright: ignore[reportReturnType]

    def ensure_meta_loaded(self):
        """Подгрузка крошечных метаданных"""
        if self._meta_loaded:
            return
        if not os.path.exists(self.meta_path):
            return
        with open(self.meta_path, 'rb') as f:
            meta = pickle.loads(compression.zstd.decompress(f.read()))
        self.node_count = meta['node_count']
        self.root_path = meta['root_path']
        self.last_scan_time = meta['last_scan_time']
        self.root_display_cache = meta['root_display_cache']
        self._meta_loaded = True

    @lru_cache(maxsize=8192)
    def get_name(self, idx: int) -> str:
        """Декодирует строку по её индексу напрямую из маппированного пула строк. Кэширует частые."""
        start = int(self.names_offsets[idx])
        end = int(self.names_offsets[idx + 1])

        # ВАЖНО: end - 1 отрезает нулевой байт-разделитель,
        return self.names_blob[start:end - 1].tobytes().decode('utf-8')

    def _hash_path(self, path: str) -> int:
        return xxhash.xxh64(path).intdigest()

    def _insert_node(self, name: str, is_dir: bool, size: int, parent_idx: int, path_hash: int | None = None) -> int:
        """Быстрая вставка (вызывается только во время сборки в ОЗУ)"""
        idx = self.node_count

        name = name.replace('\0', '')

        if name not in self.name_to_idx:
            self.name_to_idx[name] = len(self.unique_names)
            self.unique_names.append(name)
            self.unique_names_lower.append(name.lower())

        assert self._data is not None, '_data Должен быть заполнен'

        self._data[idx]['parent_idx'] = parent_idx
        self._data[idx]['is_dir'] = 1 if is_dir else 0
        self._data[idx]['size'] = size
        self._data[idx]['name_idx'] = self.name_to_idx[name]

        if path_hash is not None:
            self.path_hash_to_idx[path_hash] = idx

        self.node_count += 1
        return idx

    def build_from_dict(self, folders_dict: dict[str, Any], root_path: str, total_items: int):
        self._data = np.zeros(total_items, dtype=self.dtype)
        self.node_count = 0

        stack = [("ENTER", root_path, -1, -1)]
        folder_sizes = {}

        while stack:
            action, path, parent_idx, my_idx = stack.pop()

            if action == "ENTER":
                folder_data = folders_dict.get(path)
                if not folder_data:
                    continue

                my_idx = self._insert_node(
                    name=folder_data["name"],
                    is_dir=True,
                    size=0,
                    parent_idx=parent_idx,
                    path_hash=self._hash_path(path)
                )

                folder_sizes[my_idx] = 0

                for file_name, file_size in folder_data["files"].items():
                    self._insert_node(
                        name=file_name,
                        is_dir=False,
                        size=file_size,
                        parent_idx=my_idx
                    )
                    folder_sizes[my_idx] += file_size

                stack.append(("EXIT", path, parent_idx, my_idx))

                for sub_path in reversed(folder_data.get("subfolders", [])):
                    stack.append(("ENTER", sub_path, my_idx, -1))

            elif action == "EXIT":
                self._data[my_idx]['last_descendant_idx'] = self.node_count - 1
                self._data[my_idx]['size'] = folder_sizes[my_idx]

                if parent_idx != -1:
                    folder_sizes[parent_idx] += folder_sizes[my_idx]

                del folder_sizes[my_idx]

        self._data = self._data[:self.node_count]

    def save_metadata(self, root_path: str, current_time: str) -> None:
        self.root_path = root_path
        self.last_scan_time = current_time

    @staticmethod
    def _build_string_pool(names: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """Превращает список строк в байтовый пул и массив смещений для сохранения на диск"""
        if not names:
            return np.array([], dtype=np.uint8), np.array([0], dtype=np.uint64)

        encoded = [n.encode('utf-8') for n in names]
        blob = b'\0'.join(encoded) + b'\0'
        offsets = np.zeros(len(encoded) + 1, dtype=np.uint64)
        curr = 0
        for i, enc in enumerate(encoded):
            offsets[i] = curr
            curr += len(enc) + 1

        return np.frombuffer(blob, dtype=np.uint8), offsets

    def save_metadata_to_disk(self):
        meta = {
            'node_count': self.node_count,
            'root_path': self.root_path,
            'last_scan_time': self.last_scan_time,
            'root_display_cache': self.root_display_cache
        }
        with open(self.meta_path, 'wb') as f:
            f.write(compression.zstd.compress(pickle.dumps(
                meta, protocol=pickle.HIGHEST_PROTOCOL)))

    def save_to_disk(self):
        # 1. Компилируем строковые пулы
        names_blob, names_offsets = self._build_string_pool(self.unique_names)
        names_lower_blob, names_lower_offsets = self._build_string_pool(
            self.unique_names_lower)

        # 2. Компилируем словарь путей в отсортированный массив для бинарного поиска
        paths_dtype = np.dtype([('hash', np.uint64), ('idx', np.uint32)])
        if self.path_hash_to_idx:
            paths_arr = np.array(
                list(self.path_hash_to_idx.items()), dtype=paths_dtype)
            paths_arr.sort(order='hash')
        else:
            paths_arr = np.array([], dtype=paths_dtype)

        assert self._data is not None, '_data Должен быть заполнен'

        # 3. Сохраняем всё в один .npz архив
        np.savez_compressed(
            self.data_path,
            data=self._data,
            names_blob=names_blob,
            names_offsets=names_offsets,
            names_lower_blob=names_lower_blob,
            names_lower_offsets=names_lower_offsets,
            paths=paths_arr
        )

        # 4. Сохраняем крошечные метаданные
        meta = {
            'node_count': self.node_count,
            'root_path': self.root_path,
            'last_scan_time': self.last_scan_time,
            'root_display_cache': self.root_display_cache
        }
        with open(self.meta_path, 'wb') as f:
            f.write(compression.zstd.compress(pickle.dumps(meta, protocol=pickle.HIGHEST_PROTOCOL)))

        # 5. Очищаем структуры сборки, освобождая ОЗУ
        self.unique_names.clear()
        self.unique_names_lower.clear()
        self.name_to_idx.clear()
        self.path_hash_to_idx.clear()
        self.get_name.cache_clear()

        # Сбрасываем ленивые состояния, чтобы следующие запросы шли через диск
        if self._npz_file is not None:
            self._npz_file.close()
        self._npz_file = None
        self._data = None
        self._names_blob = None
        self._names_offsets = None
        self._names_lower_blob = None
        self._names_lower_offsets = None
        self._paths = None
        self._meta_loaded = False

    @classmethod
    def load_from_disk(cls, filepath: str) -> 'Database':
        return cls(filepath)

    def stop_search(self) -> None:
        self.stop_search_signal = True

    def search_by_name(self, search_str: str) -> set[int]:
        self.stop_search_signal = False
        search_bytes = search_str.lower().encode('utf-8')
        blob = self.names_lower_blob
        offsets = self.names_lower_offsets

        if len(blob) == 0:
            return set()

        blob_bytes = blob.tobytes()
        matching_name_indices: set[int] = set()
        idx = 0

        while True:
            if self.stop_search_signal:
                return set()
            idx = blob_bytes.find(search_bytes, idx)
            if idx == -1:
                break
            # Конвертируем байтовый индекс обратно в индекс строки через бинарный поиск по смещениям
            string_idx = int(np.searchsorted(offsets, idx, side='right') - 1)
            matching_name_indices.add(string_idx)
            idx += 1

        if not matching_name_indices:
            return set()

        active_data = self.data[:self.node_count]
        mask = np.isin(active_data['name_idx'], list(matching_name_indices))
        matching_indices = np.nonzero(mask)[0]

        result_set: set[int] = set()

        for idx in matching_indices:
            current = int(idx)
            while current != -1:
                if current in result_set:
                    break
                result_set.add(current)
                current = int(self.data[current]['parent_idx'])

        return result_set

    def get_ancestors(self, node_idx: int) -> list[str]:
        if self.data[node_idx]['parent_idx'] == -1:
            return []

        ancestors: list[str] = []
        current_idx = node_idx

        while True:
            parent_idx = self.data[current_idx]['parent_idx']
            if parent_idx == -1:
                break

            name_idx = self.data[parent_idx]['name_idx']
            ancestors.append(self.get_name(int(name_idx)))

            current_idx = parent_idx

        return ancestors[::-1]

    def get_root_size(self) -> int:
        if self.node_count == 0:
            return 0
        return int(self.data[0]['size'])

    def get_index(self, path: str) -> int:
        path_hash = self._hash_path(path)
        paths = self.paths
        if len(paths) == 0:
            return -1

        # Бинарный поиск по отсортированному дисковому массиву
        idx = np.searchsorted(paths['hash'], path_hash)
        if idx < len(paths) and paths[idx]['hash'] == path_hash:
            return int(paths[idx]['idx'])
        return -1

    def get_parent_index(self, path: str) -> int:
        path_hash = self._hash_path(path)
        paths = self.paths
        if len(paths) == 0:
            return -1

        idx = np.searchsorted(paths['hash'], path_hash)
        if idx < len(paths) and paths[idx]['hash'] == path_hash:
            node_idx = int(paths[idx]['idx'])
            return int(self.data[node_idx]['parent_idx'])
        return -1

    def has_parent(self, path: str) -> bool:
        parent_idx = self.get_parent_index(path)
        return parent_idx != -1

    @lru_cache(maxsize=2**16)
    def get_full_path(self, node_idx: int) -> str:
        if self.root_path is None:
            raise ValueError("Root path не задан")

        if node_idx == 0:
            return self.root_path + os.sep

        parts: list[str] = []
        current = node_idx

        while current != -1:
            name_idx: int = int(self.data[current]['name_idx'])
            parts.append(self.get_name(name_idx) + os.sep)
            current = int(self.data[current]['parent_idx'])

        if len(parts) == 0:
            return self.root_path + os.sep

        parts.reverse()

        return os.path.join(*parts)

    def get_folder_contents(self, folder_idx: int, allowed_indices: set[int] | None = None, is_need_files: bool = False) -> dict[str, Any]:
        node = self.data[folder_idx]
        if node['is_dir'] == 0:
            logging.error(
                f"Путь по индексу {folder_idx} является файлом, а не папкой")
            raise ValueError(
                f"Путь по индексу {folder_idx} является файлом, а не папкой")

        end_idx = node['last_descendant_idx']
        if folder_idx+1 > end_idx:
            return {"folders": [], "files": [], "total_files_size": 0, "total_folders_size": 0}

        subtree_parents = self.data['parent_idx'][folder_idx+1: end_idx + 1]
        relative_indices = np.nonzero(subtree_parents == folder_idx)[0]
        direct_indexes = folder_idx+1 + relative_indices

        if allowed_indices is not None:
            mask = np.isin(direct_indexes, list(allowed_indices))
            direct_indexes = direct_indexes[mask]

        if len(direct_indexes) == 0:
            return {"folders": [], "files": [], "total_files_size": 0, "total_folders_size": 0}

        direct_children = self.data[direct_indexes]

        files_mask = (direct_children['is_dir'] == 0)
        folders_mask = (direct_children['is_dir'] == 1)

        files_data = direct_children[files_mask]
        folders_data = direct_children[folders_mask]
        folders_indexes = direct_indexes[folders_mask]

        current_folder = self.get_full_path(folder_idx)
        if not current_folder.endswith(os.sep):
            current_folder += os.sep

        name_indices = folders_data['name_idx']
        # Используем кэшированный get_name вместо self.unique_names
        names = [self.get_name(int(idx)) for idx in name_indices]

        folders_list: list[dict[str, Any]] = [
            {
                "name": names[i],
                "path": current_folder + names[i],
                "size": int(folders_data[i]['size']),
                "index": int(folders_indexes[i])
            } for i in range(len(folders_data))
        ]
        folders_list.sort(key=lambda x: x['size'], reverse=True)

        files_list: list[dict[str, Any]] = []
        if is_need_files:
            for i in range(len(files_data)):
                name = self.get_name(int(files_data[i]['name_idx']))
                files_list.append({
                    "name": name,
                    "path": current_folder + name,
                    "size": int(files_data[i]['size']),
                })
            files_list.sort(key=lambda x: x['size'], reverse=True)

        return {
            "folders": folders_list,
            "files": files_list,
            "total_files_size": int(np.sum(files_data['size']) if len(files_data) > 0 else 0),
            "total_folders_size": int(np.sum(folders_data['size']) if len(folders_data) > 0 else 0)
        }
