import os
import logging
import urllib.request

from config import DATA_DIR
from translator import FILES


def update_language(lang: str):
    logging.info(f'Загрузка перевода: {lang}')
    if lang == 'en':
        return
    
    if not os.path.exists(os.path.join(DATA_DIR, 'locales', lang)):
        os.makedirs(os.path.join(DATA_DIR, 'locales', lang))

    url = f'https://raw.githubusercontent.com/Aetorny/Disk-Analyzer/main/DiskAnalyzerData/locales/{lang}/'
    try:
        for file in FILES:
            urllib.request.urlretrieve(
                url + file + '.po', 
                os.path.join(DATA_DIR, 'locales', lang, file + '.po')
            )

        logging.info(f'Перевод успешно загружен: {lang}')

    except Exception as e:
        logging.error(f'Ошибка при загрузке перевода: {e}')
