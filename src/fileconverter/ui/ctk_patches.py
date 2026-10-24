"""Исправления CustomTkinter 6.0, которые нельзя сделать снаружи виджетов.

CTkScrollbar при каждом set() перерисовывается и вызывает update_idletasks(). Прокручиваемая
рамка вызывает set() на каждое изменение размеров содержимого, поэтому пока страница строится,
она десятки раз заново раскладывается и рисуется в недостроенном виде: страница открывается
медленно (у раздела PDF 1,3 из 1,7 секунды) и видно, как она собирается по кускам.
Здесь полоса прокрутки перерисовывается один раз, когда раскладка уже закончена.
"""
import tkinter as tk

from customtkinter.windows.widgets.ctk_scrollbar import CTkScrollbar

_original_draw = CTkScrollbar._draw


def _noop():
    pass


def _draw(self, no_color_updates=False):
    # update_idletasks у холста полосы отключён: он запускал раскладку всего окна посреди построения
    self._canvas.update_idletasks = _noop
    _original_draw(self, no_color_updates)


def _set(self, start_value, end_value):
    self._start_value = float(start_value)
    self._end_value = float(end_value)
    if getattr(self, "_draw_pending", False):
        return
    self._draw_pending = True

    def draw():
        self._draw_pending = False
        try:
            if self.winfo_exists():
                self._draw()
        except tk.TclError:
            pass

    try:
        # таймер на главном окне: after_idle удалённого виджета сработал бы на удалённой команде Tcl
        self.winfo_toplevel().after_idle(draw)
    except tk.TclError:
        self._draw_pending = False


def apply():
    if CTkScrollbar._draw is not _draw:
        CTkScrollbar._draw = _draw
        CTkScrollbar.set = _set
