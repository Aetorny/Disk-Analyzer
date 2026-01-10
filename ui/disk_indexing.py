import customtkinter as ctk
from tkinter import filedialog, Menu

import os
import time
import logging
import threading
from typing import Optional

from config import set_should_run_visualizer, SETTINGS
from logic import SizeFinder, Database, is_root
from utils import format_bytes, create_database, delete_database, format_date_to_time_ago


ctk.set_appearance_mode(SETTINGS['appearence_mode']['current'])
ctk.set_default_color_theme('blue')


class DiskIndexingApp(ctk.CTk):
    def __init__(self, databases: dict[str, Database]):
        super().__init__() # pyright: ignore[reportUnknownMemberType]

        self.title("Выбор путей для анализа")
        self.geometry("400x500")
        
        # Создаем меню
        self.create_menu()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Переменная для хранения текущего сканера
        self.current_size_finder = None
        self.is_scanning = False
        self.run_result = None

        # Заголовок
        self.label = ctk.CTkLabel(self, text="Выберите пути для сканирования:", font=("Arial", 16, "bold"))
        self.label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew") # pyright: ignore[reportUnknownMemberType]

        # Контейнер для списка пути
        self.scrollable_frame = ctk.CTkScrollableFrame(self, label_text="Доступные пути")
        self.scrollable_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew") # pyright: ignore[reportUnknownMemberType]
        self.scrollable_frame.grid_columnconfigure(0, weight=1)

        # Получаем пути и создаем чекбоксы
        self.paths = sorted(databases.keys())
        self.databases = databases
        self.check_vars: dict[str, ctk.BooleanVar] = {} 
        
        self.paths_frames: dict[str, tuple[ctk.CTkFrame, ctk.CTkLabel, ctk.CTkButton]] = {}
        self.find_files = 0
        self.db_check_threads: list[threading.Thread] = []
        if not self.paths:
            error_label = ctk.CTkLabel(self.scrollable_frame, text="Пути не найдены!")
            error_label.grid(row=0, column=0, padx=10, pady=10) # pyright: ignore[reportUnknownMemberType]
            path_row = 1
        else:
            # Создаем фрейм для пути с переключателем для каждого пути для сканирования и кнопкой удаления
            for idx, path in enumerate(self.paths):
                path_frame = ctk.CTkFrame(self.scrollable_frame)
                path_frame.grid(row=idx, column=0, padx=10, pady=(0, 10), sticky="ew") # pyright: ignore[reportUnknownMemberType]
                path_frame.grid_columnconfigure(0, weight=1)

                var = ctk.BooleanVar(value=False)
                self.check_vars[path] = var
                chk = ctk.CTkSwitch(path_frame, text=path, variable=var)
                chk.grid(row=0, column=0, padx=0, pady=0, sticky="w") # pyright: ignore[reportUnknownMemberType]
                
                # Кнопка удаления
                delete_button = ctk.CTkButton(path_frame, text="✕", width=30, fg_color="#d9534f", hover_color="#c9302c", command=lambda p=path: self.remove_scanned_db(p))
                delete_button.grid(row=0, column=1, padx=(10, 0), pady=0) # pyright: ignore[reportUnknownMemberType]
                
                # Лейбл для даты
                date_label = ctk.CTkLabel(path_frame, text="", text_color="gray")
                date_label.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="w") # pyright: ignore[reportUnknownMemberType]
                
                self.paths_frames[path] = (path_frame, date_label, delete_button)
                
                self.db_check_threads.append(
                    threading.Thread(target=self.check_db_if_already_scanned, args=(path, delete_button, date_label), daemon=True)
                )
                self.db_check_threads[-1].start()

            path_row = len(self.paths)
        
        # Кнопка для сканирования произвольной папки
        self.scan_folder_button = ctk.CTkButton(self.scrollable_frame, text="Сканировать конкретную папку...", command=self.scan_custom_folder, fg_color="#3b3b3b")
        self.scan_folder_button.grid(row=path_row, column=0, padx=10, pady=(10, 10), sticky="ew") # pyright: ignore[reportUnknownMemberType]

        # Прогресс бар
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="ew") # pyright: ignore[reportUnknownMemberType]
        self.progress_bar.set(0) # pyright: ignore[reportUnknownMemberType]
        self.progress_bar.grid_remove()
        
        # Лейбл для отображения процентов/состояния
        self.status_label = ctk.CTkLabel(self, text="")
        self.status_label.grid(row=3, column=0, padx=20, pady=(0, 5)) # pyright: ignore[reportUnknownMemberType]
        self.status_label.grid_remove()

        # Кнопка запуска
        self.start_button = ctk.CTkButton(self, text="Начать анализ", command=self.start_scan)
        self.start_button.grid(row=4, column=0, padx=20, pady=20, sticky="ew") # pyright: ignore[reportUnknownMemberType]
        
        if not self.paths:
            self.start_button.configure(state="disabled") # pyright: ignore[reportUnknownMemberType]

        # Кнопка для досрочного завершения (скрыта по умолчанию)
        self.abort_button = ctk.CTkButton(self, text="Прервать", command=self.abort_scan_and_dont_run_visualizer, fg_color="#d9534f")
        self.abort_button.grid(row=5, column=0, padx=20, pady=(0, 20), sticky="ew") # pyright: ignore[reportUnknownMemberType]
        self.abort_button.grid_remove()

        # Кнопка запуска визуализации (показывается только если есть файлы)
        self.visualize_button = ctk.CTkButton(self, text="Запустить визуализацию", command=self.abort_scan, fg_color="#4caf50")
        self.visualize_button.grid(row=6, column=0, padx=20, pady=(0, 20), sticky="ew") # pyright: ignore[reportUnknownMemberType]
        threading.Thread(target=self.update_visualize_button, daemon=True).start()

        # Обработка закрытия окна (останавливает сканирование)
        try:
            self.protocol("WM_DELETE_WINDOW", self.on_close) # pyright: ignore[reportUnknownMemberType]
        except Exception:
            pass

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
        appearance_label = ctk.CTkLabel(settings_container, text="Режим отображения:", font=("Arial", 13))
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
            text_color="#0066cc"
        )
        github_link.pack(side="left", padx=5) # pyright: ignore[reportUnknownMemberType]
        
        # Кнопка закрытия
        close_button = ctk.CTkButton(
            about_window, 
            text="Закрыть", 
            command=about_window.destroy,
            fg_color="#3b3b3b",
            height=40
        )
        close_button.pack(fill="x", padx=20, pady=(0, 20)) # pyright: ignore[reportUnknownMemberType]

    def check_db_if_already_scanned(self, path_name: str, delete_button: ctk.CTkButton, date_label: ctk.CTkLabel):
        '''
        Добавляет дату последнего сканирования
        Если её нет, то убирает кнопку удаления
        '''
        date = self.databases[path_name].get('__date__')
        if date:
            date_label.configure(text=f"Посл. скан.: {format_date_to_time_ago(date)}") # pyright: ignore[reportUnknownMemberType]
            self.find_files += 1
        else:
            date_label.destroy()
            delete_button.destroy()

    def update_visualize_button(self) -> None:
        for t in self.db_check_threads:
            while t.is_alive():
                time.sleep(0.1)
        if self.find_files == 0:
            self.visualize_button.grid_remove()
        self.db_check_threads = []

    def remove_scanned_db(self, path: str):
        """
        Удаляет просканированную базу данных
        """
        db = self.databases[path]
        db_is_open = db.is_open
        if db_is_open:
            db.close()
        delete_database(db.path)
        self.find_files -= 1
        self.update_visualize_button()
        if not is_root(path):
            del self.databases[path]
            self.paths_frames[path][0].destroy()
            del self.paths_frames[path]
            return
        if db_is_open:
            db.open()
        self.paths_frames[path][1].destroy()
        self.paths_frames[path][2].destroy()

    def scan_custom_folder(self):
        """Открывает диалог выбора папки и сканирует её"""
        folder_path = filedialog.askdirectory(title="Выберите папку для сканирования")
        
        if not folder_path:
            return
        
        folder_path = os.path.abspath(folder_path)

        # Создаем новую базу данных для выбранной папки
        new_db = create_database(folder_path)

        self.databases[folder_path] = new_db

        self.start_scan(folder_path)

    def start_scan(self, custom_path: Optional[str] = None):
        if custom_path:
            selected_paths = [custom_path]
        else:
            selected_paths = [path for path, var in self.check_vars.items() if var.get()]

        if not selected_paths:
            self.label.configure(text="Выберите хотя бы один путь!", text_color="red") # pyright: ignore[reportUnknownMemberType]
            return

        # Блокируем интерфейс
        self.label.configure(text="Идет сканирование...", text_color=("black", "white")) # pyright: ignore[reportUnknownMemberType]
        self.start_button.configure(state="disabled", text="Пожалуйста, подождите...") # pyright: ignore[reportUnknownMemberType]
        for child in self.scrollable_frame.winfo_children():
            if isinstance(child, ctk.CTkSwitch):
                child.configure(state="disabled") # pyright: ignore[reportUnknownMemberType]

        # Настраиваем прогресс бар
        self.progress_bar.grid() # pyright: ignore[reportUnknownMemberType]
        self.status_label.grid() # pyright: ignore[reportUnknownMemberType]
        self.progress_bar.configure(mode="determinate") # pyright: ignore[reportUnknownMemberType]
        self.progress_bar.set(0) # pyright: ignore[reportUnknownMemberType]

        self.is_scanning = True
        
        # Запускаем поток логики
        threading.Thread(target=self.run_logic, args=(selected_paths,), daemon=True).start()
        # Показываем кнопку прерывания
        self.abort_button.grid() # pyright: ignore[reportUnknownMemberType]
        
        # Запускаем цикл проверки прогресса в главном потоке
        self.update_progress_loop()

    def update_progress_loop(self):
        """Проверяет состояние SizeFinder каждые 0.1 сек"""
        if not self.is_scanning:
            return

        if self.current_size_finder:
            total = self.current_size_finder.total
            current = self.current_size_finder.current
            
            # Избегаем деления на ноль
            if total > 0:
                progress = current / total
                self.progress_bar.set(progress) # pyright: ignore[reportUnknownMemberType]
                self.status_label.configure(text=f"Обработано: {format_bytes(current)} / {format_bytes(total)} ({int(progress*100)}%)") # pyright: ignore[reportUnknownMemberType]
            else:
                # Если total еще не подсчитан или равен 0
                self.progress_bar.set(0) # pyright: ignore[reportUnknownMemberType]
                self.status_label.configure(text=f"Подсчет файлов... {format_bytes(current)}") # pyright: ignore[reportUnknownMemberType]

        # Планируем следующий вызов через 100 мс
        self.after(100, self.update_progress_loop)

    def run_logic(self, paths: list[str]):
        try:
            for path in paths:
                # Сохраняем экземпляр в self, чтобы update_progress_loop мог его видеть
                self.current_size_finder = SizeFinder(self.databases[path], path)
                
                # Обновляем текст в главном потоке (опционально)
                self.label.configure(text=f"Сканирование: {path}") # pyright: ignore[reportUnknownMemberType]

                self.run_result = self.current_size_finder.run()
            
            self.is_scanning = False
            self.after(0, self.on_scan_finished)
        except Exception as e:
            self.is_scanning = False
            logging.error(f"Ошибка при сканировании: {e}")
            self.after(0, lambda: self.label.configure(text=f"Ошибка", text_color="red")) # pyright: ignore[reportUnknownMemberType]

    def abort_scan_and_dont_run_visualizer(self):
        set_should_run_visualizer(False)
        self.abort_scan()

    def abort_scan(self):
        """Прерывает текущее сканирование, установив флаг is_running в False."""
        # Останавливаем активный SizeFinder
        if self.current_size_finder:
            self.current_size_finder.is_running = False

        # Обновляем состояние UI
        if self.is_scanning:
            self.label.configure(text="Сканирование прервано", text_color="red") # pyright: ignore[reportUnknownMemberType]
            self.status_label.configure(text="Остановка...") # pyright: ignore[reportUnknownMemberType]
        self.abort_button.configure(state="disabled") # pyright: ignore[reportUnknownMemberType]
        self.is_scanning = False

        threading.Thread(target=self.wait_for_scan_to_finish, daemon=True).start()

    def wait_for_scan_to_finish(self):
        '''
        Ожидание завершения досрочного сканирования
        '''

        while self.is_scanning:
            time.sleep(0.1)
        
        self.after(0, self.on_scan_finished)

    def on_scan_finished(self):
        self.destroy() 

    def on_close(self):
        set_should_run_visualizer(False)
        self.is_scanning = False
        if self.current_size_finder:
            self.current_size_finder.is_running = False
        self.destroy()
