import tkinter as tk

import customtkinter as ctk

from . import theme as t


def accent_button(parent, text, command=None, height=t.H, size=14, **kw):
    return ctk.CTkButton(parent, text=text, command=command, height=height, corner_radius=t.RADIUS,
                         fg_color=t.ACCENT, hover_color=t.ACCENT_HOVER, text_color=t.ON_ACCENT,
                         text_color_disabled="#6B5A3A", font=t.font(size, "bold"), **kw)


def outline_button(parent, text, command=None, height=t.H, size=13, border=t.BORDER_BTN, color=t.TEXT, **kw):
    return ctk.CTkButton(parent, text=text, command=command, height=height, corner_radius=t.RADIUS,
                         fg_color="transparent", hover_color=t.CARD_SEL, border_width=1, border_color=border,
                         text_color=color, text_color_disabled=t.MUTED, font=t.font(size), **kw)


def ghost_button(parent, text, command=None, height=t.H, size=13, color=t.MUTED, **kw):
    return ctk.CTkButton(parent, text=text, command=command, height=height, corner_radius=t.RADIUS,
                         fg_color="transparent", hover_color=t.CARD, text_color=color, font=t.font(size), **kw)


def caption(parent, text, color=t.CAPTION, size=11, **kw):
    return ctk.CTkLabel(parent, text=text, font=t.mono(size, "bold"), text_color=color, **kw)


def label(parent, text, size=13, color=t.TEXT, weight="normal", **kw):
    return ctk.CTkLabel(parent, text=text, font=t.font(size, weight), text_color=color, **kw)


def mono_label(parent, text, size=11, color=t.MUTED, **kw):
    return ctk.CTkLabel(parent, text=text, font=t.mono(size), text_color=color, **kw)


def separator(parent, vertical=False, color=t.BORDER):
    if vertical:
        return ctk.CTkFrame(parent, width=1, height=1, fg_color=color, corner_radius=0)
    return ctk.CTkFrame(parent, height=1, width=1, fg_color=color, corner_radius=0)


def holder(parent, bg="transparent"):
    """Пустой контейнер. У CTkFrame по умолчанию размер 200 на 200, здесь он минимальный."""
    return ctk.CTkFrame(parent, fg_color=bg, corner_radius=0, width=1, height=1)


class ResponsiveGrid(ctk.CTkFrame):
    """Сетка карточек: число колонок зависит от ширины."""

    def __init__(self, parent, min_width=180, max_cols=4, gap=8, bg=t.MAIN):
        super().__init__(parent, fg_color=bg, corner_radius=0, width=1, height=1)
        self.min_width = min_width
        self.max_cols = max_cols
        self.gap = gap
        self.cols = 0
        self.items = []
        self.bind("<Configure>", self.on_resize, add="+")

    def add(self, widget):
        self.items.append(widget)
        self.layout(self.cols or self.max_cols)

    def on_resize(self, event):
        scaling = ctk.ScalingTracker.get_widget_scaling(self)
        width = event.width / scaling
        cols = max(1, min(self.max_cols, int((width + self.gap) // (self.min_width + self.gap))))
        if cols != self.cols:
            self.layout(cols)

    def layout(self, cols):
        self.cols = cols
        for c in range(self.max_cols):
            self.grid_columnconfigure(c, weight=1 if c < cols else 0, uniform="g" if c < cols else "")
        for i, w in enumerate(self.items):
            w.grid(row=i // cols, column=i % cols, sticky="nsew",
                   padx=(0 if i % cols == 0 else self.gap, 0), pady=(0, self.gap))


class Flow(ctk.CTkFrame):
    """Кнопки в строку с переносом, если не помещаются."""

    def __init__(self, parent, gap=6, bg=t.MAIN):
        super().__init__(parent, fg_color=bg, corner_radius=0, width=1, height=1)
        self.gap = gap
        self.items = []
        self.bind("<Configure>", on_event(lambda e: self.after_idle(self.layout)), add="+")

    def add(self, widget):
        self.items.append(widget)
        self.after_idle(self.layout)

    def layout(self):
        try:
            width = self.winfo_width()
        except tk.TclError:
            return
        if width < 10:
            return
        scaling = ctk.ScalingTracker.get_widget_scaling(self)
        x = y = row_h = 0
        gap = int(self.gap * scaling)
        for w in self.items:
            w.update_idletasks()
            ww, wh = w.winfo_reqwidth(), w.winfo_reqheight()
            if x and x + ww > width:
                x = 0
                y += row_h + gap
                row_h = 0
            w.place(x=x / scaling, y=y / scaling)
            x += ww + gap
            row_h = max(row_h, wh)
        height = (y + row_h) / scaling
        if abs(self.cget("height") - height) > 1:
            self.configure(height=max(1, height))


def entry(parent, placeholder="", width=200, show=None, **kw):
    return ctk.CTkEntry(parent, placeholder_text=placeholder, width=width, height=t.H, corner_radius=t.RADIUS,
                        fg_color=t.BAR, border_color=t.BORDER_BTN, border_width=1, text_color=t.TEXT,
                        placeholder_text_color=t.MUTED, font=t.font(13), show=show, **kw)


def checkbox(parent, text, variable, command=None):
    return ctk.CTkCheckBox(parent, text=text, variable=variable, command=command, height=t.H,
                           corner_radius=4, border_width=1, border_color=t.BORDER_BTN, fg_color=t.ACCENT,
                           hover_color=t.ACCENT_HOVER, checkmark_color=t.ON_ACCENT, text_color=t.TEXT,
                           font=t.font(13))


class Choice(ctk.CTkFrame):
    """Выбор одного варианта из нескольких кнопок, выбранная залита янтарным."""

    def __init__(self, parent, values, variable, command=None):
        super().__init__(parent, fg_color="transparent", corner_radius=0, width=1, height=1)
        self.variable = variable
        self.command = command
        self.buttons = {}
        for v in values:
            b = ctk.CTkButton(self, text=v, height=t.H, width=40, corner_radius=t.RADIUS, border_width=1,
                              font=t.font(13), command=lambda v=v: self.pick(v))
            b.pack(side="left", padx=(0, 6))
            self.buttons[v] = b
        self.paint()

    def pick(self, value):
        self.variable.set(value)
        self.paint()
        if self.command:
            self.command(value)

    def paint(self):
        current = self.variable.get()
        for v, b in self.buttons.items():
            on = v == current
            b.configure(fg_color=t.ACCENT if on else "transparent", hover_color=t.ACCENT_HOVER if on else t.CARD_SEL,
                        text_color=t.ON_ACCENT if on else t.TEXT, border_color=t.ACCENT if on else t.BORDER_BTN)


def segmented(parent, values, variable, command=None, width=None):
    return Choice(parent, values, variable, command)


def on_event(func):
    """Обработчик события, который молча пропускает вызов без события (зависший after() удалённого виджета)."""
    def handler(event=None):
        if event is not None:
            return func(event)
    return handler


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def bind_tree(widget, sequence, func):
    for w in walk(widget):
        try:
            w.bind(sequence, func, add="+")
        except (ValueError, NotImplementedError, tk.TclError):
            pass


def pointer_inside(widget):
    try:
        x, y = widget.winfo_pointerxy()
        under = widget.winfo_containing(x, y)
    except (KeyError, tk.TclError):
        return False
    while under is not None:
        if under == widget:
            return True
        under = under.master
    return False


def make_clickable(widget, on_click=None, on_enter=None, on_leave=None):
    """Клик и наведение на рамку вместе со всеми вложенными виджетами."""
    state = {"inside": False}

    def enter(_e=None):
        if _e is not None and not state["inside"]:
            state["inside"] = True
            if on_enter:
                on_enter()

    def leave(_e=None):
        def check():
            try:
                if state["inside"] and not pointer_inside(widget):
                    state["inside"] = False
                    if on_leave:
                        on_leave()
            except tk.TclError:
                pass
        widget.after(30, check)

    def press(event=None):
        # без события сюда может попасть только зависший after() удалённого виджета, это не клик
        if event is not None:
            on_click()

    if on_click:
        bind_tree(widget, "<Button-1>", press)
    bind_tree(widget, "<Enter>", enter)
    bind_tree(widget, "<Leave>", leave)
    for w in walk(widget):
        try:
            w.configure(cursor="hand2")
        except (ValueError, tk.TclError):
            pass


class DashedBox(ctk.CTkFrame):
    """Рамка с пунктиром для зоны перетаскивания."""

    def __init__(self, parent, bg=t.MAIN, color=t.DASH, **kw):
        super().__init__(parent, fg_color=bg, corner_radius=0, **kw)
        self.color = color
        self.bg = bg
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.inner = ctk.CTkFrame(self, fg_color=bg, corner_radius=0)
        self.inner.place(relx=0.5, rely=0.5, anchor="center")
        self.canvas.bind("<Configure>", self.redraw)

    def set_color(self, color):
        self.color = color
        self.redraw()

    def redraw(self, _e=None):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 10 or h < 10:
            return
        r, p = 8, 1
        dash = (4, 4)
        kw = {"fill": self.color, "dash": dash, "width": 1}
        c.create_line(p + r, p, w - p - r, p, **kw)
        c.create_line(p + r, h - p - 1, w - p - r, h - p - 1, **kw)
        c.create_line(p, p + r, p, h - p - r, **kw)
        c.create_line(w - p - 1, p + r, w - p - 1, h - p - r, **kw)
        akw = {"style": "arc", "outline": self.color, "width": 1}
        c.create_arc(p, p, p + 2 * r, p + 2 * r, start=90, extent=90, **akw)
        c.create_arc(w - p - 1 - 2 * r, p, w - p - 1, p + 2 * r, start=0, extent=90, **akw)
        c.create_arc(p, h - p - 1 - 2 * r, p + 2 * r, h - p - 1, start=180, extent=90, **akw)
        c.create_arc(w - p - 1 - 2 * r, h - p - 1 - 2 * r, w - p - 1, h - p - 1, start=270, extent=90, **akw)


class TabBar(ctk.CTkFrame):
    """Вкладки текстом с янтарной линией под активной."""

    def __init__(self, parent, tabs, command, active=None, bg=t.MAIN):
        super().__init__(parent, fg_color=bg, corner_radius=0)
        self.command = command
        self.items = {}
        self.bg = bg
        row = Flow(self, gap=4, bg=bg)
        row.pack(fill="x")
        for key, text in tabs:
            cell = holder(row, bg)
            btn = ctk.CTkButton(cell, text=text, height=t.H - 2, fg_color="transparent", hover_color=t.CARD,
                                corner_radius=t.RADIUS, text_color=t.MUTED, font=t.font(13),
                                command=lambda k=key: self.select(k, True), width=40)
            btn.pack(padx=2)
            line = ctk.CTkFrame(cell, height=2, width=1, fg_color=bg, corner_radius=0)
            line.pack(fill="x", padx=8)
            row.add(cell)
            self.items[key] = (btn, line)
        separator(self).pack(fill="x")
        self.active = None
        if tabs:
            self.select(active or tabs[0][0], False)

    def select(self, key, notify=True):
        if key not in self.items:
            return
        self.active = key
        for k, (btn, line) in self.items.items():
            on = k == key
            btn.configure(text_color=t.TEXT if on else t.MUTED, font=t.font(13, "bold" if on else "normal"))
            line.configure(fg_color=t.ACCENT if on else self.bg)
        if notify:
            self.command(key)


class Dot(tk.Canvas):
    def __init__(self, parent, color, bg, size=8):
        super().__init__(parent, width=size + 2, height=size + 2, bg=bg, highlightthickness=0, bd=0)
        self.oval = self.create_oval(1, 1, size + 1, size + 1, fill=color, outline=color)

    def set(self, color):
        self.itemconfigure(self.oval, fill=color, outline=color)


class Popover(ctk.CTkToplevel):
    """Небольшая подсказка рядом с виджетом, закрывается кликом или через несколько секунд."""

    current = None

    def __init__(self, anchor, text, below=False, timeout=8000):
        if Popover.current is not None:
            try:
                Popover.current.destroy()
            except tk.TclError:
                pass
        super().__init__(anchor)
        Popover.current = self
        self.overrideredirect(True)
        self.configure(fg_color=t.BORDER_BTN)
        self.attributes("-topmost", True)
        body = ctk.CTkFrame(self, fg_color=t.CARD, corner_radius=0)
        body.pack(padx=1, pady=1)
        lbl = ctk.CTkLabel(body, text=text, font=t.font(12), text_color=t.TEXT, justify="left", wraplength=360)
        lbl.pack(padx=14, pady=10)
        self.update_idletasks()
        x = anchor.winfo_rootx()
        if below:
            y = anchor.winfo_rooty() + anchor.winfo_height() + 4
        else:
            y = anchor.winfo_rooty() - self.winfo_reqheight() - 6
        x = min(x, anchor.winfo_screenwidth() - self.winfo_reqwidth() - 10)
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        bind_tree(self, "<Button-1>", lambda e=None: self.close())
        self.after(timeout, self.close)

    def close(self):
        try:
            self.destroy()
        except tk.TclError:
            pass
        if Popover.current is self:
            Popover.current = None


class Dialog(ctk.CTkToplevel):
    """Модальное окно в стиле приложения."""

    def __init__(self, parent, title, width=440):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.configure(fg_color=t.MAIN)
        self.resizable(False, False)
        self.result = None
        self.transient(parent.winfo_toplevel())
        self.body = ctk.CTkFrame(self, fg_color=t.MAIN, corner_radius=0, width=width)
        self.body.pack(fill="both", expand=True, padx=24, pady=(20, 12))
        label(self.body, title, 17, weight="bold").pack(anchor="w", pady=(0, 12))
        self.footer = ctk.CTkFrame(self, fg_color=t.BAR, corner_radius=0)
        self.footer.pack(fill="x", side="bottom")
        self.bind("<Escape>", on_event(lambda e: self.cancel()))
        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def show(self):
        self.update_idletasks()
        top = self.master.winfo_toplevel()
        w, h = max(self.winfo_reqwidth(), 420), self.winfo_reqheight()
        x = top.winfo_rootx() + (top.winfo_width() - w) // 2
        y = top.winfo_rooty() + (top.winfo_height() - h) // 3
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.deiconify()
        self.lift()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.focus_force()
        self.wait_window()
        return self.result

    def ok(self, value=True):
        self.result = value
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()

    def buttons(self, ok_text="Готово", cancel_text="Отмена", ok_command=None):
        row = ctk.CTkFrame(self.footer, fg_color=t.BAR, corner_radius=0)
        row.pack(fill="x", padx=24, pady=12)
        accent_button(row, ok_text, ok_command or (lambda: self.ok(True)), width=140).pack(side="right")
        if cancel_text:
            outline_button(row, cancel_text, self.cancel, width=110).pack(side="right", padx=(0, 10))
        self.bind("<Return>", on_event(lambda e: (ok_command or (lambda: self.ok(True)))()))


def message(parent, title, text, kind="info"):
    d = Dialog(parent, title)
    color = {"error": t.ERROR, "ok": t.SUCCESS}.get(kind, t.TEXT)
    label(d.body, text, 13, color=color, wraplength=420, justify="left").pack(anchor="w")
    d.buttons("Понятно", None)
    return d.show()


def ask_yes_no(parent, title, text, yes="Да"):
    d = Dialog(parent, title)
    label(d.body, text, 13, wraplength=420, justify="left").pack(anchor="w")
    d.buttons(yes, "Отмена")
    return bool(d.show())


class FieldsDialog(Dialog):
    """Ввод параметров инструмента: диапазоны страниц, пароль, текст и так далее."""

    def __init__(self, parent, title, fields, note=""):
        super().__init__(parent, title)
        self.widgets = {}
        if note:
            label(self.body, note, 12, color=t.MUTED, wraplength=400, justify="left").pack(anchor="w", pady=(0, 8))
        for f in fields:
            caption(self.body, f.label.upper()).pack(anchor="w", pady=(8, 4))
            if f.kind == "choice":
                names = [n for _, n in f.options]
                var = ctk.StringVar(value=dict(f.options).get(f.default, names[0]))
                segmented(self.body, names, var).pack(anchor="w", fill="x")
                self.widgets[f.key] = (f, var)
            else:
                e = entry(self.body, f.hint, width=392, show="*" if f.kind == "password" else None)
                if f.default:
                    e.insert(0, f.default)
                e.pack(anchor="w", fill="x")
                self.widgets[f.key] = (f, e)
                if f.hint:
                    mono_label(self.body, f.hint, 11).pack(anchor="w", pady=(2, 0))
        self.buttons("Выполнить", "Отмена", self.submit)
        first = next((w for f, w in self.widgets.values() if f.kind != "choice"), None)
        if first is not None:
            self.after(150, first.focus_set)

    def submit(self):
        values = {}
        for key, (f, w) in self.widgets.items():
            if f.kind == "choice":
                reverse = {n: k for k, n in f.options}
                values[key] = reverse.get(w.get(), f.default)
            else:
                values[key] = w.get()
        self.ok(values)
