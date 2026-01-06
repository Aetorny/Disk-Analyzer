import customtkinter as ctk

import time
import logging
import threading

from config import set_should_run_visualizer
from logic import SizeFinder, Database
from ui import format_bytes


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class DiskIndexingApp(ctk.CTk):
    def __init__(self, databases: dict[str, Database]):
        super().__init__() # pyright: ignore[reportUnknownMemberType]

        self.title("Выбор дисков для анализа")
        self.geometry("400x500")
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Переменная для хранения текущего сканера
        self.current_size_finder = None
        self.is_scanning = False
        self.run_result = None

        # Заголовок
        self.label = ctk.CTkLabel(self, text="Выберите диски для сканирования:", font=("Arial", 16, "bold"))
        self.label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew") # pyright: ignore[reportUnknownMemberType]

        # Контейнер для списка дисков
        self.scrollable_frame = ctk.CTkScrollableFrame(self, label_text="Доступные диски")
        self.scrollable_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew") # pyright: ignore[reportUnknownMemberType]
        self.scrollable_frame.grid_columnconfigure(0, weight=1)

        # Получаем диски и создаем чекбоксы
        self.disks = sorted(databases.keys())
        self.databases = databases
        self.check_vars: dict[str, ctk.BooleanVar] = {} 
        
        if not self.disks:
            error_label = ctk.CTkLabel(self.scrollable_frame, text="Диски не найдены!")
            error_label.grid(row=0, column=0, padx=10, pady=10) # pyright: ignore[reportUnknownMemberType]
        else:
            for idx, disk in enumerate(self.disks):
                var = ctk.BooleanVar(value=False)
                self.check_vars[disk] = var
                chk = ctk.CTkSwitch(self.scrollable_frame, text=disk, variable=var)
                threading.Thread(target=self.add_date_info, args=(disk, chk), daemon=True).start()
                chk.grid(row=idx, column=0, padx=10, pady=(0, 10), sticky="w") # pyright: ignore[reportUnknownMemberType]

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
        
        if not self.disks:
            self.start_button.configure(state="disabled") # pyright: ignore[reportUnknownMemberType]

        # Кнопка для досрочного завершения (скрыта по умолчанию)
        self.abort_button = ctk.CTkButton(self, text="Прервать", command=self.abort_scan_and_dont_run_visualizer, fg_color="#d9534f")
        self.abort_button.grid(row=5, column=0, padx=20, pady=(0, 20), sticky="ew") # pyright: ignore[reportUnknownMemberType]
        self.abort_button.grid_remove()

        # Кнопка запуска визуализации (показывается только если есть .data файлы)
        self.visualize_button = ctk.CTkButton(self, text="Запустить визуализацию", command=self.abort_scan, fg_color="#4caf50")
        self.visualize_button.grid(row=6, column=0, padx=20, pady=(0, 20), sticky="ew") # pyright: ignore[reportUnknownMemberType]

        # Обработка закрытия окна (останавливает сканирование)
        try:
            self.protocol("WM_DELETE_WINDOW", self.on_close) # pyright: ignore[reportUnknownMemberType]
        except Exception:
            pass

    def add_date_info(self, disk_name: str, chk: ctk.CTkSwitch):
        date = self.databases[disk_name].get('__date__')
        if date:
            chk.configure(text=f"{disk_name}\t(Посл. скан.: {date})") # pyright: ignore[reportUnknownMemberType]

    def start_scan(self):
        selected_disks = [disk for disk, var in self.check_vars.items() if var.get()]

        if not selected_disks:
            self.label.configure(text="Выберите хотя бы один диск!", text_color="red") # pyright: ignore[reportUnknownMemberType]
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
        threading.Thread(target=self.run_logic, args=(selected_disks,), daemon=True).start()
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

    def run_logic(self, disks: list[str]):
        try:
            for disk in disks:
                # Сохраняем экземпляр в self, чтобы update_progress_loop мог его видеть
                self.current_size_finder = SizeFinder(self.databases[disk], disk)
                
                # Обновляем текст в главном потоке (опционально)
                self.label.configure(text=f"Сканирование диска: {disk}") # pyright: ignore[reportUnknownMemberType]
                
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
