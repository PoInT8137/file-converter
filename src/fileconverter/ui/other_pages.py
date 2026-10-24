import time
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ..config import data_dir
from ..osutils import open_path, show_in_folder
from ..registry import CATEGORIES, category, registry, title
from . import theme as t
from .widgets import (Dialog, Popover, on_event, accent_button, ask_yes_no, caption, entry, label, make_clickable, message,
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
    # строки из CTk-виджетов дорогие, поэтому показываем порциями
    STEP = 20

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.shown = 0
        self.signature = None
        self.refresh()

    def refresh(self, force=False):
        items = self.app.history.items
        signature = (len(items), items[0]["time"] if items else 0)
        if not force and signature == self.signature:
            return
        self.signature = signature
        b = self.reset()
        head = ctk.CTkFrame(b, fg_color=t.MAIN)
        head.pack(fill="x")
        label(head, "История", 22, weight="bold").pack(side="left")
        outline_button(head, "Очистить историю", self.clear, width=170, size=12,
                       image=t.ui_icon("trash", "muted", 16), compound="left").pack(side="right")
        label(b, f"Последние конвертации: {len(items)}", 13, t.MUTED).pack(anchor="w", pady=(2, 14))
        table = ctk.CTkFrame(b, fg_color=t.CARD, corner_radius=t.RADIUS, border_width=1, border_color=t.BORDER)
        table.pack(fill="x")
        # время под исходным файлом, статус под результатом: так таблица помещается и в узком окне
        table.grid_columnconfigure(0, weight=1, uniform="names")
        table.grid_columnconfigure(1, weight=1, uniform="names")
        for c, text in enumerate(["ИСХОДНЫЙ ФАЙЛ", "РЕЗУЛЬТАТ"]):
            caption(table, text, size=10).grid(row=0, column=c, sticky="w", padx=12, pady=(10, 6))
        if not items:
            mono_label(table, "История пуста", 12).grid(row=1, column=0, columnspan=4, pady=24)
        self.table = table
        self.shown = 0
        self.more = None
        self.show_more()

    def show_more(self):
        items = self.app.history.items
        start, end = self.shown, min(self.shown + self.STEP, len(items))
        for r in range(start, end):
            self.row(self.table, r + 1, items[r])
        self.shown = end
        if self.more is not None:
            self.more.destroy()
            self.more = None
        rest = len(items) - self.shown
        if rest > 0:
            self.more = outline_button(self.body, f"Показать ещё {min(rest, self.STEP)}", self.show_more, width=200,
                                       size=12)
            self.more.pack(anchor="w", pady=(10, 0))

    def row(self, table, r, it):
        top, bottom = 2 * r - 1, 2 * r
        # иконка и имя одной меткой: каждый CTk-виджет дорогой, а строк много
        src = Path(it["source"])
        ctk.CTkLabel(table, text=" " + short(src.name), image=t.get_icon(src.suffix, 20), compound="left",
                     font=t.font(12), text_color=t.TEXT, anchor="w", justify="left", wraplength=150).grid(
            row=top, column=0, sticky="w", padx=12, pady=(6, 0))
        mono_label(table, time.strftime("%d.%m %H:%M", time.localtime(it["time"])), 10).grid(
            row=bottom, column=0, sticky="w", padx=(38, 12), pady=(0, 6))
        res = Path(it["result"]) if it.get("result") else None
        if res:
            ctk.CTkLabel(table, text=" " + short(res.name), image=t.get_icon(res.suffix, 20), compound="left",
                         font=t.font(12), text_color=t.TEXT, anchor="w", justify="left", wraplength=150).grid(
                row=top, column=1, sticky="w", padx=12, pady=(6, 0))
        else:
            label(table, short(it.get("message", ""), 60), 11, t.MUTED, anchor="w", justify="left",
                  wraplength=150).grid(row=top, column=1, sticky="w", padx=12, pady=(6, 0))
        text, color = STATUS.get(it["status"], (it["status"].upper(), t.MUTED))
        ctk.CTkLabel(table, text=text, font=t.mono(10, "bold"), text_color=color, anchor="w").grid(
            row=bottom, column=1, sticky="w", padx=(12, 12), pady=(0, 6))
        if res:
            open_btn = outline_button(table, "", lambda: self.open(res), width=t.H,
                                      image=t.ui_icon("external-link", "muted", 16))
            open_btn.grid(row=top, column=2, rowspan=2, padx=(8, 2), pady=4)
            folder_btn = outline_button(table, "", lambda: show_in_folder(res), width=t.H,
                                        image=t.ui_icon("folder-open", "muted", 16))
            folder_btn.grid(row=top, column=3, rowspan=2, padx=(2, 8), pady=4)
            hint(open_btn, "Открыть")
            hint(folder_btn, "Показать в папке")

    def open(self, path):
        if not open_path(path):
            message(self, "Файл не найден", f"Не удалось открыть {path.name}. Возможно, файл перемещён или удалён.",
                    "error")

    def clear(self):
        if ask_yes_no(self, "Очистить историю", "Удалить все записи истории? Сами файлы не удаляются.", "Очистить"):
            self.app.history.clear()
            self.refresh(force=True)


def hint(widget, text):
    widget.bind("<Enter>", on_event(lambda e: Popover(widget, text, timeout=1500)), add="+")


def short(text, n=40):
    return text if len(text) <= n else text[: n - 10] + "..." + text[-7:]


class SettingsPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.refresh()

    def refresh(self):
        b = self.reset()
        self.path_entries = {}
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

        # сохраняем при каждом изменении: FocusOut не приходит, если сразу нажать кнопку или уйти в другой раздел
        e.bind("<KeyRelease>", save)
        e.bind("<FocusOut>", save)
        e.bind("<Return>", save)
        self.path_entries[key] = e

        def browse():
            path = filedialog.askopenfilename(title=f"Где находится {exe}", filetypes=[(exe, exe), ("Программы", "*.exe")])
            if path:
                e.delete(0, "end")
                e.insert(0, path)
                save()

        outline_button(row, "Обзор", browse, width=90, size=12).pack(side="left", padx=(8, 0))

    def rescan(self):
        for key, e in self.path_entries.items():
            self.app.settings.set(key, e.get().strip())
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
        e = entry(self.body, "Поиск: например, pdf или jpg в png", width=620)
        e.pack(fill="x")
        self.entry = e
        self.list = ctk.CTkScrollableFrame(self.body, fg_color=t.MAIN, width=620, height=440,
                                           scrollbar_button_color=t.BORDER)
        self.list.pack(fill="both", expand=True, pady=(12, 0))
        self.all = registry.all_conversions(app.engines)
        # строки создаются один раз и порциями, поиск только прячет и показывает готовые
        self.plan = []
        for key, cname in CATEGORIES:
            by_src = {}
            for c in self.all:
                if category(c.src) == key:
                    by_src.setdefault(c.src, []).append(c)
            if by_src:
                self.plan.append(("caption", cname, list(by_src)))
                self.plan += [("row", src, convs) for src, convs in by_src.items()]
        self.widgets = []
        self.empty = mono_label(self.list, "Ничего не найдено", 12)
        e.bind("<KeyRelease>", on_event(lambda ev: self.fill()))
        self.buttons("Закрыть", None)
        self.build_some()
        self.after(150, e.focus_set)

    def build_some(self):
        try:
            for _ in range(4):
                if len(self.widgets) >= len(self.plan):
                    return
                kind, name, data = self.plan[len(self.widgets)]
                if kind == "caption":
                    self.widgets.append((kind, caption(self.list, name.upper()), data))
                else:
                    self.widgets.append((kind, self.make_row(name, data), data))
            self.fill()
            self.after(15, self.build_some)
        except Exception:
            pass

    def make_row(self, src, convs):
        row = ctk.CTkFrame(self.list, fg_color=t.CARD, corner_radius=t.RADIUS)
        ctk.CTkLabel(row, text="", image=t.get_icon(src, 24)).pack(side="left", padx=(10, 6), pady=8)
        label(row, src.upper(), 13, weight="bold", width=50, anchor="w").pack(side="left")
        wrap = ctk.CTkFrame(row, fg_color="transparent")
        wrap.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        row.chips = []
        for c in convs:
            b = ctk.CTkButton(wrap, text=c.dst.upper(), width=56, height=t.H - 8, corner_radius=t.RADIUS,
                              fg_color=t.BAR, hover_color=t.ACCENT, text_color=t.TEXT, font=t.mono(11, "bold"),
                              border_width=1, border_color=t.BORDER_BTN, command=lambda c=c: self.pick(c))
            row.chips.append((c, b))
        return row

    def fill(self):
        q = self.entry.get().lower().replace(" в ", " ").split()
        visible_src = set()
        for kind, w, data in self.widgets:
            w.pack_forget()
        for kind, w, data in self.widgets:
            if kind == "caption":
                continue
            n = 0
            for c, b in w.chips:
                if self.match(c, q):
                    b.grid(row=n // 8, column=n % 8, padx=2, pady=2)
                    n += 1
                else:
                    b.grid_remove()
            w.visible = n > 0
            if n:
                visible_src.add(data[0].src)
        self.empty.pack_forget()
        for kind, w, data in self.widgets:
            if kind == "caption":
                if any(s in visible_src for s in data):
                    w.pack(anchor="w", pady=(10, 4))
            elif w.visible:
                w.pack(fill="x", pady=2)
        if not visible_src and len(self.widgets) >= len(self.plan):
            self.empty.pack(pady=20)

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
