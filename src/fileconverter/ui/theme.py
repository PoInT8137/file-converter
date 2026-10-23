import ctypes
import tkinter.font as tkfont

import customtkinter as ctk
from PIL import Image

from ..config import assets_dir

BG = "#0B0E12"
MAIN = "#14181D"
BAR = "#0F1318"
QUEUE = "#12161B"
CARD = "#1B2128"
CARD_SEL = "#222A33"
BORDER = "#2A323C"
BORDER_BTN = "#3B4654"
TEXT = "#E6EAF0"
MUTED = "#9AA6B5"
CAPTION = "#C5CDD8"
ACCENT = "#F5A524"
ACCENT_HOVER = "#FFB845"
ON_ACCENT = "#14181D"
SUCCESS = "#5BD38A"
ERROR = "#F06A6A"
DASH = "#5A6878"
RADIUS = 6
H = 44

SANS = "Segoe UI"
MONO = "Consolas"

ICON_FILES = {
    "doc": "doc", "docx": "docx", "xls": "xls", "xlsx": "xlsx", "csv": "csv", "ppt": "ppt", "pptx": "pptx",
    "pdf": "pdf", "odt": "odt", "ods": "ods", "odp": "odp", "rtf": "rtf", "txt": "txt", "html": "html",
    "htm": "html", "md": "md", "epub": "epub", "png": "png", "jpg": "jpg", "jpeg": "jpg", "webp": "webp",
    "gif": "gif", "bmp": "bmp", "tiff": "tiff", "tif": "tiff", "ico": "ico", "heic": "heic", "heif": "heic",
    "mp3": "mp3", "wav": "wav", "flac": "flac", "ogg": "ogg", "m4a": "m4a", "aac": "aac", "opus": "opus",
    "mp4": "mp4", "mkv": "mkv", "avi": "avi", "mov": "mov", "webm": "webm",
}

_icons = {}
_ui = {}


def load_fonts():
    """Подгружает IBM Plex только для этого процесса. Если не вышло, остаются Segoe UI и Consolas."""
    global SANS, MONO
    folder = assets_dir() / "fonts"
    FR_PRIVATE = 0x10
    for f in folder.glob("*.ttf"):
        try:
            ctypes.windll.gdi32.AddFontResourceExW(str(f), FR_PRIVATE, 0)
        except Exception:
            pass
    try:
        families = set(tkfont.families())
    except Exception:
        return
    if "IBM Plex Sans" in families:
        SANS = "IBM Plex Sans"
    if "IBM Plex Mono" in families:
        MONO = "IBM Plex Mono"


def font(size=13, weight="normal"):
    return ctk.CTkFont(family=SANS, size=size, weight=weight)


def mono(size=12, weight="normal"):
    return ctk.CTkFont(family=MONO, size=size, weight=weight)


def _scaling():
    try:
        return ctk.ScalingTracker.get_window_scaling(None)
    except Exception:
        return 1.0


def get_icon(ext, size=32):
    """Иконка формата. Для неизвестного расширения нейтральный лист."""
    ext = (ext or "").lower().lstrip(".")
    key = (ext, size)
    if key in _icons:
        return _icons[key]
    name = ICON_FILES.get(ext, "generic")
    folder = assets_dir() / "icons"
    src_size = 48 if size > 28 else 32
    path = folder / f"{name}_{src_size}.png"
    if not path.exists():
        path = folder / f"generic_{src_size}.png"
    try:
        img = Image.open(path).convert("RGBA")
    except OSError:
        img = Image.new("RGBA", (src_size, src_size), (0, 0, 0, 0))
    _icons[key] = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    return _icons[key]


def ui_icon(name, color="muted", size=20):
    key = (name, color, size)
    if key in _ui:
        return _ui[key]
    path = assets_dir() / "ui" / f"{name}_{color}.png"
    try:
        img = Image.open(path).convert("RGBA")
    except OSError:
        img = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    _ui[key] = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    return _ui[key]


def logo_image(size=28):
    try:
        img = Image.open(assets_dir() / "logo_64.png").convert("RGBA")
    except OSError:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
