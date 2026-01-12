import os
import json
import logging
from typing import Any

VERSION = '1.7.4'

REQUIRED_SETTINGS = [
    'version',
    'is_first_run',
    'language',
    'appearence_mode',
    'color_map'
]


class Settings:
    def __init__(self, settings_path: str) -> None:
        logging.info(f'Загрузка конфигурационного файла: {settings_path}')
        self.path = settings_path
        self.data: dict[str, Any] = {}
        if os.path.exists(self.path):
            logging.info(f'Конфигурационный файл обнаружен, загрузка...')
            try:
                with open(self.path, 'r') as f:
                    self.data = json.load(f)
                self._check_data()
            except Exception as e:
                logging.error(f'Ошибка при загрузке конфигурационного файла: {e}')
                return self._generate_default_settings()

            logging.info(f'Конфигурационный файл успешно загружен.')
        else:
            self._generate_default_settings()

    def _check_data(self) -> None:
        for setting in REQUIRED_SETTINGS:
            if setting not in self.data:
                self._generate_default_settings()
                return

        if self.data['version'] != VERSION:
            self.data['is_first_run'] = True

    def _generate_default_settings(self) -> None:
        logging.info('Создание стандартного конфигурационного файла...')
        self.data = {
            'version': VERSION,
            'is_first_run': True,
            "language": {
                "current": "en",
                "available": ["en", "ru"]
            },
            'appearence_mode': {
                'current': 'dark',
                'available': ['light', 'dark']
            },
            'color_map': {
                'current': 'turbo',
                'available': [
                    "Blues",
                    "BuPu",
                    "CMRmap",
                    "Grays",
                    "Greens",
                    "Oranges",
                    "Purples",
                    "RdBu",
                    "RdGy",
                    "Spectral",
                    "autumn",
                    "jet",
                    "turbo"
                ]
            }
        }
        self.save()
        logging.info('Стандартный конфигурационный файл создан.')

    def save(self) -> None:
        logging.info('Сохранение конфигурационного файла...')
        try:
            with open(self.path, 'w') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f'Ошибка при сохранении конфигурационного файла: {e}')
            return

        logging.info('Конфигурационный файл успешно сохранен.')

    def __getitem__(self, name: str) -> Any:
        return self.data[name]

    def __setitem__(self, name: str, value: Any) -> None:
        self.data[name] = value

    def __delattr__(self, name: str) -> None:
        del self.data[name]

    def get(self, name: str, default: Any = None) -> Any:
        if name in self.data:
            return self.data[name]
        return default
