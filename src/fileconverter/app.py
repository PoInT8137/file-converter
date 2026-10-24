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
from .ui import theme as t
from .ui.convert_page import ConvertPage
from .ui.other_pages import AllConversions, HistoryPage, SettingsPage
from .ui.queue_panel import QueuePanel
from .ui.tools_page import ToolsPage
from .ui.widgets import (Dot, on_event, FieldsDialog, Flow, Popover, ask_yes_no, caption, checkbox, entry, label, make_clickable, message,
                         mono_label, outline_button, segmented, separator)

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
QUALITY = [("high", "Высокое"), ("medium", "Среднее"), ("low", "Низкое")]


def file_patterns(ext):
    exts = [ext] + [a for a, target in ALIASES.items() if target == ext]
    return " ".join(f"*.{e}" for e in exts)


class App(ctk.CTk, DND_BASE):
    def __init__(self, selftest=False):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=t.BG)
        self.selftest = selftest
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

        self.settings = Settings()
        self.stats = Stats()
        self.history = History()
        self.engines = Engines(self.settings)
        self.jobs = JobQueue(self.engines, self.settings, self.stats, self.history)
        self.job_items = {}
        self.ui_calls = queue.Queue()
        self.pages = {}
        self.current = None
        self.search_popup = None

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_header()
        self.body = ctk.CTkFrame(self, fg_color=t.BG, corner_radius=0)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(4, weight=1)
        self.body.grid_columnconfigure(0, minsize=200)
        self.body.grid_columnconfigure(2, minsize=290)
        self.build_sidebar()
        separator(self.body, vertical=True).grid(row=0, column=1, sticky="ns")
        self.queue_panel = QueuePanel(self)
        self.queue_panel.grid(row=0, column=2, sticky="nsew")
        separator(self.body, vertical=True).grid(row=0, column=3, sticky="ns")
        self.content = ctk.CTkFrame(self.body, fg_color=t.MAIN, corner_radius=0)
        self.content.grid(row=0, column=4, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.build_engines_bar()

        if self.dnd_ok:
            self.register_drop(self, self.add_files)
        self.bind_all("<Control-KeyPress>", self.on_ctrl_key)
        # у полей ввода Tk своя комбинация Ctrl+K "удалить до конца строки", она срабатывает раньше bind_all
        for cls in ("Entry", "Text"):
            self.bind_class(cls, "<Control-Key-k>", self.on_ctrl_key)
            self.bind_class(cls, "<Control-Key-K>", self.on_ctrl_key)
        self.bind("<Escape>", on_event(lambda e: self.close_search()))
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
        self.minsize(min(1000, w), min(640, h))
        x = left + max(0, int((width - w * scale) / 2))
        y = top + max(0, int((height - 40 - h * scale) / 2))
        self.geometry(f"{w}x{h}+{x}+{y}")

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
        head = ctk.CTkFrame(self, fg_color=t.BAR, corner_radius=0, height=60)
        head.grid(row=0, column=0, sticky="ew")
        head.grid_propagate(False)
        head.grid_columnconfigure(1, weight=1)
        logo = ctk.CTkFrame(head, fg_color=t.BAR)
        logo.grid(row=0, column=0, padx=18, pady=12, sticky="w")
        ctk.CTkLabel(logo, text="", image=t.ui_icon("arrow-left-right", "accent", 24)).pack(side="left")
        ctk.CTkLabel(logo, text="FILE CONVERTER", font=t.mono(15, "bold"), text_color=t.TEXT).pack(side="left", padx=10)

        box = ctk.CTkFrame(head, fg_color=t.BAR)
        box.grid(row=0, column=2, padx=18, sticky="e")
        self.search = entry(box, "Найти функцию или формат", width=360)
        self.search.configure(height=40)
        self.search.pack()
        ctk.CTkLabel(self.search, text="", image=t.ui_icon("search", "muted", 16), fg_color=t.BAR).place(
            relx=1.0, x=-70, rely=0.5, anchor="e")
        hint = ctk.CTkLabel(self.search, text="Ctrl K", font=t.mono(10, "bold"), text_color=t.MUTED,
                            fg_color=t.CARD, corner_radius=4, height=20, width=48)
        hint.place(relx=1.0, x=-10, rely=0.5, anchor="e")
        self.search.bind("<KeyRelease>", self.on_search_key)
        self.search.bind("<Return>", on_event(lambda e: self.search_pick(0)))
        self.search.bind("<Down>", on_event(lambda e: self.search_focus_first()))
        self.search.bind("<FocusOut>", on_event(lambda e: self.after(200, self.maybe_close_search)))
        separator(self).grid(row=0, column=0, sticky="sew")

    def build_sidebar(self):
        side = ctk.CTkFrame(self.body, fg_color=t.BAR, corner_radius=0, width=200)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        self.nav = {}
        caption(side, "РАЗДЕЛЫ", color=t.MUTED, size=10).pack(anchor="w", padx=20, pady=(16, 6))
        for s in SECTIONS:
            if s is None:
                separator(side).pack(fill="x", padx=16, pady=10)
                continue
            key, text, icon = s
            btn = ctk.CTkButton(side, text=text, anchor="w", height=t.H, corner_radius=t.RADIUS,
                                fg_color="transparent", hover_color=t.CARD, text_color=t.MUTED, font=t.font(13),
                                image=t.ui_icon(icon, "muted", 18), compound="left",
                                command=lambda k=key: self.show_section(k))
            btn.pack(fill="x", padx=10, pady=1)
            self.nav[key] = (btn, icon)

    def build_engines_bar(self):
        if hasattr(self, "engines_bar"):
            self.engines_bar.destroy()
        bar = ctk.CTkFrame(self, fg_color=t.BAR, corner_radius=0, height=t.H)
        bar.grid(row=2, column=0, sticky="ew")
        bar.pack_propagate(False)
        self.engines_bar = bar
        separator(bar).place(x=0, y=0, relwidth=1)
        caption(bar, "ДВИЖКИ", color=t.MUTED, size=10).pack(side="left", padx=(20, 14))
        for name, text, ok in self.engines.status():
            cell = ctk.CTkFrame(bar, fg_color=t.BAR, corner_radius=t.RADIUS, height=36)
            cell.pack(side="left", padx=2, pady=4)
            Dot(cell, t.SUCCESS if ok else t.ERROR, t.BAR).pack(side="left", padx=(10, 6))
            mono_label(cell, text, 11, t.CAPTION if ok else t.MUTED).pack(side="left", padx=(0, 10))
            make_clickable(cell, lambda n=name, c=cell: Popover(c, self.engines.describe(n)),
                           lambda c=cell: c.configure(fg_color=t.CARD), lambda c=cell: c.configure(fg_color=t.BAR))
        mono_label(bar, f"v{__version__}", 11).pack(side="right", padx=20)
        if not self.dnd_ok:
            mono_label(bar, "перетаскивание недоступно", 10, t.ERROR).pack(side="right", padx=10)

    def show_section(self, key):
        self.close_search()
        for k, (btn, icon) in self.nav.items():
            on = k == key
            btn.configure(fg_color=t.CARD_SEL if on else "transparent", text_color=t.TEXT if on else t.MUTED,
                          image=t.ui_icon(icon, "accent" if on else "muted", 18))
        if self.current is not None:
            self.current.grid_remove()
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
        page.grid(row=0, column=0, sticky="nsew")
        self.current = page
        self.current_key = key

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

    def register_drop(self, widget, func):
        if not self.dnd_ok:
            return

        def handler(event):
            try:
                paths = [p for p in self.tk.splitlist(event.data) if p]
            except Exception:
                paths = []
            if paths:
                self.after(10, lambda: func(paths))
            return event.action

        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", handler)
        except Exception:
            pass

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
            message(self, "Конвертация недоступна",
                    f"Нельзя конвертировать в {dst.upper()}: {names}. Нет подходящего движка или формат не поддерживается.",
                    "error")
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
        self.build_engines_bar()
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

    def on_ctrl_key(self, event):
        # 75 это клавиша K в любой раскладке
        if event.keycode == 75:
            self.search.focus_set()
            self.search.select_range(0, "end")
            return "break"
        return None

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

    def on_search_key(self, event):
        if event.keysym in ("Return", "Down", "Up", "Escape") or event.keysym.startswith("Control"):
            if event.keysym == "Escape":
                self.close_search()
            return
        self.update_search()

    def update_search(self):
        results = self.search_items(self.search.get())
        self.close_search()
        if not self.search.get().strip():
            return
        pop = ctk.CTkToplevel(self)
        pop.withdraw()
        pop.overrideredirect(True)
        pop.configure(fg_color=t.BORDER_BTN)
        pop.attributes("-topmost", True)
        inner = ctk.CTkFrame(pop, fg_color=t.CARD, corner_radius=0)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        self.search_results = results
        self.search_buttons = []
        if not results:
            mono_label(inner, "Ничего не найдено", 12).pack(padx=16, pady=12, anchor="w")
        for i, (kind, text, _) in enumerate(results):
            row = ctk.CTkButton(inner, text=f"{text}", anchor="w", height=t.H, corner_radius=0, fg_color=t.CARD,
                                hover_color=t.CARD_SEL, text_color=t.TEXT, font=t.font(13),
                                command=lambda n=i: self.search_pick(n))
            row.pack(fill="x")
            mono_label(row, kind, 9).place(relx=1.0, x=-10, rely=0.5, anchor="e")
            row.bind("<Return>", on_event(lambda e, n=i: self.search_pick(n)))
            self.search_buttons.append(row)
        pop.update_idletasks()
        x = self.search.winfo_rootx()
        y = self.search.winfo_rooty() + self.search.winfo_height() + 4
        w = self.search.winfo_width()
        pop.geometry(f"{w}x{pop.winfo_reqheight()}+{x}+{y}")
        pop.deiconify()
        self.search_popup = pop

    def search_focus_first(self):
        if getattr(self, "search_buttons", None):
            self.search_buttons[0].focus_set()

    def search_pick(self, n):
        results = getattr(self, "search_results", [])
        if n < len(results):
            action = results[n][2]
            self.search.delete(0, "end")
            self.close_search()
            self.focus_set()
            self.after(20, action)

    def maybe_close_search(self):
        focus = self.focus_get()
        if self.search_popup is not None and focus is not None and str(focus).startswith(str(self.search_popup)):
            return
        if focus is not self.search and (focus is None or not str(focus).startswith(str(self.search))):
            self.close_search()

    def close_search(self):
        if self.search_popup is not None:
            try:
                self.search_popup.destroy()
            except Exception:
                pass
            self.search_popup = None

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
    ctk.set_appearance_mode("dark")
    app = App()
    files = [a for a in argv if not a.startswith("--") and Path(a).exists()]
    if files:
        app.after(300, lambda: app.add_files(files))
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
