"""Стартовое окно при масштабе Windows 150% помещается в рабочую область экрана.

Запускается отдельным процессом: масштаб CustomTkinter глобальный и не должен влиять на другие тесты.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r'''
import ctypes, ctypes.wintypes, os, sys, tempfile
sys.path.insert(0, {src!r})
os.environ["FILECONVERTER_DATA"] = tempfile.mkdtemp()
import customtkinter as ctk
from fileconverter.app import App, enable_dpi_awareness
enable_dpi_awareness()
ctk.set_widget_scaling(1.5)
ctk.set_window_scaling(1.5)
app = App(selftest=True)
for _ in range(20):
    app.update()
rect = ctypes.wintypes.RECT()
ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(rect), 0)
bottom = app.winfo_rooty() + app.winfo_height()
right = app.winfo_rootx() + app.winfo_width()
print(bottom, rect.bottom, right, rect.right, flush=True)
app.destroy()
'''


def test_start_window_fits_screen_at_150_percent():
    code = SCRIPT.format(src=str(ROOT / "src"))
    r = subprocess.run([sys.executable, "-W", "ignore", "-c", code], capture_output=True, text=True, timeout=120,
                       creationflags=0x08000000)
    line = [l for l in r.stdout.splitlines() if l.strip()][-1]
    bottom, work_bottom, right, work_right = map(int, line.split())
    assert bottom <= work_bottom, f"низ окна {bottom} ниже рабочей области {work_bottom}"
    assert right <= work_right
