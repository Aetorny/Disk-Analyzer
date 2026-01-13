import customtkinter as ctk
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

from logic import Database
from config import DATA_DIR, set_should_run_analyzer, SETTINGS, PLATFORM, TRANSLATOR
from utils import ColorCache, format_bytes, update_language, render_pipeline
from ui import LoaderFrame, SettingsWindow

_ = TRANSLATOR.gettext('visualizer')


color_cache = ColorCache(SETTINGS['color_map']['current'])

ctk.set_appearance_mode(SETTINGS['theme']['current'])
ctk.set_default_color_theme('blue')


class DiskVisualizerApp(ctk.CTk):
    def __init__(self, databases: dict[str, Database], icon_path: str):
        super().__init__() # pyright: ignore[reportUnknownMemberType]

        global _
        _ = TRANSLATOR.gettext('visualizer')

        self.title(_("Disk Visualizer"))
        self.geometry("1200x900")

        # Создаем меню
        self.create_menu()

        self.raw_data: Database
        self.databases = databases
        self.icon_path = icon_path
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
        self._data_lock = threading.Lock()
        self._search_workers = 0
        
        # GUI
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Панель вверху
        self.top_frame = ctk.CTkFrame(self, height=40)
        self.top_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5) # pyright: ignore[reportUnknownMemberType]
        
        self.btn_return_to_analyzer = ctk.CTkButton(self.top_frame, text="⬅", width=30, fg_color="red", command=self.return_to_analyzer)
        self.btn_return_to_analyzer.pack(side="left", padx=(5, 2)) # pyright: ignore[reportUnknownMemberType]

        self.btn_up = ctk.CTkButton(self.top_frame, text="⬆ "+_("Up"), width=60, command=self.go_up_level, state="disabled")
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

        self.status_bar = ctk.CTkLabel(self, text=_("Program is ready"), anchor="w", height=25, font=("Arial", 14))
        self.status_bar.grid(row=2, column=0, sticky="ew", padx=5) # pyright: ignore[reportUnknownMemberType]

        self.context_menu = Menu(self, tearoff=0)
        if PLATFORM == 'Windows':
            self.context_menu.add_command(label=_("Open in Explorer"), command=self.open_in_explorer)
        self.context_menu.add_command(label=_("Copy path"), command=self.copy_path)
        self.context_menu.add_command(label=_("Copy name"), command=self.copy_name)
        self.selected_item = None

        self.tooltip_bg = self.canvas.create_rectangle(0, 0, 0, 0, fill="#2b2b2b", outline="#a0a0a0", state="hidden")
        self.tooltip_text = self.canvas.create_text(0, 0, text="", anchor="nw", fill="white", font=("Arial", 10), state="hidden")

        logging.info('UI успешно инициализирован')

        self.refresh_file_list()
        self.after(1000, self.trigger_render)

    def toggle_search_bar(self, *_args: Any) -> None:
        self.is_search_bar_active = not self.is_search_bar_active
        if self.is_search_bar_active:
            self.search_loader = LoaderFrame(self.top_frame, 30, 30)
            self.search_loader.pack(side="right") # pyright: ignore[reportUnknownMemberType]
            self.search_entry = ctk.CTkEntry(
                self.top_frame,
                textvariable=self.search_var,
                placeholder_text=_("Search"),
                width=250
            )
            self.search_entry.pack() # pyright: ignore[reportUnknownMemberType]
            self.search_entry.focus()
        else:
            self.hide_search_bar(None)

    def hide_search_bar(self, *_args: Any) -> None:
        if self.search_entry:
            self.search_entry.destroy()
            self.search_loader.destroy()
            self.is_search_bar_active = False
            self.search_var = ctk.StringVar(value="")
            self.search_var.trace_add("write", self.on_search)
        self.search_data = set()
        threading.Thread(target=self._cancel_search_thread, daemon=True).start()

    def create_menu(self):
        """Создает меню приложения"""
        # Получаем основное окно (которое использует tk.Tk)
        menubar = Menu(self)
        self.config(menu=menubar)
        
        # Меню "Меню"
        menu_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label=_("Menu"), menu=menu_menu)
        menu_menu.add_command(label=_("Settings"), command=self.open_settings)
        
        # Меню "Справка"
        help_menu = Menu(menubar, tearoff=0)
        menubar.add_cascade(label=_("Help"), menu=help_menu)
        help_menu.add_command(label=_("About"), command=self.show_about)

    def open_settings(self):
        """Открывает окно редактирования настроек с современным интерфейсом"""
        lang_map = {'en': 'English', 'ru': 'Русский'}
        
        self.is_inverted_theme = True if SETTINGS['color_map']['current'].endswith('_r') else False

        config_list = [
            {
                "label": _("Language:"),
                "options": SETTINGS['language']['available'],
                "current": SETTINGS['language']['current'],
                "display_map": lang_map,
                "callback": self.on_language_changed
            },
            {
                "label": _("Theme:"),
                "options": SETTINGS['theme']['available'],
                "current": SETTINGS['theme']['current'],
                "callback": self.on_theme_changed
            },
            {
                "label": _("Color scheme:"),
                "options": SETTINGS['color_map']['available'],
                "current": SETTINGS['color_map']['current'],
                'display_map': {
                    en: _(en) for en in SETTINGS['color_map']['available']
                },
                "callback": self.on_color_map_change
            },
            {
                "label": _("Invert color scheme:"),
                "options": [_("Yes"), _("No")],
                "current": _("Yes") if self.is_inverted_theme else _("No"),
                "callback": self.on_invert_theme_change
            },
            {
                'label': _("Visualize Type:"),
                'options': SETTINGS['visualize_type']['available'],
                'current': SETTINGS['visualize_type']['current'],
                'display_map': {en: _(en) for en in SETTINGS['visualize_type']['available']},
                'callback': self.on_visualize_type
            }
        ]

        SettingsWindow(
            parent=self,
            settings_config=config_list,
            gettext=TRANSLATOR.gettext('visualizer'),
            icon_path=self.icon_path
        )

    def on_visualize_type(self, visualize_type: str):
        SETTINGS['visualize_type']['current'] = visualize_type
        SETTINGS.save()
        logging.info(f"Тип визуализации изменен на: {visualize_type}")
        self.after(0, self.trigger_render)

    def on_update_language(self):
        if SETTINGS['language']['current'] == 'en':
            return
        update_language(SETTINGS['language']['current'])
        TRANSLATOR.change_language(SETTINGS['language']['current'])
        self.show_pop_up_after_change_language([
            "Loading complete",
            "You must restart the application\nto apply the changes"
        ])

    def on_theme_changed(self, theme: str):
        """Обработчик изменения режима отображения"""
        SETTINGS['theme']['current'] = theme
        SETTINGS.save()
        ctk.set_appearance_mode(theme)
        logging.info(f"Режим отображения изменен на: {theme}")

    def on_restart(self):
        set_should_run_analyzer(True)
        self.destroy()

    def show_pop_up_after_change_language(self, text: list[str]) -> None:
        pop_up = ctk.CTkToplevel(self)
        pop_up.title(TRANSLATOR.gettext('visualizer')(text[0]))
        pop_up.geometry("350x150")
        pop_up.resizable(False, False)
        pop_up.grab_set()
        label = ctk.CTkLabel(pop_up, text=TRANSLATOR.gettext('visualizer')(text[1]), font=("Arial", 18))
        label.pack(pady=(20, 10)) # pyright: ignore[reportUnknownMemberType]
        button = ctk.CTkButton(pop_up, text=TRANSLATOR.gettext('visualizer')("Restart"), font=("Arial", 20), command=self.on_restart, fg_color="#991b1b", height=40)
        button.pack(fill="x", padx=20, pady=(0, 20)) # pyright: ignore[reportUnknownMemberType]

    def on_language_changed(self, language: str):
        """Обработчик изменения языка"""
        SETTINGS['language']['current'] = language
        SETTINGS.save()
        if not TRANSLATOR.change_language(language):
            self.on_update_language()
            return

        self.show_pop_up_after_change_language([
            "Restart required",
            "You must restart the application\nto apply the changes"
        ])

    def on_invert_theme_change(self, value: str):
        """Обработчик изменения инвертирования цветовой схемы"""
        self.is_inverted_theme = True if value == _("Yes") else False
        if SETTINGS['color_map']['current'] in SETTINGS['color_map']['custom']:
            return
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
        about_window.after(200, lambda: about_window.iconbitmap(self.icon_path)) # type: ignore
        
        # Основная информация о программе
        title_label = ctk.CTkLabel(about_window, text="Disk Analyzer", font=("Arial", 18, "bold"))
        title_label.pack(pady=(20, 10)) # pyright: ignore[reportUnknownMemberType]
        
        info_label = ctk.CTkLabel(
            about_window, 
            text=_("Program for analyzing and visualizing\ndisk space usage"),
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
            text=_("Close"), 
            command=about_window.destroy,
            fg_color="#3b3b3b",
            height=40
        )
        close_button.pack(fill="x", padx=20, pady=(0, 20)) # pyright: ignore[reportUnknownMemberType]

    def _cancel_search_thread(self):
        self._search_workers += 100
        while self._search_lock.locked() and self._search_workers > 1:
            time.sleep(0.1)
        self.search_data = set()
        self._search_workers = 0
        self.after(0, self.trigger_render)

    def _on_search_thread(self) -> None:
        if self._search_lock.locked():
            time.sleep(0.1)
        if self._search_workers > 1:
            self._search_workers -= 1
            return
        if not self._search_lock.acquire(blocking=False):
            return
        self.search_data = set()
        temp_data: set[str] = set()
        self.search_loader.start()
        try:
            search_str = self.search_var.get().strip().lower()
            for path in self.raw_data:
                if path.startswith('__'): continue
                with self._data_lock:
                    data = self.raw_data[path]
                for folder in pickle.loads(compression.zstd.decompress(data['subfolders'])):
                    if self._search_workers > 1: return
                    if search_str in folder['n'].lower():
                        current = folder['p']
                        while current != self.scan_root_path:
                            temp_data.add(current)
                            current = os.path.dirname(current)
                for file in pickle.loads(compression.zstd.decompress(data['files'])):
                    if self._search_workers > 1: return
                    if search_str in file['n'].lower():
                        current = file['p']
                        while current != self.scan_root_path:
                            temp_data.add(current)
                            current = os.path.dirname(current)
            temp_data.add(self.scan_root_path)
        finally:
            if self._search_workers == 1:
                self.search_data = temp_data
                self.after(0, self.trigger_render)
            self._search_lock.release()
            self._search_workers -= 1

    def on_search(self, *_args: Any) -> None:
        search_str = self.search_var.get().strip().lower()
        if search_str == '':
            self.search_data = set()
            threading.Thread(target=self._cancel_search_thread, daemon=True).start()
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
            self.restart_app_label = ctk.CTkLabel(self.canvas_frame, text=_("Data in folder ") + DATA_DIR + "\nnot found\nAdd files and restart the program", font=("Arial", 20))
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

    def on_resize(self, _event: Any):
        if self._resize_job: self.after_cancel(self._resize_job)
        self._resize_job = self.after(100, self.trigger_render) # Чуть быстрее реакция

    def trigger_render(self):
        if not self.current_root: return
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        
        logging.info('Запуск пайплайна отрисовки')
        threading.Thread(target=self._render_pipeline, args=(w, h), daemon=True).start()

    def _render_pipeline(self, width: int, height: int):
        '''
        Пайплайн отрисовки
        '''
        if not self._render_lock.acquire(blocking=False):
            return

        try:
            image, hit_map = render_pipeline(
                SETTINGS['visualize_type']['current'],
                width, height,
                self.current_root,
                self.raw_data,
                color_cache,
                self.global_max_log,
                self.search_data,
                True if SETTINGS['color_map']['current'] == 'Nesting' else False,
                self._data_lock
            )
            self.after(0, lambda: self._update_canvas(image, hit_map))
        finally:
            self._render_lock.release()
            logging.info('Пайплайн отрисовки завершён')

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
            with self._data_lock:
                current_root_size = self.raw_data[self.current_root]['s'] or 1
            pct = (found[6] / current_root_size * 100)
            is_file = found[8]
            type_label = _("File") if is_file else _("Folder")
            if found[7]: type_label = _("Group")
            
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
            
            self.status_bar.configure(text=_("Program is ready")) # pyright: ignore

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

    def open_in_explorer(self):
        if self.selected_item and self.selected_item[4]:
            path = self.selected_item[4]
            if self.selected_item[8]:
                path = os.path.dirname(path)
            os.startfile(path)

    def copy_path(self):
        if self.selected_item and self.selected_item[4]:
            self.clipboard_clear(); self.clipboard_append(self.selected_item[4])

    def copy_name(self):
        if self.selected_item:
            self.clipboard_clear(); self.clipboard_append(self.selected_item[5])

    def return_to_analyzer(self):
        set_should_run_analyzer(True)
        self.destroy()
