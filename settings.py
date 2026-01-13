import os
import json
import logging
from typing import Any

VERSION = '1.8.1'

REQUIRED_SETTINGS = [
    'version',
    'is_first_run',
    'language',
    'theme',
    'color_map',
    'visualize_type'
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
                self.data = self.default_settings
                self.save()

            logging.info(f'Конфигурационный файл успешно загружен.')
        else:
            self.data = self.default_settings
            self.save()

    def _check_data(self) -> None:
        logging.info('Проверка конфигурационного файла...')
        keys_to_generate: list[str] = []
        for setting in REQUIRED_SETTINGS:
            if setting not in self.data:
                keys_to_generate.append(setting)
        
        if len(self.data)+len(keys_to_generate) > len(REQUIRED_SETTINGS):
            to_delete: list[str] = []
            for key in self.data:
                if key not in REQUIRED_SETTINGS:
                    to_delete.append(key)
            for key in to_delete:
                del self.data[key]

        data = self.default_settings
        for key in keys_to_generate:
            self.data[key] = data[key]

        if self.data['version'] != VERSION:
            self._update()
        
        for key in self.data:
            if isinstance(self.data[key], dict) and 'current' in self.data[key]:
                if self.data[key]['current'] not in self.data[key]['available']:
                    self.data[key]['current'] = self.data[key]['available'][0]
        
        self.save()
        logging.info('Конфигурационный файл успешно проверен.')

    @property
    def default_settings(self) -> dict[str, Any]:
        return {
            'version': VERSION,
            'is_first_run': True,
            "language": {
                "current": "en",
                "available": ["en", "ru"]
            },
            'theme': {
                'current': 'dark',
                'available': ['light', 'dark']
            },
            'color_map': {
                'current': 'turbo',
                'available': [
                    "Nesting",
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
                ],
                'custom': [
                    'Nesting'
                ]
            },
            'visualize_type': {
                'current': 'TreeMap',
                'available': [
                    'TreeMap',
                    'Columns'
                ]
            }
        }

    def _update(self) -> None:
        data = self.default_settings
        for key in data:
            if isinstance(data[key], dict):
                for option in data[key]:
                    if option == 'current': continue
                    self.data[key][option] = data[key][option]

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
