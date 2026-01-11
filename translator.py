import polib

import os
import gettext
import logging

import config


FILES = [
    'formatting',
    'disk_indexing',
    'visualizer'
]


class Translator:
    def __init__(self) -> None:
        self.translates = {
            file: gettext.NullTranslations() for file in FILES
        }
        self.current_language = 'en'

    def change_language(self, lang: str):
        logging.info(f'Загрузка перевода: {lang}')
        if self.current_language == lang:
            return
        if lang == 'en':
            self.translates = {
                file: gettext.NullTranslations() for file in FILES
            }
            self.current_language = 'en'
            return

        try:
            for file in FILES:
                path_to_file = os.path.join(config.DATA_DIR, 'locales', lang, file)

                if os.path.exists(path_to_file+'.po'):
                    po = polib.pofile(path_to_file+'.po')
                    po.save_as_mofile(path_to_file+'.mo')
                
                if not os.path.exists(path_to_file+'.mo'):
                    raise FileNotFoundError(f'Файл перевода {path_to_file}.mo не обнаружен')

                with open(path_to_file+'.mo', 'rb') as f:
                    self.translates[file] = gettext.GNUTranslations(f)
                    self.current_language = lang
            
            logging.info(f'Перевод успешно загружен: {lang}')

        except Exception as e:
            logging.error(f'Ошибка при загрузке перевода: {e}')
            self.translates = {
                file: gettext.NullTranslations() for file in FILES
            }
            self.current_language = 'en'

    def gettext(self, filename: str):
        return self.translates[filename].gettext

    def ngettext(self, filename: str):
        return self.translates[filename].ngettext
