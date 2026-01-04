import os
import sys
import platform
import logging


CURRENT_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) \
    else os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(CURRENT_DIR, "DiskAnalyzerData")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
PLATFORM = platform.system()
IGNORE_PATHS: set[str] = set(["/proc", "/sys", "/dev", "/run", "/tmp"]) if PLATFORM != "Windows" else set()

is_should_run_visualizer = True

def set_should_run_visualizer(value: bool) -> None:
    global is_should_run_visualizer
    is_should_run_visualizer = value

logging.basicConfig(level=logging.INFO, filename=os.path.join(DATA_DIR, "log.log"), filemode='w', format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
logging.info(f'Конфигурационный файл успешно запущен. {CURRENT_DIR=}. {DATA_DIR=}. {PLATFORM=}. {IGNORE_PATHS=}')
