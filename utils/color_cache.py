import matplotlib.pyplot as plt

import math
import logging


class ColorCache:
    def __init__(self, cmap_name: str, steps: int = 512):
        logging.info(f"Цветовая схема: {cmap_name}")
        try:
            self.cmap = plt.get_cmap(cmap_name)
        except ValueError:
            self.colors_rgb = [(50, 50, 50)]
            self.steps = 0
            logging.warning(f"Цветовая схема не найдена: {cmap_name}")
            return
        self.steps = steps
        self.colors_rgb: list[tuple[int, int, int]] = []
        self.text_colors_hex: list[str] = [] 

        for i in range(steps):
            norm = i / (steps - 1)
            rgba = self.cmap(norm)
            
            # 0-1 -> 0-255
            r = int(rgba[0] * 255)
            g = int(rgba[1] * 255)
            b = int(rgba[2] * 255)
            self.colors_rgb.append((r, g, b))

    def get_color_rgb_and_text(self, size_bytes: float, global_max_log: float) -> tuple[int, int, int]:
        if size_bytes <= 0:
            return (50, 50, 50)
        log_min = 6.0
        log_curr = math.log10(size_bytes)
        
        if log_curr <= log_min:
            idx = 0
        elif log_curr >= global_max_log:
            idx = self.steps - 1
        else:
            norm = (log_curr - log_min) / (global_max_log - log_min)
            idx = int(norm * (self.steps - 1))
        
        safe_idx = max(0, min(idx, self.steps - 1))
        return self.colors_rgb[safe_idx]

    def get_rgb_by_number(self, number: int) -> tuple[int, int, int]:
        """
        Принимает число и возвращает кортеж (R, G, B) в диапазоне 0-255.
        """
        cmap = plt.get_cmap('tab20')
        
        index = int(number) % cmap.N
        
        rgba = cmap(index)
        
        r = int(rgba[0] * 255)
        g = int(rgba[1] * 255)
        b = int(rgba[2] * 255)
        
        return r, g, b
