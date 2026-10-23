import time
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ..config import data_dir
from ..osutils import open_path, show_in_folder
from ..registry import CATEGORIES, category, registry, title
from . import theme as t
from .widgets import (Dialog, Popover, accent_button, ask_yes_no, caption, entry, label, make_clickable, message,
                      mono_label, outline_button, separator)

STATUS = {"done": ("ГОТОВО", t.SUCCESS), "error": ("ОШИБКА", t.ERROR)}


class Page(ctk.CTkScrollableFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=t.MAIN, corner_radius=0, scrollbar_button_color=t.BORDER,
                         scrollbar_button_hover_color=t.BORDER_BTN)
        self.app = app
        self.body = None

    def reset(self):
        if self.body is not None:
            self.body.destroy()
        self.body = ctk.CTkFrame(self, fg_color=t.MAIN)
        self.body.pack(fill="both", expand=True, padx=28, pady=22)
        return self.body


class HistoryPage(Page):
    LIMIT = 100

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.refresh()

    def refresh(self):
        b = self.reset()
        head = ctk.CTkFrame(b, fg_color=t.MAIN)
        head.pack(fill="x")
        label(head, "История", 22, weight="bold").pack(side="left")
        outline_button(head, "Очистить историю", self.clear, width=170, size=12,
                       image=t.ui_icon("trash", "muted", 16), compound="left").pack(side="right")
        items = self.app.history.items
        label(b, f"Последние конвертации: {len(items)}", 13, t.MUTED).pack(anchor="w", pady=(2, 14))
        table = ctk.CTkFrame(b, fg_color=t.CARD, corner_radius=t.RADIUS, border_width=1, border_color=t.BORDER)
        table.pack(fill="x")
        table.grid_columnconfigure(1, weight=1)
        table.grid_columnconfigure(2, weight=1)
        for c, text in enumerate(["ВРЕМЯ", "ИСХОДНЫЙ ФАЙЛ", "РЕЗУЛЬТАТ", "СТАТУС", ""]):
            caption(table, text, size=10).grid(row=0, column=c, sticky="w", padx=12, pady=(10, 6))
        if not items:
            mono_label(table, "История пуста", 12).grid(row=1, column=0, columnspan=5, pady=24)
        for r, it in enumerate(items[: self.LIMIT], start=1):
            self.row(table, r, it)

    def row(self, table, r, it):
        mono_label(table, time.strftime("%d.%m %H:%M", time.localtime(it["time"])), 11).grid(
            row=r, column=0, sticky="w", padx=12, pady=3)
        src = Path(it["source"])
        cell = ctk.CTkFrame(table, fg_color="transparent")
        cell.grid(row=r, column=1, sticky="w", padx=12)
        ctk.CTkLabel(cell, text="", image=t.get_icon(src.suffix, 20)).pack(side="left", padx=(0, 6))
        label(cell, short(src.name), 12).pack(side="left")
        res = Path(it["result"]) if it.get("result") else None
        cell = ctk.CTkFrame(table, fg_color="transparent")
        cell.grid(row=r, column=2, sticky="w", padx=12)
        if res:
            ctk.CTkLabel(cell, text="", image=t.get_icon(res.suffix, 20)).pack(side="left", padx=(0, 6))
            label(cell, short(res.name), 12).pack(side="left")
        else:
            label(cell, short(it.get("message", "")), 11, t.MUTED).pack(side="left")
        text, color = STATUS.get(it["status"], (it["status"].upper(), t.MUTED))
        ctk.CTkLabel(table, text=text, font=t.mono(11, "bold"), text_color=color).grid(row=r, column=3, sticky="w", padx=12)
        btns = ctk.CTkFrame(table, fg_color="transparent")
        btns.grid(row=r, column=4, sticky="e", padx=8, pady=2)
        if res:
            open_btn = outline_button(btns, "", lambda: self.open(res), width=t.H,
                                      image=t.ui_icon("external-link", "muted", 16))
            open_btn.pack(side="left", padx=2)
            folder_btn = outline_button(btns, "", lambda: show_in_folder(res), width=t.H,
                                        image=t.ui_icon("folder-open", "muted", 16))
            folder_btn.pack(side="left", padx=2)
            hint(open_btn, "Открыть")
            hint(folder_btn, "Показать в папке")

    def open(self, path):
        if not open_path(path):
            message(self, "Файл не найден", f"Не удалось открыть {path.name}. Возможно, файл перемещён или удалён.",
                    "error")

    def clear(self):
        if ask_yes_no(self, "Очистить историю", "Удалить все записи истории? Сами файлы не удаляются.", "Очистить"):
            self.app.history.clear()
            self.refresh()


def hint(widget, text):
    widget.bind("<Enter>", lambda e: Popover(widget, text, timeout=1500), add="+")


def short(text, n=26):
    return text if len(text) <= n else text[: n - 10] + "..." + text[-7:]


class SettingsPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.refresh()

    def refresh(self):
        b = self.reset()
        label(b, "Настройки", 22, weight="bold").pack(anchor="w")
        label(b, "Изменения сохраняются сразу.", 13, t.MUTED).pack(anchor="w", pady=(2, 14))

        caption(b, "РЕЗУЛЬТАТ И ПОВЕДЕНИЕ").pack(anchor="w", pady=(6, 8))
        box = self.card(b)
        self.app.build_params(box)

        caption(b, "ДВИЖКИ").pack(anchor="w", pady=(20, 8))
        box = self.card(b)
        self.path_row(box, "LibreOffice", "libreoffice_path", "libreoffice", "soffice.exe")
        self.path_row(box, "Tesseract", "tesseract_path", "tesseract", "tesseract.exe")
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", pady=(10, 0))
        accent_button(row, "Найти заново", self.rescan, width=160, size=13).pack(anchor="w")
        mono_label(row, "Поиск: папка engines, PATH, Program Files, путь из настроек", 11,
                   wraplength=420, justify="left").pack(anchor="w", pady=(4, 6))
        for name, title_, ok in self.app.engines.status():
            line = ctk.CTkFrame(box, fg_color="transparent")
            line.pack(fill="x", pady=1)
            ctk.CTkLabel(line, text="найден" if ok else "не найден", font=t.mono(11, "bold"), width=90, anchor="w",
                         text_color=t.SUCCESS if ok else t.ERROR).pack(side="left")
            p = self.app.engines.path(name)
            mono_label(line, f"{title_}  {p if p else ''}", 11, wraplength=330, justify="left").pack(side="left")

        caption(b, "ЧАСТЫЕ КОНВЕРТАЦИИ").pack(anchor="w", pady=(20, 8))
        box = self.card(b)
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x")
        label(row, "Счётчики и закреплённые плитки на главной странице", 13, wraplength=420,
              justify="left").pack(anchor="w")
        outline_button(row, "Сбросить статистику", self.reset_stats, width=190, size=12).pack(anchor="w", pady=(8, 0))

        caption(b, "ДАННЫЕ ПРОГРАММЫ").pack(anchor="w", pady=(20, 8))
        box = self.card(b)
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x")
        mono_label(row, str(data_dir()), 11, wraplength=420, justify="left").pack(anchor="w")
        outline_button(row, "Открыть папку", lambda: open_path(data_dir()), width=140, size=12).pack(anchor="w", pady=(8, 0))

    def card(self, parent):
        outer = ctk.CTkFrame(parent, fg_color=t.CARD, corner_radius=t.RADIUS, border_width=1, border_color=t.BORDER)
        outer.pack(fill="x")
        inner = ctk.CTkFrame(outer, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)
        return inner

    def path_row(self, parent, name, key, engine, exe):
        caption(parent, f"ПУТЬ К {name.upper()}", color=t.MUTED, size=10).pack(anchor="w", pady=(6, 4))
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x")
        e = entry(row, f"Автоматически ({exe})", width=200)
        value = self.app.settings.get(key)
        if value:
            e.insert(0, value)
        e.pack(side="left", fill="x", expand=True)

        def save(_e=None):
            self.app.settings.set(key, e.get().strip())

        e.bind("<FocusOut>", save)
        e.bind("<Return>", save)

        def browse():
            path = filedialog.askopenfilename(title=f"Где находится {exe}", filetypes=[(exe, exe), ("Программы", "*.exe")])
            if path:
                e.delete(0, "end")
                e.insert(0, path)
                save()

        outline_button(row, "Обзор", browse, width=90, size=12).pack(side="left", padx=(8, 0))

    def rescan(self):
        self.focus_set()
        self.app.rescan_engines()
        self.refresh()

    def reset_stats(self):
        if ask_yes_no(self, "Сбросить статистику", "Счётчики и закреплённые плитки будут сброшены.", "Сбросить"):
            self.app.stats.reset()
            self.app.refresh_home()


class AllConversions(Dialog):
    """Полный список конвертаций с поиском и группировкой по типу исходного файла."""

    def __init__(self, app):
        super().__init__(app, "Все конвертации", width=640)
        self.app = app
        self.query = ctk.StringVar()
        e = entry(self.body, "Поиск: например, pdf или jpg в png", width=620, textvariable=self.query)
        e.pack(fill="x")
        self.list = ctk.CTkScrollableFrame(self.body, fg_color=t.MAIN, width=620, height=440,
                                           scrollbar_button_color=t.BORDER)
        self.list.pack(fill="both", expand=True, pady=(12, 0))
        self.all = registry.all_conversions(app.engines)
        self.query.trace_add("write", lambda *a: self.fill())
        self.fill()
        self.buttons("Закрыть", None)
        self.after(150, e.focus_set)

    def fill(self):
        for w in self.list.winfo_children():
            w.destroy()
        q = self.query.get().lower().replace(" в ", " ").split()
        shown = 0
        for key, cname in CATEGORIES:
            items = [c for c in self.all if category(c.src) == key and self.match(c, q)]
            if not items:
                continue
            caption(self.list, cname.upper()).pack(anchor="w", pady=(10, 4))
            by_src = {}
            for c in items:
                by_src.setdefault(c.src, []).append(c)
            for src, convs in by_src.items():
                row = ctk.CTkFrame(self.list, fg_color=t.CARD, corner_radius=t.RADIUS)
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text="", image=t.get_icon(src, 24)).pack(side="left", padx=(10, 6), pady=8)
                label(row, src.upper(), 13, weight="bold", width=50, anchor="w").pack(side="left")
                wrap = ctk.CTkFrame(row, fg_color="transparent")
                wrap.pack(side="left", fill="x", expand=True, padx=6, pady=6)
                for i, c in enumerate(convs):
                    b = ctk.CTkButton(wrap, text=c.dst.upper(), width=56, height=t.H - 8, corner_radius=t.RADIUS,
                                      fg_color=t.BAR, hover_color=t.ACCENT, text_color=t.TEXT, font=t.mono(11, "bold"),
                                      border_width=1, border_color=t.BORDER_BTN,
                                      command=lambda c=c: self.pick(c))
                    b.grid(row=i // 8, column=i % 8, padx=2, pady=2)
                shown += 1
                if shown > 60:
                    return
        if shown == 0:
            mono_label(self.list, "Ничего не найдено", 12).pack(pady=20)

    @staticmethod
    def match(c, q):
        if not q:
            return True
        # "jpg png" понимаем как "из JPG в PNG"
        if len(q) == 2 and c.src.startswith(q[0]) and c.dst.startswith(q[1]):
            return True
        hay = f"{c.src} {c.dst} {title(c.src)} {title(c.dst)} {c.engine_label}".lower()
        if len(q) == 2:
            return q[0] in f"{c.src} {title(c.src)}".lower() and q[1] in f"{c.dst} {title(c.dst)}".lower()
        return all(w in hay for w in q)

    def pick(self, conv):
        self.ok(None)
        self.app.pick_and_convert(conv.src, conv.dst)
