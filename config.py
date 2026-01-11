import os
import sys
import locale
import platform
import logging

from settings import Settings
from translator import Translator


CURRENT_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) \
    else os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(CURRENT_DIR, "DiskAnalyzerData")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
PLATFORM = platform.system()
IGNORE_PATHS: set[str] = set(["/proc", "/sys", "/dev", "/run", "/tmp"]) if PLATFORM != "Windows" else set()

def get_language() -> str:
    LANGUAGE_NAMES: dict[str, str] = {
        'Russian': 'ru',
    }
    lang_temp, _ = locale.getlocale()
    if lang_temp is None:
        lang_temp = 'en'
    lang = 'en'
    for l in LANGUAGE_NAMES:
        if l in lang_temp:
            lang = LANGUAGE_NAMES[l]
    return lang

LANGUAGE = get_language()

is_should_run_visualizer = True
is_should_run_analyzer = False

def set_should_run_visualizer(value: bool) -> None:
    global is_should_run_visualizer
    is_should_run_visualizer = value

def set_should_run_analyzer(value: bool) -> None:
    global is_should_run_analyzer
    is_should_run_analyzer = value

def set_default_values() -> None:
    global is_should_run_visualizer
    global is_should_run_analyzer
    is_should_run_visualizer = True
    is_should_run_analyzer = False

logging.basicConfig(level=logging.INFO, filename=os.path.join(DATA_DIR, "log.log"), encoding='utf-8', filemode='w', format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
logging.info(f'Конфигурационный файл успешно запущен. {CURRENT_DIR=}. {DATA_DIR=}. {PLATFORM=}. {IGNORE_PATHS=}. {LANGUAGE=}. {is_should_run_visualizer=}. {is_should_run_analyzer=}.')

SETTINGS = Settings(os.path.join(DATA_DIR, "settings.json"))

TRANSLATOR = Translator()
TRANSLATOR.change_language(SETTINGS['language']['current'])
