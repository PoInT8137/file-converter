"""Слои поверх окна: палитра команд (Ctrl+K) и панель движков.

Это рамки внутри главного окна, а не отдельные окна: они не теряются за другими программами,
двигаются вместе с окном и закрываются кликом мимо или клавишей Esc.
"""
import tkinter as tk

import customtkinter as ctk

from . import motion
from . import theme as t
from .widgets import Dot, accent_button, holder, label, mono_label, on_event, outline_button, separator


class Overlay(ctk.CTkFrame):
    """Рамка поверх окна. Одновременно открыт только один слой."""

    current = None

    def __init__(self, app, width):
        super().__init__(app, fg_color=t.BORDER_BTN, corner_radius=t.RADIUS + 2, width=width, height=1)
        self.app = app
        self.is_open = False
        self.inner = ctk.CTkFrame(self, fg_color=t.CARD, corner_radius=t.RADIUS + 1, width=width - 2, height=1)
        self.inner.pack(fill="both", expand=True, padx=1, pady=1)
        # рамка подстраивается под содержимое, распорка держит ширину слоя
        self.strut = ctk.CTkFrame(self, fg_color="transparent", width=width, height=1, corner_radius=0)
        self.strut.pack(side="bottom")
        app.bind_all("<ButtonPress-1>", self.on_press, add="+")

    def place_at(self, **kw):
        """Позиция в логических пикселях, как у place() виджетов CTk."""
        self.where = kw

    def open(self):
        if Overlay.current is not None and Overlay.current is not self:
            Overlay.current.close()
        Overlay.current = self
        self.is_open = True
        where = dict(self.where)
        y = where.pop("y", 0)
        if motion.active():
            def step(p):
                self.place(y=y - round(8 * (1 - p)), **where)
            step(0.0)
            motion.run(self, f"overlay-{id(self)}", 140, step)
        else:
            self.place(y=y, **where)
        self.lift()

    def close(self):
        if not self.is_open:
            return
        self.is_open = False
        motion.cancel(f"overlay-{id(self)}")
        if Overlay.current is self:
            Overlay.current = None
        try:
            self.place_forget()
        except tk.TclError:
            pass

    def toggle(self):
        if self.is_open:
            self.close()
        else:
            self.open()

    def contains(self, widget):
        return str(widget).startswith(str(self))

    def on_press(self, event):
        if not self.is_open:
            return
        try:
            if self.contains(event.widget) or self.ignore(event.widget):
                return
        except (KeyError, tk.TclError):
            return
        self.close()

    def ignore(self, widget):
        """Виджеты, клик по которым не закрывает слой (например, кнопка, которая его открывает)."""
        return False


class CommandPalette(Overlay):
    """Поиск функций, форматов и разделов. Стрелки выбирают, Enter выполняет, Esc закрывает."""

    WIDTH = 560
    LIMIT = 9

    def __init__(self, app):
        super().__init__(app, self.WIDTH)
        self.place_at(relx=0.5, y=64, anchor="n")
        top = holder(self.inner, t.CARD)
        top.pack(fill="x", padx=14, pady=(8, 6))
        ctk.CTkLabel(top, text="", image=t.ui_icon("search", "muted", 18)).pack(side="left")
        self.entry = ctk.CTkEntry(top, placeholder_text="Найти функцию, формат или раздел", height=t.H,
                                  border_width=0, fg_color=t.CARD, text_color=t.TEXT,
                                  placeholder_text_color=t.MUTED, font=t.font(14))
        self.entry.pack(side="left", fill="x", expand=True, padx=(8, 8))
        mono_label(top, "Esc", 10, t.MUTED, fg_color=t.CARD_SEL, corner_radius=4, width=36, height=20).pack(
            side="right")
        separator(self.inner).pack(fill="x")
        self.list = holder(self.inner, t.CARD)
        self.list.pack(fill="x", pady=6)
        self.results = []
        self.rows = []
        self.index = 0
        self.entry.bind("<KeyRelease>", self.on_key)
        self.entry.bind("<Return>", on_event(lambda e: self.pick(self.index)))
        self.entry.bind("<Down>", on_event(lambda e: self.move(1)))
        self.entry.bind("<Up>", on_event(lambda e: self.move(-1)))
        self.entry.bind("<Escape>", on_event(lambda e: self.close()))

    def ignore(self, widget):
        trigger = getattr(self.app, "search_button", None)
        return trigger is not None and str(widget).startswith(str(trigger))

    def open(self):
        super().open()
        self.refresh()
        self.entry.focus_set()
        self.entry.select_range(0, "end")

    def close(self):
        was_open = self.is_open
        super().close()
        if was_open:
            try:
                self.app.focus_set()
            except tk.TclError:
                pass

    def on_key(self, event):
        if event.keysym in ("Return", "Down", "Up", "Escape") or event.keysym.startswith("Control"):
            return
        self.refresh()

    def refresh(self):
        text = self.entry.get()
        self.results = self.app.search_items(text) if text.strip() else self.app.default_commands()
        self.results = self.results[:self.LIMIT]
        self.index = 0
        for w in self.list.winfo_children():
            w.destroy()
        self.rows = []
        if not self.results:
            label(self.list, "Ничего не найдено", 13, t.MUTED).pack(anchor="w", padx=16, pady=10)
            mono_label(self.list, "Попробуйте формат (pdf, jpg) или пару форматов: pdf docx", 11).pack(
                anchor="w", padx=16, pady=(0, 8))
            return
        for i, (kind, text, _) in enumerate(self.results):
            row = ctk.CTkButton(self.list, text=text, anchor="w", height=38, corner_radius=t.RADIUS,
                                fg_color=t.CARD, hover_color=t.CARD_SEL, text_color=t.TEXT, font=t.font(13),
                                command=lambda n=i: self.pick(n))
            row.pack(fill="x", padx=6)
            row.kind = mono_label(row, kind, 9, fg_color=t.CARD)
            row.kind.place(relx=1.0, x=-12, rely=0.5, anchor="e")
            # подпись справа перекрашивается вместе со строкой, иначе на подсвеченной строке видна её подложка
            row.bind("<Enter>", lambda e, r=row: r.kind.configure(fg_color=t.CARD_SEL), add="+")
            row.bind("<Leave>", lambda e, n=i, r=row: r.kind.configure(
                fg_color=t.CARD_SEL if n == self.index else t.CARD), add="+")
            self.rows.append(row)
        self.paint()

    def paint(self):
        for i, row in enumerate(self.rows):
            fill = t.CARD_SEL if i == self.index else t.CARD
            row.configure(fg_color=fill)
            row.kind.configure(fg_color=fill)

    def move(self, delta):
        if self.rows:
            self.index = (self.index + delta) % len(self.rows)
            self.paint()
        return "break"

    def pick(self, n):
        if n < len(self.results):
            action = self.results[n][2]
            self.entry.delete(0, "end")
            self.close()
            self.app.after(20, action)


class EnginesPanel(Overlay):
    """Состояние движков: что найдено, чего не хватает и что от этого не работает."""

    WIDTH = 380

    def __init__(self, app, anchor):
        super().__init__(app, self.WIDTH)
        self.anchor_widget = anchor
        self.place_at(relx=1.0, x=-16, y=60, anchor="ne")

    def ignore(self, widget):
        return str(widget).startswith(str(self.anchor_widget))

    def open(self):
        self.build()
        super().open()

    def build(self):
        for w in self.inner.winfo_children():
            w.destroy()
        app = self.app
        box = holder(self.inner, t.CARD)
        box.pack(fill="x", padx=16, pady=14)
        label(box, "Движки", 15, weight="bold").pack(anchor="w")
        label(box, "Программа вызывает их для конвертации. Без движка часть форматов недоступна.", 12, t.MUTED,
              wraplength=self.WIDTH - 40, justify="left").pack(anchor="w", pady=(2, 10))
        for name, text, ok in app.engines.status():
            row = holder(box, t.CARD)
            row.pack(fill="x", pady=3)
            Dot(row, t.SUCCESS if ok else t.ERROR, t.CARD).pack(side="left", padx=(0, 8))
            label(row, text, 13, t.TEXT if ok else t.MUTED, "bold").pack(side="left")
            mono_label(row, "найден" if ok else "не найден", 11, t.MUTED if ok else t.ERROR).pack(side="right")
            if not ok:
                label(box, app.engines.describe(name), 11, t.MUTED, wraplength=self.WIDTH - 56,
                      justify="left").pack(anchor="w", padx=(18, 0), pady=(0, 4))
        if not app.dnd_ok:
            label(box, "Перетаскивание файлов недоступно: добавляйте их кнопкой «Добавить файлы».", 12, t.ERROR,
                  wraplength=self.WIDTH - 40, justify="left").pack(anchor="w", pady=(8, 0))
        separator(self.inner).pack(fill="x")
        foot = holder(self.inner, t.CARD)
        foot.pack(fill="x", padx=16, pady=10)
        from .. import __version__
        mono_label(foot, f"версия {__version__}", 11).pack(side="left")
        accent_button(foot, "Настройки движков", lambda: (self.close(), app.show_section("settings")),
                      height=34, size=12, width=150).pack(side="right")
        outline_button(foot, "Найти заново", lambda: (app.rescan_engines(), self.build()), height=34, size=12,
                       width=110).pack(side="right", padx=(0, 8))
