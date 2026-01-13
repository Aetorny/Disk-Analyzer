import cairo
from PIL import Image

import time
import pickle
import logging
import threading
import compression.zstd
from typing import Any

import utils.squarify_local as squarify
from logic import Database
from utils import ColorCache


CULLING_SIZE_PX = 2


def render_pipeline(
        pipeline: str,
        width: int, height: int,
        current_root: str,
        database: Database,
        color_cache: ColorCache,
        global_max_log: float,
        search_data: set[str],
        is_level_color_map: bool,
        data_lock: threading.Lock
    ) -> tuple[Image.Image, list[tuple[float, float, float, float, str, str, float, bool, bool]]]:
    '''
    Пайплайн отрисовки в виде TreeMap.
    '''
    def _calculate_tree_map_layout(
            rects: list[tuple[int, int, int, int, int, int, int]],
            texts: list[tuple[float, float, str, str]],
            hit_map: list[tuple[float, float, float, float, str, str, float, bool, bool]],
            path_str: str,
            size: float, x: float, y: float, dx: float, dy: float,
            level: int) -> float:
        """
        Итеративно считает координаты (через стек). Не рисует, а заполняет списки rects и texts.
        """
        start_time = time.perf_counter()
        stack = [(path_str, path_str, size, x, y, dx, dy, level)]
        while stack:
            path, name, size, x, y, dx, dy, level = stack.pop()

            if dx < CULLING_SIZE_PX or dy < CULLING_SIZE_PX:
                continue

            if is_level_color_map:
                rgb_color = color_cache.get_rgb_by_number(level)
            else:
                rgb_color = color_cache.get_color_rgb_and_text(size, global_max_log)
            r, g, b = rgb_color
            brightness = (r * 299 + g * 587 + b * 114) / 1000
            text_color = "black" if brightness > 128 else "white"
            
            ix, iy, idx, idy = int(x), int(y), int(dx), int(dy)
            rects.append((iy, iy+idy, ix, ix+idx, r, g, b)) 
            
            hit_map.append((x, y, x+dx, y+dy, path, name, size, False, False))

            # Текст (Имя сверху)
            header_h = 0
            has_header_space = dx > 45 and dy > 40
            if has_header_space:
                header_h = 20
                max_chars = int(dx / 10)
                disp_name = name if len(name) <= max_chars else name[:max_chars] + "..."
                texts.append((x+4, y+3, disp_name, text_color))

            pad = 2
            norm_w, norm_h = dx - 2*pad, dy - header_h - 2*pad
            if norm_w < 4 or norm_h < 4:
                continue
            
            with data_lock:
                data = database[path]

            subfolders = pickle.loads(compression.zstd.decompress(data['subfolders']))
            if search_data:
                subfolders = [x for x in subfolders if x['p'] in search_data]

            files = []
            if level > 0 and not search_data:
                sizes: list[float] = [x['s'] for x in subfolders]
            else:
                files = pickle.loads(compression.zstd.decompress(data['files']))
                if search_data:
                    files = [x for x in files if x['p'] in search_data]
                sizes: list[float] = [x['s'] for x in subfolders + files]
                sizes.sort(reverse=True)

            norm = squarify.normalize_sizes(sizes, norm_w, norm_h, sum(sizes)) # pyright: ignore[reportUnknownMemberType]
            subfolders_norm, files_norm = norm[:len(subfolders)], norm[len(subfolders):]
            while 0.0 in subfolders_norm:
                subfolders_norm.remove(0.0)
            while 0.0 in files_norm:
                files_norm.remove(0.0)
            subfolders_len = len(subfolders_norm)
            rects_sq: list[dict[str, Any]] = squarify.squarify(subfolders_norm+files_norm, x + pad, y + header_h + pad, norm_w, norm_h) # type: ignore
            subfolders_rects, files_rects = rects_sq[:subfolders_len], rects_sq[subfolders_len:]

            for rect, folder in zip(subfolders_rects, subfolders):
                rx, ry, rdx, rdy = rect['x'], rect['y'], rect['dx'], rect['dy']

                stack.append((
                    folder['p'], 
                    folder['n'],
                    folder['s'], 
                    rx, ry, rdx, rdy, 
                    level + 1
                ))

            if level > 0 and not search_data:
                continue
            
            for rect, file in zip(files_rects, files):
                rx, ry, rdx, rdy = rect['x'], rect['y'], rect['dx'], rect['dy']
                
                if rdx > CULLING_SIZE_PX and rdy > CULLING_SIZE_PX:
                    f_rgb = color_cache.get_color_rgb_and_text(file['s'], global_max_log)
                    r, g, b = f_rgb
                    brightness = (r * 299 + g * 587 + b * 114) / 1000
                    text_color = "black" if brightness > 128 else "white"
                    rix, riy, ridx, ridy = int(rx), int(ry), int(rdx), int(rdy)
                    
                    rects.append((riy, riy+ridy, rix, rix+ridx, r, g, b))
                    
                    if rdx > 40 and rdy > 30:
                        max_chars = int(rdx / 10)
                        name = file['n']
                        dname = name if len(name) <= max_chars else name[:max_chars] + "..."

                        texts.append((rx+4, ry+3, dname, text_color))
                    
                    hit_map.append((rx, ry, rx+rdx, ry+rdy, file['p'], name, file['s'], False, True))
        end_time = time.perf_counter()
        return end_time - start_time

    def _calculate_columns_layout(
            rects: list[tuple[int, int, int, int, int, int, int]],
            texts: list[tuple[float, float, str, str]],
            hit_map: list[tuple[float, float, float, float, str, str, float, bool, bool]],
            path_str: str,
            size: float, x: float, y: float, dx: float, dy: float,
            level: int
        ) -> float:
        """
        Расчет координат.
        Структура: [ ПАПКИ (столбцы) | ФАЙЛЫ (строки) ]
        """
        start_time = time.perf_counter()
        stack = [(path_str, path_str, size, x, y, dx, dy, level)]

        while stack:
            curr_path, curr_name, curr_size, cx, cy, cdx, cdy, lvl = stack.pop()

            if cdx < CULLING_SIZE_PX or cdy < CULLING_SIZE_PX:
                continue
            
            if is_level_color_map:
                rgb_color = color_cache.get_rgb_by_number(lvl)
            else:
                rgb_color = color_cache.get_color_rgb_and_text(curr_size, global_max_log)
            r, g, b = rgb_color
            brightness = (r * 299 + g * 587 + b * 114) / 1000
            text_color = "black" if brightness > 128 else "white"

            rects.append((int(cy), int(cy + cdy), int(cx), int(cx + cdx), r, g, b))

            header_h = 0.0
            if cdx > 40 and cdy > 40:
                header_h = 20.0
                max_chars = int(cdx / 9)
                disp_name = curr_name[:max_chars] + "..." if len(curr_name) > max_chars else curr_name
                texts.append((cx + 4, cy + 3, disp_name, text_color))

            with data_lock:
                if curr_path not in database:
                    hit_map.append((cx, cy, cx+cdx, cy+cdy, curr_path, curr_name, curr_size, False, True))
                    continue
                
                node_data = database[curr_path]
                hit_map.append((cx, cy, cx+cdx, cy+cdy, curr_path, curr_name, curr_size, False, False))

            child_area_h = cdy - header_h
            if child_area_h < 2.0:
                continue

            subfolders = pickle.loads(compression.zstd.decompress(node_data['subfolders']))
            files = pickle.loads(compression.zstd.decompress(node_data['files']))

            if search_data:
                subfolders = [x for x in subfolders if x['p'] in search_data]
                files = [x for x in files if x['p'] in search_data]

            if not subfolders and not files:
                continue

            subfolders.sort(key=lambda x: x['s'], reverse=True) # pyright: ignore[reportUnknownLambdaType]
            files.sort(key=lambda x: x['s'], reverse=True) # pyright: ignore[reportUnknownLambdaType]

            sum_folders = sum(f['s'] for f in subfolders)
            sum_files = sum(f['s'] for f in files)
            total_s = sum_folders + sum_files
            
            if total_s <= 0:
                continue

            # Базовый отступ внутри папки
            pad = 1.0 if cdx > 40 else 0.0
            
            current_x = cx + pad
            available_w = max(0.0, cdx - 2 * pad)
            start_y = cy + header_h + pad
            available_h = max(0.0, child_area_h - 2 * pad)

            if available_w < 1.0 or available_h < 1.0:
                continue

            for folder in subfolders:
                ratio = folder['s'] / total_s
                folder_w = ratio * available_w
                
                if folder_w >= 1.0:
                    stack.append((
                        folder['p'], folder['n'], folder['s'],
                        current_x, start_y, folder_w, available_h,
                        lvl + 1
                    ))
                current_x += folder_w

            if sum_files == 0:
                continue

            raw_files_width = (sum_files / total_s) * available_w
            
            extra_file_pad = 3.0
            
            file_draw_x = current_x + extra_file_pad
            file_draw_w = raw_files_width - (2 * extra_file_pad)
            
            dark_factor = 0.75 

            if file_draw_w >= CULLING_SIZE_PX:
                file_y_cursor = start_y
                
                for file in files:
                    file_h_ratio = file['s'] / sum_files
                    file_h = file_h_ratio * available_h
                    
                    if file_h >= 1.0:
                        if is_level_color_map:
                            f_rgb = color_cache.get_rgb_by_number(lvl)
                        else:
                            f_rgb = color_cache.get_color_rgb_and_text(file['s'], global_max_log)
                        fr = f_rgb[0] * dark_factor
                        fg = f_rgb[1] * dark_factor
                        fb = f_rgb[2] * dark_factor
                        
                        rects.append((
                            int(file_y_cursor), int(file_y_cursor + file_h),
                            int(file_draw_x), int(file_draw_x + file_draw_w),
                            int(fr), int(fg), int(fb)
                        ))
                        
                        hit_map.append((
                            file_draw_x, file_y_cursor, 
                            file_draw_x + file_draw_w, file_y_cursor + file_h, 
                            file['p'], file['n'], file['s'], 
                            False, True
                        ))
                        
                        if file_h > 14 and file_draw_w > 40:
                            f_bright = (fr * 299 + fg * 587 + fb * 114) / 1000
                            f_tcol = "black" if f_bright > 128 else "white"
                            
                            max_f_chars = int(file_draw_w / 9)
                            f_disp_name = file['n']
                            if len(f_disp_name) > max_f_chars:
                                f_disp_name = f_disp_name[:max_f_chars] + "..."
                            
                            texts.append((file_draw_x + 4, file_y_cursor + (file_h/2) - 7, f_disp_name, f_tcol))
                    
                    file_y_cursor += file_h
        end_time = time.perf_counter()
        return end_time - start_time

    # Список (y1, y2, x1, x2, r, g, b)
    rects: list[tuple[int, int, int, int, int, int, int]] = []
    # Список (x, y, text, font, color, anchor)
    texts: list[tuple[float, float, str, str]] = []
    # Список (x1, y1, x2, y2, name, size_str, size, is_file, is_group)
    hit_map: list[tuple[float, float, float, float, str, str, float, bool, bool]] = []
    logging.info(f'Начало расчета макета {pipeline}...')
    with data_lock:
        size = database[current_root]['s']
    layout = _calculate_tree_map_layout
    if pipeline == 'Columns':
        layout = _calculate_columns_layout
    execution_time = layout(
        rects, texts, hit_map,
        current_root,
        size, 0, 0, width, height, 0
    )
    logging.info(f'Расчёт макета завершён. Получено {len(rects)=} | {len(texts)=} | {len(hit_map)=}')
    logging.info(f'Время расчёта макета: {execution_time} секунд')
    
    stride = width * 4
    data = bytearray(stride * height)
    surface = cairo.ImageSurface.create_for_data(
        data, 
        cairo.FORMAT_ARGB32, 
        width, 
        height, 
        stride
    )
    ctx = cairo.Context(surface)

    bg_val = 32 / 255.0
    ctx.set_source_rgb(bg_val, bg_val, bg_val)
    ctx.paint() #
    for y1, y2, x1, x2, r, g, b in rects:
        w = x2 - x1
        h = y2 - y1
        
        # --- Черная подложка (Outline) ---
        ctx.set_source_rgb(0, 0, 0)
        ctx.rectangle(x1, y1, w, h)
        ctx.fill()
        
        # --- Цветная середина ---
        if w > 2 and h > 2:
            # Cairo принимает цвета 0.0-1.0
            # Cairo ARGB пишет в памяти B-G-R-A (на little-endian).
            ctx.set_source_rgb(b/255.0, g/255.0, r/255.0)
            
            # Рисуем внутренний квадрат (+1 пиксель отступа)
            ctx.rectangle(x1 + 1, y1 + 1, w - 2, h - 2)
            ctx.fill()
        else:
            ctx.set_source_rgb(b/255.0, g/255.0, r/255.0)
            ctx.rectangle(x1, y1, w, h)
            ctx.fill()

    ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(14) 

    for tx, ty, ttext, tcol in texts:
        if tcol == 'black':
            ctx.set_source_rgb(0, 0, 0)
        else:
            ctx.set_source_rgb(1, 1, 1)
        ctx.move_to(tx, ty + 14)
        ctx.show_text(ttext)
    surface.flush()

    image = Image.frombuffer("RGBA", (width, height), data, "raw", "RGBA", 0, 1)
    return (image, hit_map)
