import os
import json
import logging
from typing import Any


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
            except Exception as e:
                logging.error(f'Ошибка при загрузке конфигурационного файла: {e}')
                return self._generate_default_settings()

            logging.info(f'Конфигурационный файл успешно загружен.')
        else:
            self._generate_default_settings()

    def _generate_default_settings(self) -> None:
        logging.info('Создание стандартного конфигурационного файла...')
        self.data = {
            'appearence_mode': {
                'current': 'system',
                'available': ['system', 'light', 'dark']
            },
            'theme': {
                'current': 'blue',
                'available': ['blue', 'green', 'dark-blue']
            }
        }
        self._save()
        logging.info('Стандартный конфигурационный файл создан.')

    def _save(self) -> None:
        logging.info('Сохранение конфигурационного файла...')
        try:
            with open(self.path, 'w') as f:
                json.dump(self.data, f)
        except Exception as e:
            logging.error(f'Ошибка при сохранении конфигурационного файла: {e}')
            return

        logging.info('Конфигурационный файл успешно сохранен.')

    def __getattr__(self, name: str) -> Any:
        return self.data[name]

    def __setattr__(self, name: str, value: Any) -> None:
        self.data[name] = value
        self._save()

    def __delattr__(self, name: str) -> None:
        del self.data[name]
        self._save()

    def get(self, name: str, default: Any = None) -> Any:
        if name in self.data:
            return self.data[name]
        return default
