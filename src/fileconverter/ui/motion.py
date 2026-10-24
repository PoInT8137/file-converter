"""Анимации интерфейса на after(): сдвиги, смена цвета, прозрачность окон диалогов.

Как в Happ: разделы переключаются мгновенно, плавными сделаны только мелкие элементы (маркер
и цвет пунктов меню) и появление диалогов. Если кадры идут медленно, анимации выключаются
до конца сеанса.
"""
import ctypes
import time
import tkinter as tk

from . import theme as t

FRAME = 10

enabled = True
_running = {}


def active():
    return enabled and not t.HIDDEN


def ease_out(p):
    return 1 - (1 - p) ** 3


def ease_in_out(p):
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def mix(a, b, p):
    a, b = a.lstrip("#"), b.lstrip("#")
    ca = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * p):02x}" for x, y in zip(ca, cb))


_timer_fine = False


def _fine_timer(on):
    """Таймер Windows по умолчанию тикает раз в 15,6 мс, и after(15) иногда ждёт два тика. На время анимаций 1 мс."""
    global _timer_fine
    if on == _timer_fine:
        return
    _timer_fine = on
    try:
        if on:
            ctypes.windll.winmm.timeBeginPeriod(1)
        else:
            ctypes.windll.winmm.timeEndPeriod(1)
    except Exception:
        pass


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
    state = {"job": None}
    _running[key] = state
    _fine_timer(True)

    def tick():
        if _running.get(key) is not state:
            return
        # прогресс по времени: если кадр задержался (строится страница), анимация просто перескакивает вперёд
        now = time.perf_counter()
        p = min(1.0, (now - start) * 1000 / duration)
        try:
            step(easing(p))
            if p >= 1.0:
                cancel(key)
                if done:
                    done()
                return
            state["job"] = root.after(FRAME, tick)
        except tk.TclError:
            cancel(key)

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
    if not _running:
        _fine_timer(False)


def fade_color(widget, key, attr, start, end, duration=140):
    """Плавная смена цвета; в конце ставится сама пара цветов, чтобы виджет перекрашивался со сменой темы."""
    a, b = t.color(start), t.color(end)
    if a == b or a == "transparent" or b == "transparent":
        widget.configure(**{attr: end})
        return

    def step(p):
        widget.configure(**{attr: end if p >= 1 else mix(a, b, p)})

    run(widget, key, duration, step, easing=ease_in_out)
