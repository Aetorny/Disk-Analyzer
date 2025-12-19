from __future__ import annotations
from tqdm import tqdm

import os
import json
from typing import Optional, Any

from info import CURRENT_DIR, DATA_DIR, IGNORE_PATHS
from disk_info import get_start_directories, get_used_disk_size
from folder import Folder
from folder_info import FolderInfo


class SizeFinder:
    def get_size_of_directory(
            self, path: str,
            folder: Optional[Folder] = None,
            pbar: Optional[tqdm[Any]] = None
        ) -> Folder:
        folder = Folder(path, parent=folder)
        try:
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        if os.path.islink(entry.path):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if entry.path.rstrip('/\\') in IGNORE_PATHS:
                                if pbar:
                                    pbar.write(f"Skipping ignored path: {entry.path}")
                                continue
                            subfolder = self.get_size_of_directory(entry.path, folder=folder, pbar=pbar)
                            folder.subfolders_size[entry.path] = subfolder.used_size
                            folder.used_size += subfolder.used_size
                        elif entry.is_file(follow_symlinks=False):
                            file_size = entry.stat(follow_symlinks=False).st_size
                            folder.used_size += file_size
                            if pbar:
                                pbar.update(file_size)
                    except Exception as e:
                        if pbar:
                            pbar.write(f"Error processing entry {entry.path}: {e}")
                        else:
                            print(f"Error processing entry {entry.path}: {e}")
                        continue
        except Exception as e:
            if pbar:
                pbar.write(f"Error accessing directory {path}: {e}")
            else:
                print(f"Error accessing directory {path}: {e}")
            return folder

        self.folders[path] = {
            "used_size": folder.used_size,
            "subfolders": list(folder.subfolders_size.keys())
        }

        return folder

    def __init__(self, paths: Optional[list[str]] = None) -> None:
        self.starting_points = get_start_directories() if paths is None else paths

    def run(self) -> None:
        for start in self.starting_points:
            used_size = None
            try:
                used_size = get_used_disk_size(start)
                print(f"Path: {start} - Used Size: {used_size / (1024 ** 3):.2f} GB")
            except Exception as e:
                print(f"Could not access {start}: {e}")
            
            self.folders: dict[str, FolderInfo] = {}
            with tqdm(total=used_size, unit='B', unit_scale=True, unit_divisor=1024, desc="Scanning") as pbar:
                self.get_size_of_directory(start, pbar=pbar)

            with open(os.path.join(CURRENT_DIR, DATA_DIR,
                f"disk_usage_{start.replace(':', '').replace('/', '_').replace('\\', '_').rstrip('_')}.json"),
                "w") as f:
                json.dump(self.folders, f, indent=4)

if __name__ == "__main__":
    size_finder = SizeFinder()
    size_finder.run()
