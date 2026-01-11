import customtkinter as ctk
import cairo
from tkinter import Menu
from PIL import Image, ImageTk

import os
import math
import logging
import threading
import pickle
import compression.zstd
import time
from typing import Any

import utils.squarify_local as squarify
from logic import Database
from config import DATA_DIR, set_should_run_analyzer, SETTINGS
from utils import ColorCache, format_bytes


CULLING_SIZE_PX = 2
color_cache = ColorCache(SETTINGS['color_map']['current'])

ctk.set_appearance_mode(SETTINGS['appearence_mode']['current'])
ctk.set_default_color_theme('blue')


class DiskVisualizerApp(ctk.CTk):
    def __init__(self, databases: dict[str, Database]):
        super().__init__() # pyright: ignore[reportUnknownMemberType]

        self.title("Disk Visualizer")
        self.geometry("1200x900")

        # Создаем меню
        self.create_menu()

        self.layout_cache: dict[tuple[Any, Any, Any], Any] = {}
        self.raw_data: Database
        self.databases = databases
        self.search_data: set[str] = set()
        self.current_root: str = ""
        self.scan_root_path: str = ""
        self.global_max_log = 1.0
        self.is_search_bar_active = False

        self.hit_map = []
        self.current_tk_image = None
        self.highlight_rect_id = None
        
        self._resize_job = None
        self._render_lock = threading.Lock()
        self._search_lock = threading.Lock()
        self._search_workers = 0
        
        # GUI
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Панель вверху
        self.top_frame = ctk.CTkFrame(self, height=40)
        self.top_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5) # pyright: ignore[reportUnknownMemberType]
        
        self.btn_return_to_analyzer = ctk.CTkButton(self.top_frame, text="⬅", width=30, fg_color="red", command=self.return_to_analyzer)
        self.btn_return_to_analyzer.pack(side="left", padx=(5, 2)) # pyright: ignore[reportUnknownMemberType]

        self.btn_up = ctk.CTkButton(self.top_frame, text="⬆ Вверх", width=60, command=self.go_up_level, state="disabled")
        self.btn_up.pack(side="left", padx=(5, 2)) # pyright: ignore[reportUnknownMemberType]

        self.breadcrumb_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.breadcrumb_frame.pack(side="left", padx=5, fill="x", expand=True) # pyright: ignore[reportUnknownMemberType]

        self.combo_files = ctk.CTkComboBox(self.top_frame, width=200, command=self.change_data)
        self.combo_files.pack(side="right", padx=5) # pyright: ignore[reportUnknownMemberType]

        # Canvas
        self.canvas_frame = ctk.CTkFrame(self)
        self.canvas_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=0) # pyright: ignore[reportUnknownMemberType]
        
        self.canvas = ctk.CTkCanvas(self.canvas_frame, bg="#202020", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        self.canvas.bind("<Configure>", self.on_resize)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Button-1>", self.on_left_click)
        self.canvas.bind("<Button-3>", self.on_right_click)

        self.search_entry = None
        self.search_var = ctk.StringVar(value="")
        self.search_var.trace_add("write", self.on_search)
        self.search_button = ctk.CTkButton(self.top_frame, text="🔍", font=("Arial", 16), width=30, command=self.toggle_search_bar)
        self.search_button.pack(side="right", padx=5) # pyright: ignore[reportUnknownMemberType]
        self.bind("<Control-f>", self.toggle_search_bar)
        self.bind("<Control-F>", self.toggle_search_bar)
        self.bind("<Escape>", self.hide_search_bar)

        self.status_bar = ctk.CTkLabel(self, text="Ready", anchor="w", height=25, font=("Arial", 14))
        self.status_bar.grid(row=2, column=0, sticky="ew", padx=5) # pyright: ignore[reportUnknownMemberType]

        self.context_menu = Menu(self, tearoff=0)
        self.context_menu.add_command(label="Копировать путь", command=self.copy_path)
        self.context_menu.add_command(label="Копировать имя", command=self.copy_name)
        self.selected_item = None

        self.tooltip_bg = self.canvas.create_rectangle(0, 0, 0, 0, fill="#2b2b2b", outline="#a0a0a0", state="hidden")
        self.tooltip_text = self.canvas.create_text(0, 0, text="", anchor="nw", fill="white", font=("Arial", 10), state="hidden")

        logging.info('UI успешно инициализирован')

        self.refresh_file_list()
        self.after(1000, self.trigger_render)

    def toggle_search_bar(self, *_: Any) -> None:
        self.is_search_bar_active = not self.is_search_bar_active
        if self.is_search_bar_active:
            self.search_entry = ctk.CTkEntry(
                self.top_frame,
                textvariable=self.search_var,
                placeholder_text="Поиск",
                width=250
            )
            self.search_entry.pack() # pyright: ignore[reportUnknownMemberType]
            self.search_entry.focus()
        else:
            self.hide_search_bar(None)

    def hide_search_bar(self, _: Any) -> None:
        if self.search_entry:
            self.search_entry.destroy()
            self.is_search_bar_active = False
            self.search_var = ctk.StringVar(value="")
            self.search_var.trace_add("write", self.on_search)
        self.search_data = set()
        self.after(100, self.trigger_render)

    def create_menu(self):
        """Создает меню приложения"""
        # Получаем основное окно (которое использует tk.Tk)
        menubar = Menu(self)
        self.config(menu=menubar)
        
        # Меню "Меню"
        menu_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Меню", menu=menu_menu)
        menu_menu.add_command(label="Настройки", command=self.open_settings)
        
        # Меню "Справка"
        help_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Справка", menu=help_menu)
        help_menu.add_command(label="О программе", command=self.show_about)

    def open_settings(self):
        """Открывает окно редактирования настроек с современным интерфейсом"""
        settings_window = ctk.CTkToplevel(self)
        settings_window.title("Настройки")
        settings_window.geometry("450x280")
        settings_window.resizable(False, False)
        settings_window.grab_set()
        
        # Заголовок
        title_label = ctk.CTkLabel(settings_window, text="Настройки", font=("Arial", 18, "bold"))
        title_label.pack(padx=20, pady=(20, 30)) # pyright: ignore[reportUnknownMemberType]
        
        # Основной контейнер для настроек
        settings_container = ctk.CTkFrame(settings_window)
        settings_container.pack(fill="both", expand=True, padx=20, pady=(0, 20)) # pyright: ignore[reportUnknownMemberType]
        settings_container.grid_columnconfigure(1, weight=1)
        
         # ===== РЕЖИМ ОТОБРАЖЕНИЯ =====
        appearance_label = ctk.CTkLabel(settings_container, text="Режим отображения:", font=("Arial", 16))
        appearance_label.grid(row=0, column=0, sticky="w", pady=(0, 15)) # pyright: ignore[reportUnknownMemberType]
        
        current_appearance = SETTINGS['appearence_mode']['current']
        available_appearances = SETTINGS['appearence_mode']['available']
        appearance_options = [app for app in available_appearances]
        
        appearance_combo = ctk.CTkComboBox(
            settings_container,
            values=appearance_options,
            state="readonly",
            command=lambda value: self.on_appearance_changed(available_appearances[appearance_options.index(value)])
        )
        appearance_combo.set(current_appearance)
        appearance_combo.grid(row=0, column=1, sticky="ew", pady=(0, 15), padx=(20, 0)) # pyright: ignore[reportUnknownMemberType]

        # ===== Цветовая схема =====
        color_map_label = ctk.CTkLabel(settings_container, text="Цветовая схема:", font=("Arial", 16))
        color_map_label.grid(row=1, column=0, sticky="w", pady=(0, 15)) # pyright: ignore[reportUnknownMemberType]
        
        current_color_map = SETTINGS['color_map']['current']
        self.is_inverted_theme = False if not current_color_map.endswith('_r') else True
        available_color_maps = sorted(SETTINGS['color_map']['available'], key=lambda x: x.lower())
        color_map_options = [app for app in available_color_maps]
        
        color_map_combo = ctk.CTkComboBox(
            settings_container,
            values=color_map_options,
            state="readonly",
            command=lambda value: self.on_color_map_change(available_color_maps[color_map_options.index(value)])
        )
        color_map_combo.set(current_color_map.replace('_r', ''))
        color_map_combo.grid(row=1, column=1, sticky="ew", pady=(0, 15), padx=(20, 0)) # pyright: ignore[reportUnknownMemberType]
        
        invert_theme_label = ctk.CTkLabel(settings_container, text="Инвертировать цветовую схему:", font=("Arial", 16))
        invert_theme_label.grid(row=2, column=0, sticky="w", pady=(0, 15)) # pyright: ignore[reportUnknownMemberType]
        
        self.invert_theme_check = ctk.CTkCheckBox(
            settings_container,
            text="",
            command=self.on_invert_theme_change,
            checkbox_width=24, 
            checkbox_height=24,
            corner_radius=8,
            fg_color="blue",
            hover_color="darkblue"
        )
        self.invert_theme_check.select() if self.is_inverted_theme else self.invert_theme_check.deselect()
        self.invert_theme_check.grid(row=2, column=1, sticky="ew", pady=(0, 15), padx=(20, 0)) # pyright: ignore[reportUnknownMemberType]

        # Кнопка закрытия
        close_button = ctk.CTkButton(
            settings_window,
            text="Закрыть", 
            command=settings_window.destroy,
            fg_color="#3b3b3b",
            height=40
        )
        close_button.pack(fill="x", padx=20, pady=(0, 20)) # pyright: ignore[reportUnknownMemberType]

    def on_appearance_changed(self, appearance: str):
        """Обработчик изменения режима отображения"""
        SETTINGS['appearence_mode']['current'] = appearance
        SETTINGS.save()
        ctk.set_appearance_mode(appearance)
        logging.info(f"Режим отображения изменен на: {appearance}")

    def on_invert_theme_change(self):
        """Обработчик изменения инвертирования цветовой схемы"""
        self.is_inverted_theme = not self.is_inverted_theme
        self.on_color_map_change(SETTINGS['color_map']['current'])

    def on_color_map_change(self, color_map: str):
        """Обработчик изменения цветовой схемы"""
        global color_cache
        SETTINGS['color_map']['current'] = color_map.replace('_r', '') + ('_r' if self.is_inverted_theme else '')
        SETTINGS.save()
        color_cache = ColorCache(SETTINGS['color_map']['current'])
        logging.info(f"Цветовая схема изменена на: {SETTINGS['color_map']['current']}")
        self.after(0, self.trigger_render)

    def show_about(self):
        """Показывает окно 'О программе'"""
        about_window = ctk.CTkToplevel(self)
        about_window.title("О программе")
        about_window.geometry("450x250")
        about_window.resizable(False, False)
        about_window.grab_set()
        
        # Основная информация о программе
        title_label = ctk.CTkLabel(about_window, text="Disk Analyzer", font=("Arial", 18, "bold"))
        title_label.pack(pady=(20, 10)) # pyright: ignore[reportUnknownMemberType]
        
        info_label = ctk.CTkLabel(
            about_window, 
            text="Программа для анализа и визуализации\nиспользования дискового пространства",
            font=("Arial", 16),
            justify="center"
        )
        info_label.pack(pady=10) # pyright: ignore[reportUnknownMemberType]
        
        # GitHub ссылка
        github_frame = ctk.CTkFrame(about_window, fg_color="transparent")
        github_frame.pack(pady=10) # pyright: ignore[reportUnknownMemberType]
        
        github_label = ctk.CTkLabel(github_frame, text="GitHub:", font=("Arial", 16))
        github_label.pack(side="left", padx=5) # pyright: ignore[reportUnknownMemberType]
        
        github_link = ctk.CTkLabel(
            github_frame, 
            text="https://github.com/Aetorny/Disk-Analyzer",
            font=("Arial", 16, "underline"),
            text_color="#0066cc",
            cursor="hand2"
        )
        github_link.pack(side="left", padx=5) # pyright: ignore[reportUnknownMemberType]
        github_link.bind("<Button-1>", lambda _: webbrowser.open("https://github.com/Aetorny/Disk-Analyzer")) # type: ignore
        
        # Кнопка закрытия
        close_button = ctk.CTkButton(
            about_window, 
            text="Закрыть", 
            command=about_window.destroy,
            fg_color="#3b3b3b",
            height=40
        )
        close_button.pack(fill="x", padx=20, pady=(0, 20)) # pyright: ignore[reportUnknownMemberType]

    def _on_search_thread(self) -> None:
        if self._search_lock.locked():
            time.sleep(0.1)
        if not self._search_lock.acquire(blocking=False):
            return
        try:
            search_str = self.search_var.get().strip().lower()
            self.search_data = set()
            for path in self.raw_data:
                if path.startswith('__'): continue
                for folder in pickle.loads(compression.zstd.decompress(self.raw_data[path]['subfolders'])):
                    if self._search_workers > 1: return
                    if search_str in folder['n'].lower():
                        current = folder['p']
                        while current != self.scan_root_path:
                            self.search_data.add(current)
                            current = os.path.dirname(current)
                for file in pickle.loads(compression.zstd.decompress(self.raw_data[path]['files'])):
                    if self._search_workers > 1: return
                    if search_str in file['n'].lower():
                        current = file['p']
                        while current != self.scan_root_path:
                            self.search_data.add(current)
                            current = os.path.dirname(current)
            self.search_data.add(self.scan_root_path)
        finally:
            self._search_lock.release()
            self._search_workers -= 1
            self.after(0, self.trigger_render)

    def on_search(self, *_: Any) -> None:
        search_str = self.search_var.get().strip().lower()
        if search_str == '':
            self.search_data = set()
            self.after(100, self.trigger_render)
            return
        self._search_workers += 1
        threading.Thread(target=self._on_search_thread, daemon=True).start()

    def refresh_file_list(self):
        '''Обновление списка файлов'''
        paths = sorted([key for key, db in self.databases.items() if not db.is_empty()])
        if paths:
            logging.info(f'Обнаружены пути: {paths}')
            self.combo_files.configure(values=paths) # pyright: ignore[reportUnknownMemberType]
            self.combo_files.set(paths[0])
            for file in paths:
                logging.info(f'Запуск загрузки данных из {file}')
            self.change_data(paths[0])
        else:
            logging.info(f'Данных в папке {DATA_DIR} не обнаружено')
            self.restart_app_label = ctk.CTkLabel(self.canvas_frame, text=f"Данные в папке {DATA_DIR}\nне обнаружены\nДобавьте файлы и запустите программу заново", font=("Arial", 20))
            self.restart_app_label.place(relx=0.5, rely=0.5, anchor="center") # pyright: ignore[reportUnknownMemberType]

    def change_data(self, path: str) -> None:
        self.raw_data = self.databases[path]
        self.scan_root_path = self.raw_data['__root__']
        if self.scan_root_path in self.raw_data:
            size = self.raw_data[self.scan_root_path]['s']
            self.global_max_log = math.log10(size)
        self.change_directory(self.scan_root_path)

    def change_directory(self, path_str: str):
        self.current_root = path_str
        self.search_data = set()
        self.trigger_render()
        self.on_search(None)
        self.update_breadcrumbs(path_str)
        self.check_up_button()
    
    def check_up_button(self):
        if self.current_root == self.scan_root_path:
            self.btn_up.configure(state="disabled"); return # pyright: ignore[reportUnknownMemberType]
        parent = os.path.dirname(self.current_root)
        
        while parent and len(parent) >= len(self.scan_root_path):
            if parent in self.raw_data:
                self.btn_up.configure(state="normal"); return # pyright: ignore[reportUnknownMemberType]
            if parent == os.path.dirname(parent): break
            parent = os.path.dirname(parent)
        self.btn_up.configure(state="disabled") # pyright: ignore[reportUnknownMemberType]

    def go_up_level(self):
        parent = os.path.dirname(self.current_root)
        while parent and len(parent) >= len(self.scan_root_path):
            if parent in self.raw_data:
                self.change_directory(parent)
                return
            if parent == os.path.dirname(parent): break
            parent = os.path.dirname(parent)

    def update_breadcrumbs(self, path_str: str):
        for widget in self.breadcrumb_frame.winfo_children(): # type: ignore
            widget.destroy() # pyright: ignore[reportUnknownMemberType]
        clean_path = path_str.lstrip('\\')
        parts = clean_path.split(os.sep)
        if path_str.startswith('\\\\'): parts[0] = f"\\\\{parts[0]}"
        accumulated_path = ""
        for i, part in enumerate(parts):
            if not part: continue
            accumulated_path = (part + os.sep if ":" in part else part) if i == 0 else os.path.join(accumulated_path, part)
            is_valid, is_last = (accumulated_path in self.raw_data), (accumulated_path == self.current_root)
            btn = ctk.CTkButton(
                self.breadcrumb_frame, text=part, fg_color="transparent",
                hover_color="#555555", text_color="#FFFFFF" if is_last else ("#1E90FF" if is_valid else "#777777"),
                state="normal" if (is_valid and not is_last) else "disabled", height=25, width=20,
                command=lambda p=accumulated_path: self.change_directory(p)
            )
            btn.pack(side="left", padx=0) # pyright: ignore[reportUnknownMemberType]
            if accumulated_path != self.current_root:
                ctk.CTkLabel(self.breadcrumb_frame, text="›", width=12, text_color="#777777").pack(side="left") # pyright: ignore[reportUnknownMemberType]

    def on_resize(self, _: Any):
        if self._resize_job: self.after_cancel(self._resize_job)
        self._resize_job = self.after(100, self.trigger_render) # Чуть быстрее реакция

    def trigger_render(self):
        if not self.current_root: return
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        
        cache_key = (self.current_root, w, h, SETTINGS['color_map']['current'])
        
        logging.info('Запуск пайплайна отрисовки')
        threading.Thread(target=self._render_pipeline, args=(w, h, cache_key), daemon=True).start()

    def _render_pipeline(self, width: int, height: int, cache_key: tuple[str, int, int]):
        '''
        Пайплайн отрисовки
        '''
        if not self._render_lock.acquire(blocking=False):
            return
        try:
            if cache_key in self.layout_cache and not self.search_data:
                logging.info(f'Макет из кэша: {cache_key}')
                rects, texts, hit_map = self.layout_cache[cache_key]
            else:
                # Список (y1, y2, x1, x2, r, g, b)
                rects: list[tuple[float, float, float, float, float, float, float]] = []
                # Список (x, y, text, font, color, anchor)
                texts: list[tuple[float, float, str, str, str | None]] = []
                # Список (x1, y1, x2, y2, name, size_str, size, is_file, is_group)
                hit_map: list[tuple[float, float, float, float, str, str, float, bool, bool]] = []
                logging.info('Начало расчета макета')
                execution_time = self._calculate_layout(
                    rects, texts, hit_map,
                    self.current_root,
                    self.raw_data[self.current_root]['s'], 0, 0, width, height, 0
                )
                logging.info(f'Расчёт макета завершён. Получено {len(rects)=} | {len(texts)=} | {len(hit_map)=}')
                logging.info(f'Время расчёта макета: {execution_time} секунд')
                if execution_time >= 0.1:
                    logging.info(f'Макет сохранён в кэш: {cache_key}')
                    self.layout_cache[cache_key] = (rects, texts, hit_map)
            
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
                    # Если слишком мелкий, просто красим
                    ctx.set_source_rgb(b/255.0, g/255.0, r/255.0)
                    ctx.rectangle(x1, y1, w, h)
                    ctx.fill()

            ctx.select_font_face("Arial", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            ctx.set_font_size(14) 

            for tx, ty, ttext, tcol, _ in texts:
                if tcol == 'black':
                    ctx.set_source_rgb(0, 0, 0)
                else:
                    ctx.set_source_rgb(1, 1, 1)
                ctx.move_to(tx, ty + 14)
                ctx.show_text(ttext)
            surface.flush()

            image = Image.frombuffer("RGBA", (width, height), data, "raw", "RGBA", 0, 1)
            self.after(0, lambda: self._update_canvas(image, hit_map))
        finally:
            self._render_lock.release()
            logging.info('Пайплайн отрисовки завершён')

    def _calculate_layout(
            self,
            rects: list[tuple[float, float, float, float, float, float, float]],
            texts: list[tuple[float, float, str, str, str | None]],
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

            rgb_color = color_cache.get_color_rgb_and_text(size, self.global_max_log)
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
                texts.append((x+4, y+3, disp_name, text_color, None))

            pad = 2
            norm_w, norm_h = dx - 2*pad, dy - header_h - 2*pad
            if norm_w < 4 or norm_h < 4:
                continue

            subfolders = pickle.loads(compression.zstd.decompress(self.raw_data[path]['subfolders']))
            if self.search_data:
                subfolders = [x for x in subfolders if x['p'] in self.search_data]

            files = []
            if level > 0 and not self.search_data:
                sizes: list[float] = [x['s'] for x in subfolders]
            else:
                files = pickle.loads(compression.zstd.decompress(self.raw_data[path]['files']))
                if self.search_data:
                    files = [x for x in files if x['p'] in self.search_data]
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

            if level > 0 and not self.search_data:
                continue
            
            for rect, file in zip(files_rects, files):
                rx, ry, rdx, rdy = rect['x'], rect['y'], rect['dx'], rect['dy']
                
                if rdx > CULLING_SIZE_PX and rdy > CULLING_SIZE_PX:
                    f_rgb = color_cache.get_color_rgb_and_text(file['s'], self.global_max_log)
                    r, g, b = f_rgb
                    brightness = (r * 299 + g * 587 + b * 114) / 1000
                    text_color = "black" if brightness > 128 else "white"
                    rix, riy, ridx, ridy = int(rx), int(ry), int(rdx), int(rdy)
                    
                    rects.append((riy, riy+ridy, rix, rix+ridx, r, g, b))
                    
                    if rdx > 40 and rdy > 30:
                        max_chars = int(rdx / 10)
                        name = file['n']
                        dname = name if len(name) <= max_chars else name[:max_chars] + "..."

                        texts.append((rx+4, ry+3, dname, text_color, None))
                    
                    hit_map.append((rx, ry, rx+rdx, ry+rdy, file['p'], name, file['s'], False, True))
        end_time = time.perf_counter()
        return end_time - start_time

    def _update_canvas(self, pil_image: Image.Image, hit_map: list[tuple[float, float, float, float, str, str, float, bool, bool]]):
        self.hit_map = hit_map
        self.current_tk_image = ImageTk.PhotoImage(pil_image)
        self.highlight_rect_id = None
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.current_tk_image) # pyright: ignore[reportUnknownMemberType]

    def on_mouse_move(self, event: Any):
        mx = self.canvas.canvasx(event.x) # type: ignore
        my = self.canvas.canvasy(event.y) # type: ignore
        
        found = None
        for i in range(len(self.hit_map) - 1, -1, -1):
            item = self.hit_map[i]
            if item[0] <= mx <= item[2] and item[1] <= my <= item[3]:
                found = item
                break
        
        if not getattr(self, 'tooltip_text', None) or self.canvas.type(self.tooltip_text) is None:
            self.tooltip_bg = self.canvas.create_rectangle(0, 0, 0, 0, fill="#2b2b2b", outline="#a0a0a0", state="hidden")
            self.tooltip_text = self.canvas.create_text(0, 0, text="", anchor="nw", fill="white", font=("Arial", 10), state="hidden")

        if found:
            name, size_str = found[5], format_bytes(found[6])
            current_root_size = self.raw_data[self.current_root]['s'] or 1
            pct = (found[6] / current_root_size * 100)
            is_file = found[8]
            type_label = "Файл" if is_file else "Папка"
            if found[7]: type_label = "Группа"
            
            x1, y1, x2, y2 = found[0], found[1], found[2], found[3]
            
            # Обводка
            if self.highlight_rect_id and self.canvas.type(self.highlight_rect_id):
                self.canvas.coords(self.highlight_rect_id, x1, y1, x2, y2) # pyright: ignore[reportUnknownMemberType]
            else:
                self.highlight_rect_id = self.canvas.create_rectangle(x1, y1, x2, y2, outline="white", width=2)
            self.canvas.tag_raise(self.highlight_rect_id) # Обводка выше карты

            # Тултип
            tooltip_str = f"[{type_label}] {name}\n{size_str} | {pct:.1f}%"
            offset_x, offset_y = 15, 15
            
            self.canvas.itemconfigure(self.tooltip_text, text=tooltip_str, state="normal")
            self.canvas.coords(self.tooltip_text, mx + offset_x, my + offset_y) # type: ignore
            
            bbox = self.canvas.bbox(self.tooltip_text)
            if bbox:
                pad = 4
                self.canvas.coords(self.tooltip_bg, bbox[0]-pad, bbox[1]-pad, bbox[2]+pad, bbox[3]+pad) # pyright: ignore[reportUnknownMemberType]
                self.canvas.itemconfigure(self.tooltip_bg, state="normal")
            
            self.canvas.tag_raise(self.tooltip_bg) 
            self.canvas.tag_raise(self.tooltip_text)

            # Статус бар снизу
            self.status_bar.configure(text=f"[{type_label}] {name} | {size_str} | {pct:.1f}%") # pyright: ignore[reportUnknownMemberType]

        else:
            if self.highlight_rect_id: 
                self.canvas.delete(self.highlight_rect_id)
                self.highlight_rect_id = None
            
            self.canvas.itemconfigure(self.tooltip_text, state="hidden")
            self.canvas.itemconfigure(self.tooltip_bg, state="hidden")
            
            self.status_bar.configure(text="Ready") # pyright: ignore

    def on_left_click(self, event: Any):
        mx, my = event.x, event.y
        for i in range(len(self.hit_map) - 1, -1, -1):
            item = self.hit_map[i]
            if item[0] <= mx <= item[2] and item[1] <= my <= item[3]:
                path, is_dummy, is_file = item[4], item[7], item[8]
                if path and not is_dummy and not is_file and path in self.raw_data:
                    self.change_directory(path)
                return

    def on_right_click(self, event: Any):
        mx, my = event.x, event.y
        for i in range(len(self.hit_map) - 1, -1, -1):
            item = self.hit_map[i]
            if item[0] <= mx <= item[2] and item[1] <= my <= item[3]:
                self.selected_item = item
                try:
                    self.context_menu.tk_popup(event.x_root, event.y_root)
                finally:
                    self.context_menu.grab_release()
                return

    def copy_path(self):
        if self.selected_item and self.selected_item[4]:
            self.clipboard_clear(); self.clipboard_append(self.selected_item[4])

    def copy_name(self):
        if self.selected_item:
            self.clipboard_clear(); self.clipboard_append(self.selected_item[5])

    def return_to_analyzer(self):
        set_should_run_analyzer(True)
        self.destroy()
