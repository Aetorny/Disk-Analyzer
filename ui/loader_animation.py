import customtkinter as ctk
import tkinter as tk

close = False

class MinimalLoader(ctk.CTk):
    def __init__(self):
        super().__init__() # pyright: ignore[reportUnknownMemberType]

        # Настройки окна
        self.geometry("200x200")
        self.resizable(False, False)
        self.title("") # Убираем текст заголовка
        
        # Устанавливаем цвет фона окна и холста одинаковым
        self.bg_color = "#242424" 
        self.configure(fg_color=self.bg_color) # pyright: ignore[reportUnknownMemberType]

        # Создаем Canvas на всё окно
        self.canvas = tk.Canvas(
            self, 
            bg=self.bg_color, 
            highlightthickness=0 # Убираем белую рамку
        )
        self.canvas.pack(fill="both", expand=True)

        # Переменные анимации
        self.angle = 0
        self.after(50, self.animate) # Задержка перед стартом для корректной отрисовки

    def animate(self):
        # Получаем текущие размеры окна, чтобы рисовать по центру
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        
        # Если окно еще не отрисовалось, используем дефолтные значения
        if w < 1: w = 200
        if h < 1: h = 200

        self.canvas.delete("all")

        # Отступы от краев окна
        padding = 30
        
        # Рисуем дугу
        self.canvas.create_arc( # pyright: ignore[reportUnknownMemberType]
            padding, padding, w - padding, h - padding,
            start=self.angle,
            extent=280,   # Длина дуги (почти круг)
            style="arc",
            width=12,     # Толщина линии
            outline="#3B8ED0" # Цвет (стандартный синий CTk)
        )

        # Вращение
        self.angle -= 15
        if self.angle <= -360:
            self.angle = 0

        if close:
            self.destroy()

        self.after(20, self.animate)


def run_app():
    app = MinimalLoader()
    app.mainloop() # pyright: ignore[reportUnknownMemberType]
