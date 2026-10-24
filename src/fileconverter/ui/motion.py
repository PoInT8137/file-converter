"""Анимации интерфейса на after(): сдвиги, смена цвета, переход между разделами.

Tk не умеет прозрачность отдельных виджетов, поэтому «растворение» старой страницы сделано
снимком экрана, который плавно смешивается с цветом фона. Если снимок не получился или кадры
идут медленно, анимации упрощаются, а при сильных тормозах выключаются до конца сеанса.
"""
import ctypes
import time
import tkinter as tk

from . import theme as t

FRAME = 15
SLOW_FRAME = 0.06

enabled = True
# компьютер не успевал рисовать кадры: анимации выключены до перезапуска
too_slow = False
_slow_frames = 0
_running = {}


def active():
    return enabled and not too_slow and not t.HIDDEN


def ease_out(p):
    return 1 - (1 - p) ** 3


def ease_in_out(p):
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def mix(a, b, p):
    a, b = a.lstrip("#"), b.lstrip("#")
    ca = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * p):02x}" for x, y in zip(ca, cb))


def _note_frame(dt):
    global _slow_frames, too_slow
    if dt > SLOW_FRAME:
        _slow_frames += 1
        if _slow_frames >= 6:
            too_slow = True
    elif _slow_frames:
        _slow_frames -= 1


def run(widget, key, duration, step, done=None, easing=ease_out):
    """Вызывает step(p) с p от 0 до 1 за duration мс. Новая анимация с тем же key отменяет прежнюю."""
    cancel(key)
    if not active() or duration <= 0:
        _finish(step, done, easing)
        return
    # таймер на главном окне: after() удалённого виджета срабатывает на уже удалённой команде Tcl
    try:
        root = widget.winfo_toplevel()
    except tk.TclError:
        return
    start = time.perf_counter()
    state = {"last": start, "job": None}
    _running[key] = state

    def tick():
        if _running.get(key) is not state:
            return
        now = time.perf_counter()
        _note_frame(now - state["last"])
        state["last"] = now
        p = min(1.0, (now - start) * 1000 / duration)
        try:
            step(easing(p))
            if p >= 1.0 or too_slow:
                _running.pop(key, None)
                if p < 1.0:
                    step(1.0)
                if done:
                    done()
                return
            state["job"] = root.after(FRAME, tick)
        except tk.TclError:
            _running.pop(key, None)

    tick()


def _finish(step, done, easing):
    try:
        step(easing(1.0))
        if done:
            done()
    except tk.TclError:
        pass


def cancel(key):
    _running.pop(key, None)


def fade_color(widget, key, attr, start, end, duration=140):
    """Плавная смена цвета; в конце ставится сама пара цветов, чтобы виджет перекрашивался со сменой темы."""
    a, b = t.color(start), t.color(end)
    if a == b or a == "transparent" or b == "transparent":
        widget.configure(**{attr: end})
        return

    def step(p):
        widget.configure(**{attr: end if p >= 1 else mix(a, b, p)})

    run(widget, key, duration, step, easing=ease_in_out)


def _foreground(window):
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        return ctypes.windll.user32.GetForegroundWindow() == hwnd
    except Exception:
        return False


def snapshot(widget):
    """Снимок области виджета с экрана или None, если окно закрыто другими окнами."""
    if not _foreground(widget.winfo_toplevel()):
        return None
    try:
        from PIL import ImageGrab
        x, y = widget.winfo_rootx(), widget.winfo_rooty()
        w, h = widget.winfo_width(), widget.winfo_height()
        if w < 10 or h < 10:
            return None
        return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
    except Exception:
        return None


class PageTransition:
    """Старая страница растворяется в фоне, новая выезжает снизу на несколько пикселей."""

    FADE = 90
    SLIDE = 170
    OFFSET = 18

    def __init__(self, holder):
        self.holder = holder
        self.overlay = None
        self.photo = None
        self.page = None

    def start(self, old, new, show):
        """show(page) ставит страницу на место сеткой; до конца перехода она стоит через place()."""
        self.finish()
        self.page = new
        self.show = show
        if not active() or old is None:
            old is not None and old.grid_remove()
            show(new)
            return
        shot = snapshot(self.holder)
        old.grid_remove()
        new.place(x=0, y=self.OFFSET, relwidth=1, relheight=1)
        if shot is None:
            self._slide()
            return
        from PIL import Image, ImageTk
        bg = Image.new("RGB", shot.size, t.color(t.MAIN))
        self.overlay = tk.Label(self.holder, bd=0, highlightthickness=0, bg=t.color(t.MAIN))
        self.overlay.place(x=0, y=0, relwidth=1, relheight=1)
        self.overlay.lift()

        def step(p):
            self.photo = ImageTk.PhotoImage(Image.blend(shot, bg, p))
            self.overlay.configure(image=self.photo)

        step(0.0)
        run(self.holder, "page-fade", self.FADE, step, self._slide, easing=lambda p: p)

    def _slide(self):
        self._drop_overlay()
        page = self.page

        def step(p):
            # place() целиком, а не place_configure: CTkScrollableFrame переносит его на свою внешнюю рамку
            page.place(x=0, y=round(self.OFFSET * (1 - p)), relwidth=1, relheight=1)

        run(self.holder, "page-slide", self.SLIDE, step, self.finish)

    def _drop_overlay(self):
        if self.overlay is not None:
            try:
                self.overlay.destroy()
            except tk.TclError:
                pass
        self.overlay = None
        self.photo = None

    def finish(self):
        cancel("page-fade")
        cancel("page-slide")
        self._drop_overlay()
        page, self.page = self.page, None
        if page is not None:
            try:
                page.place_forget()
                self.show(page)
            except tk.TclError:
                pass
