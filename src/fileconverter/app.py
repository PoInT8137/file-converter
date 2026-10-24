import ctypes
import ctypes.wintypes
import gc
import os
import queue
import sys
import tempfile
import time
import traceback
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from . import __version__
from .config import Settings, assets_dir, data_dir
from .engines.finder import Engines
from .jobs import JobQueue
from .registry import FORMATS, ALIASES, registry, title
from .stats import History, Stats
from .tools import SECTION_TITLES, TOOLS, TOOLS_BY_ID
from .osutils import show_in_folder
from .ui import motion
from .ui import theme as t
from .ui.convert_page import ConvertPage
from .ui.other_pages import AllConversions, HistoryPage, SettingsPage
from .ui.overlays import CommandPalette, EnginesPanel, Overlay
from .ui.queue_panel import QueuePanel
from .ui.tools_page import ToolsPage
from .ui.widgets import (Dot, on_event, FieldsDialog, Flow, Popover, Toasts, ask_yes_no, caption, checkbox, entry,
                         mono_label, message, outline_button, segmented, separator)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_BASE = TkinterDnD.DnDWrapper
except Exception:
    TkinterDnD = None
    DND_FILES = None
    DND_BASE = object

SECTIONS = [
    ("convert", "Конвертация", "arrow-left-right"),
    ("pdf", "Инструменты PDF", "file-text"),
    ("images", "Изображения", "image"),
    ("media", "Аудио и видео", "clapperboard"),
    ("ocr", "Распознавание", "scan-text"),
    None,
    ("history", "История", "rotate-ccw-clock"),
    ("settings", "Настройки", "settings"),
]
SECTION_NAMES = {s[0]: s[1] for s in SECTIONS if s}
# Ctrl+1 ... Ctrl+7 в порядке разделов
HOTKEYS = {key: str(n) for n, key in enumerate(SECTION_NAMES, 1)}
GROUPS = {"convert": "ФАЙЛЫ", "pdf": "ИНСТРУМЕНТЫ"}
# окно уже этой ширины (в логических пикселях): меню только значками, очередь уже
COMPACT_WIDTH = 1120
SIDE_WIDE, SIDE_COMPACT = 200, 60
QUEUE_WIDE, QUEUE_COMPACT = 290, 250
QUALITY = [("high", "Высокое"), ("medium", "Среднее"), ("low", "Низкое")]


def file_patterns(ext):
    exts = [ext] + [a for a, target in ALIASES.items() if target == ext]
    return " ".join(f"*.{e}" for e in exts)


class App(ctk.CTk, DND_BASE):
    def __init__(self, selftest=False):
        self.settings = Settings()
        t.apply_theme(self.settings.get("theme"))
        super().__init__(fg_color=t.BG)
        t.conceal(self)
        self.selftest = selftest
        # в самопроверке и тестах всё синхронно: анимации меняют порядок событий
        motion.enabled = bool(self.settings.get("animations")) and not selftest
        self.errors = []
        self.error_shown = False
        self.dnd_ok = False
        if TkinterDnD is not None:
            try:
                self.TkdndVersion = TkinterDnD._require(self)
                self.dnd_ok = True
            except Exception as e:
                self.errors_dnd = str(e)
        # сборка мусора только из главного потока, иначе объекты Tk могут удаляться из потоков задач
        gc.disable()
        self.gc_tick = 0
        t.reset_cache()
        t.load_fonts()
        self.title("File Converter")
        self.fit_to_screen()
        try:
            self.iconbitmap(default=str(assets_dir() / "app.ico"))
        except Exception:
            pass

        self.stats = Stats()
        self.history = History()
        self.engines = Engines(self.settings)
        self.jobs = JobQueue(self.engines, self.settings, self.stats, self.history)
        self.job_items = {}
        self.ui_calls = queue.Queue()
        self.pages = {}
        self.current = None
        self.current_key = None
        self.compact = None

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_header()
        self.body = ctk.CTkFrame(self, fg_color=t.BG, corner_radius=0)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(4, weight=1)
        self.body.grid_columnconfigure(0, minsize=SIDE_WIDE)
        self.body.grid_columnconfigure(2, minsize=QUEUE_WIDE)
        self.build_sidebar()
        separator(self.body, vertical=True).grid(row=0, column=1, sticky="ns")
        self.queue_panel = QueuePanel(self)
        self.queue_panel.grid(row=0, column=2, sticky="nsew")
        separator(self.body, vertical=True).grid(row=0, column=3, sticky="ns")
        self.content = ctk.CTkFrame(self.body, fg_color=t.MAIN, corner_radius=0)
        self.content.grid(row=0, column=4, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.transition = motion.PageTransition(self.content)
        self.palette = CommandPalette(self)
        # поле палитры: Ctrl+K ставит фокус сюда
        self.search = self.palette.entry
        self.engines_panel = EnginesPanel(self, self.engines_button)
        self.toasts = Toasts(self)
        self.update_engines_status()

        if self.dnd_ok:
            self.register_drop(self, self.add_files, self.on_drag)
        self.bind_all("<Control-KeyPress>", self.on_ctrl_key)
        # у полей ввода Tk своя комбинация Ctrl+K "удалить до конца строки", она срабатывает раньше bind_all
        for cls in ("Entry", "Text"):
            self.bind_class(cls, "<Control-Key-k>", self.on_ctrl_key)
            self.bind_class(cls, "<Control-Key-K>", self.on_ctrl_key)
        self.bind("<Escape>", on_event(lambda e: self.close_search()))
        self.bind("<Configure>", self.on_resize, add="+")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_section("convert")
        self.after(80, self.poll)

    def fit_to_screen(self):
        """Стартовый размер 1180x760, но не больше рабочей области экрана.

        CustomTkinter умножает размер на масштаб Windows: при 150% окно 1180x760 занимает 1770x1140
        и не помещается на экран 1920x1080.
        """
        scale = ctk.ScalingTracker.get_window_scaling(self) or 1.0
        left, top, width, height = 0, 0, self.winfo_screenwidth(), self.winfo_screenheight() - 48
        try:
            rect = ctypes.wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0):
                left, top, width, height = rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
        except Exception:
            pass
        # запас на рамку и заголовок окна
        w = max(600, min(1180, int(width / scale) - 16))
        h = max(400, min(760, int((height - 40) / scale)))
        self.minsize(min(940, w), min(600, h))
        x = left + max(0, int((width - w * scale) / 2))
        y = top + max(0, int((height - 40 - h * scale) / 2))
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _windows_set_titlebar_color(self, color_mode):
        """Цвет заголовка окна под тему без скрытия окна.

        CustomTkinter для этого прячет и снова показывает окно, при смене темы окно мигает.
        """
        if not self._window_exists:
            return super()._windows_set_titlebar_color(color_mode)
        value = ctypes.c_int(1 if color_mode.lower() == "dark" else 0)
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value)) != 0:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
            # SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
        except Exception:
            pass

    def report_callback_exception(self, exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb))
        self.errors.append(text)
        try:
            with open(data_dir() / "error.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S\n") + text + "\n")
        except OSError:
            pass
        # окно с ошибкой показываем один раз за сеанс и не изнутри poll, остальные ошибки только в error.log
        if not self.selftest and not self.error_shown:
            self.error_shown = True

            def show():
                try:
                    message(self, "Что-то пошло не так",
                            f"Внутренняя ошибка: {val}\nПодробности в error.log в папке данных.", "error")
                except Exception:
                    pass

            self.after(50, show)

    def build_header(self):
        head = ctk.CTkFrame(self, fg_color=t.BAR, corner_radius=0, height=56)
        head.grid(row=0, column=0, sticky="ew")
        head.grid_propagate(False)
        head.grid_rowconfigure(0, weight=1)
        head.grid_columnconfigure(1, weight=1)
        logo = ctk.CTkFrame(head, fg_color=t.BAR)
        logo.grid(row=0, column=0, padx=18, sticky="w")
        ctk.CTkLabel(logo, text="", image=t.ui_icon("arrow-left-right", "accent", 22)).pack(side="left")
        ctk.CTkLabel(logo, text="FILE CONVERTER", font=t.mono(14, "bold"), text_color=t.TEXT).pack(side="left", padx=10)

        # поле поиска в шапке только открывает палитру команд
        self.search_button = ctk.CTkButton(
            head, text="  Найти функцию или формат", anchor="w", width=340, height=36, corner_radius=t.RADIUS,
            fg_color=t.MAIN, hover_color=t.CARD, border_width=1, border_color=t.BORDER_BTN, text_color=t.MUTED,
            font=t.font(13), image=t.ui_icon("search", "muted", 16), compound="left",
            command=lambda: self.palette.toggle())
        self.search_button.grid(row=0, column=2, padx=(0, 10), sticky="e")
        mono_label(self.search_button, "Ctrl K", 10, t.MUTED, fg_color=t.CARD_SEL, corner_radius=4, height=20,
                   width=48).place(relx=1.0, x=-8, rely=0.5, anchor="e")

        self.engines_button = ctk.CTkButton(
            head, text="", width=40, height=36, corner_radius=t.RADIUS, fg_color="transparent",
            hover_color=t.CARD, border_width=1, border_color=t.BORDER, text_color=t.CAPTION, font=t.mono(11),
            command=lambda: self.engines_panel.toggle())
        self.engines_button.grid(row=0, column=3, padx=(0, 18), sticky="e")
        separator(self).grid(row=0, column=0, sticky="sew")

    def build_sidebar(self):
        side = ctk.CTkFrame(self.body, fg_color=t.BAR, corner_radius=0, width=SIDE_WIDE)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        side.pack_propagate(False)
        self.side = side
        self.nav = {}
        self.nav_captions = []
        bottom = [s for s in SECTIONS[SECTIONS.index(None) + 1:]]
        for s in SECTIONS[:SECTIONS.index(None)]:
            if s[0] in GROUPS:
                cap = caption(side, GROUPS[s[0]], color=t.MUTED, size=10)
                cap.pack(anchor="w", padx=20, pady=(16 if s[0] == "convert" else 14, 6))
                self.nav_captions.append((cap, GROUPS[s[0]]))
            self.nav_button(side, s).pack(fill="x", padx=10, pady=1)
        for s in reversed(bottom):
            self.nav_button(side, s).pack(side="bottom", fill="x", padx=10, pady=1)
        separator(side).pack(side="bottom", fill="x", padx=16, pady=8)
        # янтарная полоска у активного раздела, переезжает к выбранному пункту
        self.marker = ctk.CTkFrame(side, fg_color=t.ACCENT, corner_radius=2, width=3, height=20)
        self.marker_y = None
        side.bind("<Configure>", on_event(lambda e: self.after_idle(lambda: self.move_marker(False))), add="+")

    def nav_button(self, side, s):
        key, text, icon = s
        btn = ctk.CTkButton(side, text=text, anchor="w", height=t.H - 4, corner_radius=t.RADIUS,
                            fg_color="transparent", hover_color=t.CARD, text_color=t.MUTED, font=t.font(13),
                            image=t.ui_icon(icon, "muted", 18), compound="left",
                            command=lambda k=key: self.show_section(k))
        self.nav[key] = (btn, icon)
        state = {"job": None}

        def enter(_e):
            # подсказка с клавишей появляется, только если задержать курсор
            state["job"] = btn.after(700, lambda: Popover(btn, f"{text}    Ctrl+{HOTKEYS[key]}", below=True,
                                                          timeout=1800) if btn.winfo_exists() else None)

        def leave(_e):
            if state["job"]:
                btn.after_cancel(state["job"])
                state["job"] = None

        btn.bind("<Enter>", enter, add="+")
        btn.bind("<Leave>", leave, add="+")
        btn.bind("<ButtonPress-1>", leave, add="+")
        return btn

    def move_marker(self, animate=True):
        if self.current_key not in self.nav:
            return
        btn = self.nav[self.current_key][0]
        try:
            scale = ctk.ScalingTracker.get_widget_scaling(self.side)
            y = (btn.winfo_y() + btn.winfo_height() / 2) / scale - 10
        except Exception:
            return
        if btn.winfo_height() <= 1:
            return
        start = self.marker_y
        self.marker_y = y
        if not animate or start is None or start == y:
            self.marker.place(x=4, y=y)
            return

        def step(p):
            self.marker.place(x=4, y=start + (y - start) * p)

        motion.run(self.marker, "nav-marker", 200, step)

    def on_resize(self, event):
        if event.widget is not self:
            return
        scale = ctk.ScalingTracker.get_window_scaling(self) or 1.0
        self.set_compact(event.width / scale < COMPACT_WIDTH)

    def set_compact(self, compact):
        """Узкое окно: меню только значками, очередь уже. Подсказки с названием раздела остаются."""
        if compact == self.compact:
            return
        self.compact = compact
        side_w = SIDE_COMPACT if compact else SIDE_WIDE
        self.side.configure(width=side_w)
        self.body.grid_columnconfigure(0, minsize=side_w)
        self.body.grid_columnconfigure(2, minsize=QUEUE_COMPACT if compact else QUEUE_WIDE)
        self.queue_panel.configure(width=QUEUE_COMPACT if compact else QUEUE_WIDE)
        for key, (btn, icon) in self.nav.items():
            btn.configure(text="" if compact else SECTION_NAMES[key], anchor="center" if compact else "w")
        for cap, text in self.nav_captions:
            cap.configure(text="" if compact else text)
        self.after_idle(lambda: self.move_marker(False))

    def update_engines_status(self):
        status = self.engines.status()
        found = sum(1 for _, _, ok in status if ok)
        good = found == len(status) and self.dnd_ok
        btn = self.engines_button
        btn.configure(text=f"   Движки {found}/{len(status)}", width=40)
        if not hasattr(self, "engines_dot"):
            self.engines_dot = Dot(btn, t.SUCCESS, t.BAR)
            self.engines_dot.place(x=12, rely=0.5, anchor="w")
        self.engines_dot.set(t.SUCCESS if good else t.ACCENT)

    def show_section(self, key):
        self.close_search()
        previous = self.current_key
        for k, (btn, icon) in self.nav.items():
            on = k == key
            btn.configure(fg_color=t.CARD_SEL if on else "transparent", text_color=t.TEXT if on else t.MUTED,
                          image=t.ui_icon(icon, "accent" if on else "muted", 18))
        old = self.current
        page = self.pages.get(key)
        if page is None:
            if key == "convert":
                page = ConvertPage(self.content, self)
            elif key == "history":
                page = HistoryPage(self.content, self)
            elif key == "settings":
                page = SettingsPage(self.content, self)
            else:
                page = ToolsPage(self.content, self, key)
            self.pages[key] = page
        elif key in ("history", "settings"):
            page.refresh()
        elif isinstance(page, ToolsPage):
            page.refresh()
        elif key == "convert":
            sel = self.queue_panel.selected
            if len(sel) == 1 and page.item is not sel[0]:
                page.show_file(sel[0])
        self.current = page
        self.current_key = key
        if page is old:
            self.transition.finish()
            page.grid(row=0, column=0, sticky="nsew")
        else:
            self.transition.start(old, page, lambda p: p.grid(row=0, column=0, sticky="nsew"))
        self.move_marker(animate=previous is not None)

    def go_home(self):
        self.queue_panel.select([])
        self.pages["convert"].show_home()

    def refresh_home(self):
        page = self.pages.get("convert")
        if page is not None and page.item is None:
            page.show_home()

    def on_selection(self):
        sel = self.queue_panel.selected
        if self.current_key == "convert":
            page = self.pages["convert"]
            if len(sel) == 1:
                page.show_file(sel[0])
            elif not sel:
                page.show_home()
        elif isinstance(self.current, ToolsPage):
            self.current.refresh()
        elif self.current_key in ("history", "settings") and len(sel) == 1:
            self.show_section("convert")

    def register_drop(self, widget, func, on_drag=None):
        if not self.dnd_ok:
            return

        def handler(event):
            if on_drag:
                on_drag(False)
            try:
                paths = [p for p in self.tk.splitlist(event.data) if p]
            except Exception:
                paths = []
            if paths:
                self.after(10, lambda: func(paths))
            return event.action

        def drag(on):
            def f(event):
                on_drag(on)
                return event.action
            return f

        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", handler)
            if on_drag:
                widget.dnd_bind("<<DropEnter>>", drag(True))
                widget.dnd_bind("<<DropLeave>>", drag(False))
        except Exception:
            pass

    def on_drag(self, on):
        """Файлы несут над окном: зона перетаскивания на главной подсвечивается."""
        page = self.pages.get("convert")
        if page is not None:
            page.highlight_drop(on and self.current is page)

    def add_files(self, paths):
        files = []
        for p in paths:
            p = Path(p)
            if p.is_dir():
                files += [f for f in sorted(p.iterdir()) if f.is_file()][:200]
            elif p.is_file():
                files.append(p)
        items = self.queue_panel.add(files)
        if not items:
            return []
        if isinstance(self.current, ToolsPage):
            self.queue_panel.select(items)
            self.current.refresh()
        else:
            self.queue_panel.select([items[0]])
            if self.current_key != "convert":
                self.show_section("convert")
            self.pages["convert"].show_file(items[0])
        return items

    def all_filetypes(self):
        exts = sorted(set(registry.sources()))
        patterns = " ".join(file_patterns(e) for e in exts)
        return [("Поддерживаемые файлы", patterns), ("Все файлы", "*.*")]

    def pick_files(self):
        paths = filedialog.askopenfilenames(title="Выберите файлы", filetypes=self.all_filetypes())
        if paths:
            self.add_files(paths)

    def pick_and_convert(self, src, dst):
        paths = filedialog.askopenfilenames(
            title=f"Выберите файлы {src.upper()} для конвертации в {dst.upper()}",
            filetypes=[(f"{title(src)} ({src.upper()})", file_patterns(src)), ("Все файлы", "*.*")])
        if paths:
            self.convert_paths(paths, dst)

    def convert_paths(self, paths, dst):
        items = self.add_files(paths)
        if items:
            self.start_conversion(items, dst)

    def start_conversion(self, items, dst, batch=False):
        started, skipped = 0, []
        for item in items:
            if item.status in ("run", "wait"):
                continue
            conv = registry.get(item.ext, dst, self.engines)
            if conv is None:
                skipped.append(item.path.name)
                continue
            job, _ = self.jobs.convert(item.path, conv)
            self.job_items[job.id] = [item]
            item.jobs.append(job)
            item.status = "wait"
            self.queue_panel.refresh(item)
            started += 1
        if skipped and (not batch or not started):
            names = ", ".join(skipped[:5]) + (" и другие" if len(skipped) > 5 else "")
            self.toasts.show(f"Нельзя конвертировать в {dst.upper()}: {names}. Нет подходящего движка "
                             "или формат не поддерживается.", "error", timeout=7000)
        return started

    def run_tool(self, tool, items):
        params = {}
        if tool.fields:
            note = ""
            if tool.id == "pdf_meta" and items:
                from .engines.pdf import read_metadata
                meta = read_metadata(items[0].path)
                note = f"Сейчас: {meta.get('title') or 'без названия'}, автор: {meta.get('author') or 'не указан'}"
            params = FieldsDialog(self, tool.title, tool.fields, note).show()
            if params is None:
                return None
        job, _ = self.jobs.run_tool([i.path for i in items], tool, params)
        self.job_items[job.id] = list(items)
        for i in items:
            i.jobs.append(job)
            i.status = "wait"
            self.queue_panel.refresh(i)
        return job

    def cancel_item(self, item):
        if item.jobs:
            self.jobs.cancel(item.jobs[-1])

    def run_quick(self, tool_id, items):
        tool = TOOLS_BY_ID[tool_id]
        if not self.engines.available(tool.engine):
            message(self, tool.title, self.engines.describe(tool.engine if tool.engine != "ocr" else "tesseract"),
                    "error")
            return
        if len(items) < tool.min_files:
            self.show_section(tool.section)
            page = self.pages[tool.section]
            page.select(tool)
            Popover(page.run_btn, f"Выберите в очереди ещё файлы (нужно {tool.min_files}). Ctrl + клик добавляет к выбору.")
            return
        self.run_tool(tool, items)

    def show_all_conversions(self):
        AllConversions(self).show()

    def build_params(self, parent, on_change=None):
        s = self.settings

        def changed():
            if on_change:
                on_change()

        def title_row(text):
            caption(parent, text, color=t.MUTED, size=10).pack(anchor="w", pady=(8, 4))

        title_row("ПАПКА РЕЗУЛЬТАТА")
        folder = mono_label(parent, s.get("output_dir") or "рядом с исходным файлом", 12, t.CAPTION,
                            wraplength=420, justify="left")
        folder.pack(anchor="w")
        row = Flow(parent, bg=t.CARD)
        row.pack(fill="x", pady=(4, 0))

        def browse():
            path = filedialog.askdirectory(title="Папка для результатов")
            if path:
                s.set("output_dir", path)
                folder.configure(text=path)
                changed()

        def reset():
            s.set("output_dir", "")
            folder.configure(text="рядом с исходным файлом")
            changed()

        row.add(outline_button(row, "Выбрать папку", browse, width=40, size=12))
        row.add(outline_button(row, "Рядом с исходным", reset, width=40, size=12))

        title_row("КАЧЕСТВО КАРТИНОК")
        names = dict(QUALITY)
        var = ctk.StringVar(value=names.get(s.get("quality"), "Высокое"))

        def set_quality(value):
            s.set("quality", {v: k for k, v in QUALITY}[value])
            changed()

        segmented(parent, [n for _, n in QUALITY], var, set_quality).pack(anchor="w")

        title_row("ПОВЕДЕНИЕ")
        v1 = ctk.BooleanVar(value=bool(s.get("open_after")))
        v2 = ctk.BooleanVar(value=bool(s.get("delete_source")))
        checkbox(parent, "Открывать результат после конвертации", v1,
                 lambda: (s.set("open_after", v1.get()), changed())).pack(anchor="w")
        checkbox(parent, "Удалять исходный файл (перемещается в корзину)", v2,
                 lambda: (s.set("delete_source", v2.get()), changed())).pack(anchor="w")

        title_row("ШАБЛОН ИМЕНИ")
        e = entry(parent, "{name}", width=260)
        e.insert(0, s.get("name_template") or "{name}")
        e.pack(anchor="w")
        mono_label(parent, "{name} имя файла, {date} дата, {time} время. Пример: {name}_{date}", 11,
                   wraplength=420, justify="left").pack(anchor="w", pady=(4, 0))

        def save_template(_e=None):
            s.set("name_template", e.get().strip() or "{name}")
            changed()

        e.bind("<KeyRelease>", save_template)
        e.bind("<FocusOut>", save_template)
        e.bind("<Return>", save_template)

    def rescan_engines(self):
        self.engines.refresh()
        self.update_engines_status()
        for key in list(self.pages):
            if key not in ("settings", self.current_key):
                self.pages.pop(key).destroy()
        conv = self.pages.get("convert")
        if conv is not None:
            if conv.item is not None:
                conv.show_file(conv.item)
            else:
                conv.show_home()

    def call_soon(self, fn):
        self.ui_calls.put(fn)

    def poll(self):
        # ошибка в одном событии не должна останавливать весь цикл обновления окна
        try:
            self.gc_tick += 1
            if self.gc_tick % 25 == 0:
                gc.collect()
            for _ in range(200):
                try:
                    fn = self.ui_calls.get_nowait()
                except queue.Empty:
                    break
                self.safe(fn)
            for _ in range(200):
                try:
                    event = self.jobs.events.get_nowait()
                except queue.Empty:
                    break
                self.safe(lambda: self.handle_event(event))
        finally:
            try:
                self.after(80, self.poll)
            except Exception:
                pass

    def safe(self, fn):
        try:
            fn()
        except Exception:
            self.report_callback_exception(*sys.exc_info())

    def handle_event(self, event):
        kind, job = event[0], event[1]
        items = self.job_items.get(job.id, [])
        for item in items:
            if item.jobs and item.jobs[-1] is not job:
                continue
            item.status = job.status
            item.progress = job.progress
            if job.status == "done":
                item.outputs = job.outputs
            item.error = job.error
            self.queue_panel.refresh(item)
        if kind in ("log", "done"):
            conv = self.pages.get("convert")
            if conv is not None and conv.item in items and conv.item.jobs and conv.item.jobs[-1] is job:
                conv.show_log(job)
            if job.tool is not None:
                page = self.pages.get(job.tool.section)
                if page is not None:
                    page.show_log(job)
        if kind == "done":
            self.refresh_home()
            if not self.selftest:
                self.notify_done(job, items)

    def notify_done(self, job, items):
        """Сообщение в углу окна о готовом результате или ошибке. Несколько готовых подряд собираются в одно."""
        if job.status == "done" and job.outputs:
            first = job.outputs[0]
            recent = getattr(self, "done_toast", None)
            if recent is not None and recent[0] in self.toasts.items and time.time() - recent[2] < 3:
                toast, count = recent[0], recent[1] + 1
                toast.text.configure(text=f"Готово файлов: {count}")
                self.done_toast = (toast, count, time.time())
                return
            toast = self.toasts.show(f"Готово: {first.name}", "ok", ("Показать в папке", lambda: show_in_folder(first)))
            self.done_toast = (toast, 1, time.time())
        elif job.status == "error":
            name = items[0].path.name if items else "файл"

            def open_item():
                if items and items[0] in self.queue_panel.items:
                    self.queue_panel.click(items[0])
                    if self.current_key != "convert" and job.tool is None:
                        self.show_section("convert")

            self.toasts.show(f"Не получилось: {name}. {job.error or ''}".strip(), "error",
                             ("Подробности", open_item), timeout=7000)

    def on_ctrl_key(self, event):
        # коды клавиш не зависят от раскладки: 75 это K, 79 это O, 49..55 это цифры 1..7
        if event.keycode == 75:
            self.palette.open()
            return "break"
        if event.keycode == 79:
            self.pick_files()
            return "break"
        if 49 <= event.keycode < 49 + len(SECTION_NAMES):
            self.show_section(list(SECTION_NAMES)[event.keycode - 49])
            return "break"
        return None

    def default_commands(self):
        """Палитра без запроса: разделы с клавишами и частые действия."""
        items = [("Ctrl O", "Добавить файлы", self.pick_files),
                 ("СПИСОК", "Все конвертации", self.show_all_conversions)]
        for key, name in SECTION_NAMES.items():
            items.append((f"Ctrl {HOTKEYS[key]}", name, lambda k=key: self.show_section(k)))
        return items

    def search_items(self, text):
        q = text.lower().strip().replace(" в ", " ")
        if not q:
            return []
        words = q.split()
        results = []
        for s in SECTIONS:
            if s and q in s[1].lower():
                results.append(("РАЗДЕЛ", s[1], lambda k=s[0]: self.show_section(k)))
        for tool in TOOLS:
            hay = f"{tool.title} {tool.desc} {SECTION_TITLES[tool.section]}".lower()
            if all(w in hay for w in words):
                results.append((SECTION_TITLES[tool.section].upper(), tool.title,
                                lambda tl=tool: self.open_tool(tl)))
        for conv in registry.all_conversions(self.engines):
            if len(words) == 2 and conv.src.startswith(words[0]) and conv.dst.startswith(words[1]):
                results.append(("КОНВЕРТАЦИЯ", conv.label, lambda c=conv: self.pick_and_convert(c.src, c.dst)))
        if len(words) == 1 and (words[0] in FORMATS or words[0] in ALIASES):
            ext = ALIASES.get(words[0], words[0])
            for conv in registry.targets(ext, self.engines)[:6]:
                results.append(("КОНВЕРТАЦИЯ", conv.label, lambda c=conv: self.pick_and_convert(c.src, c.dst)))
            results.append(("ФОРМАТ", f"Все конвертации {ext.upper()}", self.show_all_conversions))
        return results[:9]

    def close_search(self):
        if Overlay.current is not None:
            Overlay.current.close()

    def set_theme(self, name):
        self.settings.set("theme", name)
        t.apply_theme(name)

    def set_animations(self, on):
        self.settings.set("animations", bool(on))
        motion.enabled = bool(on) and not self.selftest

    def open_tool(self, tool):
        self.show_section(tool.section)
        self.pages[tool.section].select(tool)

    def on_close(self):
        active = self.jobs.active()
        if active and not self.selftest:
            text = (f"Ещё выполняется задач: {len(active)}. Если закрыть программу, они будут остановлены, "
                    "а незаконченные файлы удалены.")
            if not ask_yes_no(self, "Закрыть File Converter", text, "Остановить и закрыть"):
                return
        self.jobs.shutdown()
        self.transition.finish()
        self.destroy()
        gc.collect()
        gc.enable()


def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("FileConverter.App.1")
    except Exception:
        pass


def out(text):
    if sys.stdout is not None:
        try:
            print(text, flush=True)
        except Exception:
            pass


def run_selftest():
    """Создаёт окно, проверяет движки и разделы, конвертирует PNG в JPG и закрывается."""
    tmp = Path(tempfile.mkdtemp(prefix="fc_selftest_"))
    os.environ["FILECONVERTER_DATA"] = str(tmp / "data")
    lines = []
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        lines.append(f"{'OK  ' if cond else 'FAIL'} {name} {detail}".rstrip())
        if not cond:
            ok = False

    app = None
    try:
        app = App(selftest=True)
        app.update()
        for name, text, avail in app.engines.status():
            lines.append(f"     движок {text}: {'найден' if avail else 'не найден'}")
        check("шрифт", t.SANS == "IBM Plex Sans" and t.MONO == "IBM Plex Mono", f"{t.SANS} / {t.MONO}")
        check("иконки", (assets_dir() / "icons" / "pdf_48.png").exists() and (assets_dir() / "app.ico").exists())
        check("перетаскивание", app.dnd_ok)
        for key in SECTION_NAMES:
            app.show_section(key)
            app.update()
            check(f"раздел {SECTION_NAMES[key]}", app.current is app.pages[key])
        app.show_section("convert")
        page = app.pages["convert"]
        page.show_home()
        app.update()
        check("плитки из пустой статистики", [x.pair for x in page.tiles] == app.stats.top_pairs(8)
              and len(page.tiles) == 8)
        for _ in range(3):
            app.stats.add("png", "webp")
        app.stats.toggle_pin("doc", "odt")
        page.show_home()
        app.update()
        pairs = [x.pair for x in page.tiles]
        check("плитки из статистики", pairs[0] == ("doc", "odt") and pairs[1] == ("png", "webp") and len(pairs) == 8)

        from PIL import Image
        src = tmp / "проверка файл.png"
        Image.new("RGB", (64, 48), (245, 165, 36)).save(src)
        items = app.add_files([src])
        app.update()
        check("файл в очереди", len(items) == 1 and page.item is items[0])
        app.start_conversion(items, "jpg")
        deadline = time.time() + 60
        while time.time() < deadline and items[0].status not in ("done", "error"):
            app.update()
            time.sleep(0.05)
        app.update()
        result = items[0].outputs[0] if items[0].outputs else None
        check("конвертация PNG в JPG", items[0].status == "done" and result is not None
              and result.read_bytes()[:2] == b"\xff\xd8", str(result or items[0].error))
        AllConversions(app).destroy()
        app.update()
        check("ошибки интерфейса", not app.errors, app.errors[0].splitlines()[-1] if app.errors else "")
    except Exception:
        ok = False
        lines.append("FAIL исключение\n" + traceback.format_exc())
    finally:
        if app is not None:
            try:
                app.on_close()
            except Exception:
                pass
    report = "\n".join(lines) + f"\nИТОГ: {'OK' if ok else 'ОШИБКА'}\n"
    out(report)
    try:
        log = Path(os.environ.get("APPDATA", tmp)) / "FileConverter"
        log.mkdir(parents=True, exist_ok=True)
        (log / "selftest.log").write_text(report, encoding="utf-8")
    except OSError:
        pass
    return 0 if ok else 1


def run_cli_convert(src, dst_ext, out_dir=""):
    from .engines.base import Context
    from .naming import Namer
    from .registry import ext_of

    settings = Settings()
    engines = Engines(settings)
    src = Path(src)
    conv = registry.get(ext_of(src), dst_ext, engines)
    if conv is None:
        out(f"Нет конвертации {ext_of(src)} в {dst_ext}")
        return 2
    ctx = Context(settings.get("quality"), on_log=out, namer=Namer(out_dir))
    try:
        outputs = conv.run(engines, src, ctx.namer.file(src, dst_ext), ctx)
    except Exception as e:
        from .jobs import friendly_error
        out(f"Ошибка: {friendly_error(e)}")
        return 1
    for o in outputs:
        out(str(o))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    enable_dpi_awareness()
    if "--selftest" in argv:
        return run_selftest()
    if "--convert" in argv:
        i = argv.index("--convert")
        try:
            src, dst = argv[i + 1], argv[i + 2]
        except IndexError:
            out("Использование: --convert ФАЙЛ ФОРМАТ [--out ПАПКА]")
            return 2
        out_dir = argv[argv.index("--out") + 1] if "--out" in argv else ""
        return run_cli_convert(src, dst, out_dir)
    app = App()
    files = [a for a in argv if not a.startswith("--") and Path(a).exists()]
    if files:
        app.after(300, lambda: app.add_files(files))
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
