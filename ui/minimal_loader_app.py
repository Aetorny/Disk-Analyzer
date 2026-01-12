import customtkinter as ctk

from ui import LoaderFrame


close = False


class MinimalLoader(ctk.CTk):
    def __init__(self):
        super().__init__() # type: ignore

        self.geometry("200x200")
        self.resizable(False, False)
        self.title("") 
        
        self.configure(fg_color="#242424") # pyright: ignore[reportUnknownMemberType]

        self.loader_widget = LoaderFrame(self, width=200, height=200, fg_color="transparent") # type: ignore
        self.loader_widget.pack(fill="both", expand=True) # pyright: ignore[reportUnknownMemberType]

        self.loader_widget.start()

        self.after(10, self.wait)
    
    def wait(self):
        while not close:
            self.after(10, self.wait)
            return

        self.loader_widget.stop()
        self.destroy()


def run_app():
    app = MinimalLoader()
    app.mainloop() # pyright: ignore[reportUnknownMemberType]
