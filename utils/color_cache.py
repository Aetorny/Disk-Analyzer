import matplotlib.pyplot as plt

import math


class ColorCache:
    def __init__(self, cmap_name: str, steps: int = 512):
        self.cmap = plt.get_cmap(cmap_name)
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
            
            # Яркость
            luminance = 0.299*rgba[0] + 0.587*rgba[1] + 0.114*rgba[2]
            self.text_colors_hex.append("#000000" if luminance > 0.5 else "#FFFFFF")
    
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