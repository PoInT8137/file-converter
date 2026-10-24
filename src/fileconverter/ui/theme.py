import ctypes
import os
import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk
from customtkinter.windows.widgets.appearance_mode import AppearanceModeTracker
from PIL import Image

from ..config import assets_dir

# цвета парами (светлая тема, тёмная тема): CustomTkinter сам берёт нужный и перекрашивает виджеты при смене темы
BG = ("#ECEEF1", "#0B0E12")
MAIN = ("#FFFFFF", "#14181D")
BAR = ("#F5F6F8", "#0F1318")
QUEUE = ("#F8F9FA", "#12161B")
CARD = ("#F6F7F9", "#1B2128")
CARD_SEL = ("#ECEEF2", "#222A33")
BORDER = ("#E1E4E9", "#2A323C")
BORDER_BTN = ("#C9CFD8", "#3B4654")
TEXT = ("#161B22", "#E6EAF0")
MUTED = ("#69727E", "#9AA6B5")
CAPTION = ("#3A424D", "#C5CDD8")
ACCENT = ("#F5A524", "#F5A524")
ACCENT_HOVER = ("#E8960F", "#FFB845")
# янтарный текст и значки на светлом фоне темнее, иначе не читаются
ACCENT_TEXT = ("#A86400", "#F5A524")
ON_ACCENT = ("#14181D", "#14181D")
ON_ACCENT_DIM = ("#5C4513", "#4A3B1E")
ON_ACCENT_DISABLED = ("#8A7650", "#6B5A3A")
SUCCESS = ("#1F8A4C", "#5BD38A")
ERROR = ("#CC3B3B", "#F06A6A")
DASH = ("#AAB2BD", "#5A6878")
RADIUS = 6
H = 44

ICON_COLORS = {"muted": MUTED, "accent": ACCENT_TEXT, "text": TEXT, "dark": ON_ACCENT}
THEMES = [("system", "Как в системе"), ("light", "Светлая"), ("dark", "Тёмная")]

SANS = "Segoe UI"
MONO = "Consolas"

# в тестах окна создаются полностью прозрачными: они отвечают на события, но не мешают на экране
HIDDEN = os.environ.get("FILECONVERTER_HIDDEN") == "1"

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
_fonts = {}
# старые объекты не удаляем: их __del__ обращается к Tcl и не должен сработать в фоновом потоке
_keep = []


def conceal(window):
    if HIDDEN:
        try:
            window.attributes("-alpha", 0.0)
        except tk.TclError:
            pass


def is_dark():
    return AppearanceModeTracker.get_mode() == 1


def color(value):
    """Один цвет для текущей темы: нужен обычным виджетам Tk, которые не понимают пары."""
    if isinstance(value, (tuple, list)):
        return value[1 if is_dark() else 0]
    return value


def apply_theme(name):
    ctk.set_appearance_mode(name if name in ("light", "dark") else "system")


def reset_cache():
    """Картинки и шрифты привязаны к окну Tk, при новом главном окне кэш создаётся заново."""
    _keep.extend(list(_icons.values()) + list(_ui.values()) + list(_fonts.values()))
    _icons.clear()
    _ui.clear()
    _fonts.clear()


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


def _font(family, size, weight):
    key = (family, size, weight)
    if key not in _fonts:
        _fonts[key] = ctk.CTkFont(family=family, size=size, weight=weight)
    return _fonts[key]


def font(size=13, weight="normal"):
    return _font(SANS, size, weight)


def mono(size=12, weight="normal"):
    return _font(MONO, size, weight)


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


def _tinted(alpha, hex_color):
    img = Image.new("RGBA", alpha.size, hex_color)
    img.putalpha(alpha)
    return img


def ui_icon(name, color="muted", size=20):
    """Значок интерфейса. Цвет берётся из темы: из готового PNG нужна только форма (прозрачность)."""
    key = (name, color, size)
    if key in _ui:
        return _ui[key]
    try:
        alpha = Image.open(assets_dir() / "ui" / f"{name}_text.png").convert("RGBA").getchannel("A")
    except OSError:
        alpha = Image.new("L", (48, 48), 0)
    light, dark = ICON_COLORS.get(color, MUTED)
    _ui[key] = ctk.CTkImage(light_image=_tinted(alpha, light), dark_image=_tinted(alpha, dark), size=(size, size))
    return _ui[key]


def logo_image(size=28):
    try:
        img = Image.open(assets_dir() / "logo_64.png").convert("RGBA")
    except OSError:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
