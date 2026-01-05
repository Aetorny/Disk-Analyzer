import os
import struct
import marshal
from typing import Any


class Database:
    def __init__(self, path: str):
        self.path = path
        self.is_open = False

    def __del__(self):
        if self.is_open:
            self.close()

    def __iter__(self):
        return iter(self.index)

    def __contains__(self, key: str):
        return key in self.index

    def __getitem__(self, key: str):
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def get(self, key: str):
        """
        Мгновенное чтение
        """
        try:
            offset, length = self.index[key]
        except KeyError:
            return None
            
        self.f.seek(offset)
        raw_data = self.f.read(length)
        return marshal.loads(raw_data)

    def create_db(self, source_dict: dict[str, Any], open_after: bool = True):
        """
        source_dict: Словарь данных для загрузки в бд.
        open_after: Открывать ли после загрузки
        """
        if self.is_open:
            self.close()
        try:
            offset = 0
            index: dict[str, tuple[int, int]] = {}  # {ключ: (смещение, длина)}
            
            with open(self.path, 'wb') as f:
                for key, value in source_dict.items():
                    # 1. Сериализуем данные в бинарный формат (marshal самый быстрый)
                    data_bytes = marshal.dumps(value)
                    length = len(data_bytes)
                    
                    # 2. Пишем данные
                    f.write(data_bytes)
                    
                    # 3. Запоминаем, где они лежат
                    index[key] = (offset, length)
                    offset += length
                    
                # 4. В конце файла пишем сам индекс
                index_bytes = marshal.dumps(index)
                start_of_index = f.tell()
                f.write(index_bytes)
                
                # 5. В последние 8 байт пишем, где начинается индекс
                # <Q означает unsigned long long (8 байт)
                f.write(struct.pack('<Q', start_of_index))
        finally:
            if open_after:
                self.open()

    def open(self):
        '''
        Открытие бд
        '''
        if self.is_open:
            return
        if not os.path.exists(self.path):
            return
        self.f = open(self.path, 'rb')
        self.is_open = True
        
        # 1. Читаем последние 8 байт, чтобы найти начало индекса
        self.f.seek(-8, 2) # 2 = конец файла
        index_offset = struct.unpack('<Q', self.f.read(8))[0]
        
        # 2. Читаем и загружаем индекс в память
        self.f.seek(index_offset)
        raw_index = self.f.read()
        
        # Это словарь {key: (offset, length)}
        self.index = marshal.loads(raw_index) 

    def close(self):
        if not self.is_open:
            return
        self.f.close()
        self.is_open = False
