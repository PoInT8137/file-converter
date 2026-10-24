from pathlib import Path

import customtkinter as ctk

from ..osutils import human_size
from ..registry import ext_of
from . import motion
from . import theme as t
from .widgets import caption, empty_state, ghost_button, inside, make_clickable, mono_label, walk_own

STATUS_TEXT = {"wait": "ЖДЁТ", "done": "ГОТОВО", "error": "ОШИБКА", "cancel": "ОТМЕНА", "new": ""}
STATUS_COLOR = {"wait": t.MUTED, "done": t.SUCCESS, "error": t.ERROR, "run": t.ACCENT_TEXT, "cancel": t.MUTED,
                "new": t.MUTED}


class QueueFile:
    def __init__(self, path):
        self.path = Path(path)
        self.ext = ext_of(path)
        try:
            self.size = self.path.stat().st_size
        except OSError:
            self.size = 0
        self.status = "new"
        self.progress = 0.0
        self.error = ""
        self.outputs = []
        self.jobs = []


class QueueRow(ctk.CTkFrame):
    def __init__(self, panel, item):
        super().__init__(panel.list, fg_color=t.QUEUE, corner_radius=t.RADIUS, height=56)
        self.panel = panel
        self.item = item
        self.selected = False
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text="", image=t.get_icon(item.ext, 28), width=32).grid(
            row=0, column=0, rowspan=2, padx=(10, 8), pady=8)
        name = item.path.name
        if len(name) > 30:
            name = name[:18] + "..." + name[-9:]
        self.name = ctk.CTkLabel(self, text=name, font=t.font(13), text_color=t.TEXT, anchor="w")
        self.name.grid(row=0, column=1, sticky="ew", pady=(8, 0))
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=1, column=1, sticky="ew", pady=(0, 8))
        bottom.grid_columnconfigure(1, weight=1)
        self.size = mono_label(bottom, human_size(item.size), 11)
        self.size.grid(row=0, column=0, sticky="w")
        # прогресс тонкой линией по низу строки
        self.bar = ctk.CTkProgressBar(self, height=2, corner_radius=0, fg_color=t.BORDER,
                                      progress_color=t.ACCENT, width=60, border_width=0)
        self.shown_progress = 0.0
        self.status = ctk.CTkLabel(bottom, text="", font=t.mono(11, "bold"), text_color=t.MUTED)
        self.status.grid(row=0, column=2, sticky="e", padx=(6, 0))
        self.remove = ctk.CTkButton(self, text="", image=t.ui_icon("x", "muted", 14), width=28, height=28,
                                    fg_color="transparent", hover_color=t.BORDER, corner_radius=t.RADIUS,
                                    command=self.remove_or_cancel)
        self.remove.grid(row=0, column=2, rowspan=2, padx=(4, 8))
        make_clickable(self, None, self.hover_on, self.hover_off)
        for w in walk_own(self):
            if w is not self.remove:
                try:
                    w.bind("<ButtonRelease-1>", self.click, add="+")
                except (ValueError, NotImplementedError):
                    pass
        self.refresh()

    def appear(self):
        """Новая строка коротко подсвечивается, чтобы было видно, что файл добавился."""
        self.configure(fg_color=t.CARD_SEL)
        motion.fade_color(self, f"row-{id(self)}", "fg_color", t.CARD_SEL,
                          t.CARD_SEL if self.selected else t.QUEUE, 600)

    def remove_or_cancel(self):
        # крестик у файла в работе отменяет задачу, у остальных убирает файл из очереди
        if self.item.status in ("run", "wait"):
            self.panel.app.cancel_item(self.item)
        else:
            self.panel.remove(self.item)

    def click(self, event=None):
        if event is None or not inside(self, event):
            return
        ctrl = bool(event and event.state & 0x0004)
        self.panel.click(self.item, ctrl)

    def hover_on(self):
        if not self.selected:
            motion.fade_color(self, f"row-{id(self)}", "fg_color", t.QUEUE, t.CARD, 100)

    def hover_off(self):
        if not self.selected:
            motion.fade_color(self, f"row-{id(self)}", "fg_color", t.CARD, t.QUEUE, 160)

    def set_selected(self, value):
        self.selected = value
        motion.cancel(f"row-{id(self)}")
        self.configure(fg_color=t.CARD_SEL if value else t.QUEUE, border_width=1 if value else 0,
                       border_color=t.BORDER_BTN)

    def refresh(self):
        it = self.item
        if it.status == "run":
            if not self.bar.winfo_ismapped():
                self.shown_progress = 0.0
                self.bar.set(0)
                self.bar.place(relx=0.5, rely=1.0, y=-3, relwidth=0.92, anchor="s")
            self.animate_progress(it.progress)
            self.status.configure(text=f"{int(it.progress * 100)}%", text_color=t.ACCENT_TEXT)
        else:
            motion.cancel(f"bar-{id(self)}")
            self.bar.place_forget()
            self.status.configure(text=STATUS_TEXT.get(it.status, ""), text_color=STATUS_COLOR.get(it.status, t.MUTED))


    def animate_progress(self, value):
        start = self.shown_progress
        self.shown_progress = value

        def step(p):
            self.bar.set(start + (value - start) * p)

        motion.run(self, f"bar-{id(self)}", 250, step)


class QueuePanel(ctk.CTkFrame):
    def __init__(self, app):
        super().__init__(app.body, fg_color=t.QUEUE, corner_radius=0, width=290)
        self.app = app
        self.items = []
        self.rows = {}
        self.selected = []
        self.grid_propagate(False)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(self, fg_color=t.QUEUE, height=t.H + 8)
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 0))
        caption(head, "ОЧЕРЕДЬ").pack(side="left")
        self.count = mono_label(head, "0", 11)
        self.count.pack(side="left", padx=8)
        add = ctk.CTkButton(head, text="", image=t.ui_icon("plus", "muted", 16), width=32, height=32,
                            corner_radius=t.RADIUS, fg_color="transparent", hover_color=t.CARD,
                            command=app.pick_files)
        add.pack(side="right")
        ghost_button(head, "Очистить", self.clear, width=70, height=32, size=12).pack(side="right", padx=(0, 2))

        self.list = ctk.CTkScrollableFrame(self, fg_color=t.QUEUE, corner_radius=0,
                                           scrollbar_button_color=t.BORDER, scrollbar_button_hover_color=t.BORDER_BTN)
        self.list.grid(row=1, column=0, sticky="nsew", padx=(6, 2), pady=(0, 8))
        self.empty = empty_state(self.list, "upload", "Файлов пока нет",
                                 "Перетащите файлы в окно или нажмите плюс вверху.", bg=t.QUEUE)
        self.empty.pack(pady=40, fill="x")

    def add(self, paths):
        added = []
        known = {str(i.path).lower() for i in self.items}
        for p in paths:
            p = Path(p)
            if not p.is_file() or str(p).lower() in known:
                existing = self.find(p)
                if existing:
                    added.append(existing)
                continue
            item = QueueFile(p)
            self.items.append(item)
            known.add(str(p).lower())
            self.empty.pack_forget()
            row = QueueRow(self, item)
            row.pack(fill="x", pady=2, padx=(0, 4))
            row.appear()
            self.rows[id(item)] = row
            added.append(item)
        self.count.configure(text=str(len(self.items)))
        return added

    def find(self, path):
        key = str(Path(path)).lower()
        for i in self.items:
            if str(i.path).lower() == key:
                return i
        return None

    def remove(self, item):
        if item not in self.items:
            return
        self.items.remove(item)
        row = self.rows.pop(id(item), None)
        if row:
            row.destroy()
        if item in self.selected:
            self.selected.remove(item)
            self.app.on_selection()
        if not self.items:
            self.empty.pack(pady=40, fill="x")
        self.count.configure(text=str(len(self.items)))

    def clear(self):
        for item in list(self.items):
            if item.status not in ("run", "wait"):
                self.remove(item)

    def click(self, item, ctrl=False):
        if ctrl:
            if item in self.selected:
                self.selected.remove(item)
            else:
                self.selected.append(item)
        else:
            self.selected = [item]
        self.update_selection()
        self.app.on_selection()

    def select(self, items):
        self.selected = [i for i in items if i in self.items]
        self.update_selection()

    def update_selection(self):
        for item in self.items:
            row = self.rows.get(id(item))
            if row:
                row.set_selected(item in self.selected)

    def refresh(self, item):
        row = self.rows.get(id(item))
        if row:
            row.refresh()
