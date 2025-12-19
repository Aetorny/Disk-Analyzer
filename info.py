import os
import platform


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(CURRENT_DIR, "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
PLATFORM = platform.system()
IGNORE_PATHS: set[str] = set(["/proc", "/sys", "/dev", "/run", "/tmp"]) if PLATFORM != "Windows" else set()
