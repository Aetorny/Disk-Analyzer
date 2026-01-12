import customtkinter as ctk

import logging
import tkinter as tk
from typing import Any


class LoaderFrame(ctk.CTkFrame):
    def __init__(self, master: ctk.CTk, width: int, height: int, **kwargs: dict[Any, Any]):
        super().__init__(master, width=width, height=height, **kwargs) # type: ignore
        
        self.target_color = self._get_canvas_color(kwargs.get("fg_color", "transparent")) # type: ignore

        self.canvas = tk.Canvas(
            self, 
            bg=self.target_color, 
            highlightthickness=0,
            width=width,
            height=height
        )
        self.canvas.place(relx=0.5, rely=0.5, anchor="center")

        self.angle = 0
        self.is_running = False
        self.animation_id = None

    def _get_canvas_color(self, color_arg: str | None):
        if color_arg == "transparent" or color_arg is None:
            try:
                parent_color = self.master.cget("fg_color")
                return self._apply_appearance_mode(parent_color)
            except Exception as e:
                logging.error("Can't get parent color. Error: " + str(e))
                return self._apply_appearance_mode("#242424")
        else:
            return self._apply_appearance_mode(color_arg)

    def start(self):
        if not self.is_running:
            self.is_running = True
            self.animate()

    def stop(self):
        self.is_running = False
        if self.animation_id:
            self.after_cancel(self.animation_id)
        self.canvas.delete("all")

    def animate(self):
        if not self.is_running:
            return

        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        
        if w < 1: w = float(self.cget("width")) # type: ignore
        if h < 1: h = float(self.cget("height")) # type: ignore

        self.canvas.delete("all")
        
        padding = 30 
        
        self.canvas.create_arc( # pyright: ignore[reportUnknownMemberType]
            padding, padding, w - padding, h - padding,
            start=self.angle,
            extent=280,
            style="arc",
            width=12, 
            outline="#3B8ED0" 
        )

        self.angle -= 15
        if self.angle <= -360:
            self.angle = 0

        self.animation_id = self.after(20, self.animate)
