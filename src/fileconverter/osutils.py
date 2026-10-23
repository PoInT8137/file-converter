import ctypes
import os
import subprocess
from ctypes import wintypes
from pathlib import Path


def open_path(path):
    try:
        os.startfile(str(path))
        return True
    except OSError:
        return False


def show_in_folder(path):
    path = Path(path)
    try:
        if path.exists() and path.is_file():
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            folder = path if path.is_dir() else path.parent
            os.startfile(str(folder))
        return True
    except OSError:
        return False


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


def send_to_trash(path):
    """Перемещает файл в корзину, а не удаляет насовсем."""
    FO_DELETE = 3
    FOF_ALLOWUNDO, FOF_NOCONFIRMATION, FOF_SILENT, FOF_NOERRORUI = 0x40, 0x10, 0x4, 0x400
    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = str(Path(path).resolve()) + "\0"
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    try:
        return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0
    except Exception:
        return False


def human_size(n):
    n = float(n)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or unit == "ГБ":
            return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
        n /= 1024
