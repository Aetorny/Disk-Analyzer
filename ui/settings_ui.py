import customtkinter as ctk

from typing import Any, Callable


class SettingsWindow(ctk.CTkToplevel):
    def __init__(
            self,
            parent: ctk.CTk,
            settings_config: list[dict[str, Any]],
            gettext: Callable[..., str],
            title: str = "Settings",
            icon_path: str | None = None,
            *args: list[Any], **kwargs: Any):
        """
        Универсальное окно настроек.
        """
        super().__init__(parent, *args, **kwargs) # pyright: ignore[reportUnknownMemberType]
        global _
        _ = gettext
        
        self.settings_config = settings_config
        self.icon_path = icon_path
        
        # Настройка окна
        self.title(_(title))
        self.geometry("450x350") # Чуть увеличим высоту на случай множества опций
        self.resizable(False, False)
        self.grab_set()
        
        if self.icon_path:
            self.after(200, self._update_icon)
            
        self._create_ui()

    def _update_icon(self):
        self.iconbitmap(self.icon_path) # pyright: ignore[reportUnknownMemberType]

    def _create_ui(self):
        # Заголовок
        title_label = ctk.CTkLabel(self, text=self.title(), font=("Arial", 18, "bold"))
        title_label.pack(padx=20, pady=(20, 20)) # pyright: ignore[reportUnknownMemberType]
        
        # Скролл-контейнер (на случай, если настроек будет много)
        self.settings_container = ctk.CTkScrollableFrame(self)
        self.settings_container.pack(fill="both", expand=True, padx=20, pady=(0, 10)) # pyright: ignore[reportUnknownMemberType]
        self.settings_container.grid_columnconfigure(1, weight=1)
        
        # Генерация полей настроек в цикле
        for idx, item in enumerate(self.settings_config):
            self._add_setting_row(idx, item)

        # Кнопка закрытия
        close_button = ctk.CTkButton(
            self, 
            text=_("Close"), 
            command=self.destroy,
            fg_color="#3b3b3b",
            height=40
        )
        close_button.pack(fill="x", padx=20, pady=(0, 20)) # pyright: ignore[reportUnknownMemberType]

    def _add_setting_row(self, row_idx: int, config: dict[str, Any]):
        """Добавляет одну строку с настройкой"""
        label_text = config.get("label", "Option")
        options = config.get("options", [])
        current_value = config.get("current")
        callback = config.get("callback")
        display_map = config.get("display_map", {}) # Маппинг {internal_val: display_name}

        # 1. Метка (Label)
        label = ctk.CTkLabel(self.settings_container, text=label_text, font=("Arial", 13))
        label.grid(row=row_idx, column=0, sticky="w", pady=(0, 15)) # pyright: ignore[reportUnknownMemberType]

        # 2. Подготовка значений для ComboBox
        # Если есть display_map, показываем красивые имена, иначе сами значения
        display_values = [display_map.get(opt, opt) for opt in options]
        
        # Определяем, что показать сейчас
        current_display = display_map.get(current_value, current_value)

        # 3. ComboBox
        combo = ctk.CTkComboBox(
            self.settings_container,
            values=display_values,
            state="readonly",
            # Используем замыкание (closure), чтобы захватить текущие данные
            command=lambda val: self._on_combo_change(val, options, display_values, callback)
        )
        combo.set(current_display)
        combo.grid(row=row_idx, column=1, sticky="ew", pady=(0, 15), padx=(20, 0)) # pyright: ignore[reportUnknownMemberType]

    def _on_combo_change(self, selected_display_value: str, original_options: list[str], display_values: list[str], callback: Callable[..., Any] | None):
        """
        Обрабатывает выбор.
        Находит оригинальное (техническое) значение по выбранному (отображаемому) тексту.
        """
        if not callback:
            return

        try:
            index = display_values.index(selected_display_value)
            internal_value = original_options[index]
            callback(internal_value)
        except ValueError:
            pass
