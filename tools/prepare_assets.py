"""Скачивает и готовит иконки для приложения.

Запуск: .venv\\Scripts\\python.exe tools\\prepare_assets.py
Сырые SVG кэшируются в build/raw_icons, готовые PNG кладутся в assets/icons.
"""
import io
import sys
import urllib.request
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "build" / "raw_icons"
ICONS = ROOT / "assets" / "icons"
UI_ICONS = ROOT / "assets" / "ui"
FONTS = ROOT / "assets" / "fonts"

WIKI = "https://commons.wikimedia.org/wiki/Special:FilePath/"
VSI = "https://raw.githubusercontent.com/vscode-icons/vscode-icons/master/icons/"
LUCIDE = "https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/"

# в именах файлов Wikimedia стоит короткое тире, поэтому оно закодировано
WIKI_FILES = {
    "word": "Microsoft_Office_Word_(2019%E2%80%93present).svg",
    "excel": "Microsoft_Office_Excel_(2019%E2%80%93present).svg",
    "powerpoint": "Microsoft_Office_PowerPoint_(2019%E2%80%93present).svg",
    "pdf": "Adobe_Acrobat_DC_logo_2020.svg",
}

VSI_FILES = ["libreoffice_writer", "libreoffice_calc", "libreoffice_impress", "text", "html",
             "markdown", "epub", "image", "favicon", "audio", "video", "csv"]

# расширение: (базовая иконка, подпись на плашке или None)
FORMATS = {
    "doc": ("word", None), "docx": ("word", None),
    "xls": ("excel", None), "xlsx": ("excel", None), "csv": ("excel", "CSV"),
    "ppt": ("powerpoint", None), "pptx": ("powerpoint", None),
    "pdf": ("pdf", None),
    "odt": ("libreoffice_writer", None), "ods": ("libreoffice_calc", None),
    "odp": ("libreoffice_impress", None),
    "rtf": ("text", "RTF"), "txt": ("text", "TXT"),
    "html": ("html", None), "md": ("markdown", None), "epub": ("epub", None),
    "png": ("image", "PNG"), "jpg": ("image", "JPG"), "webp": ("image", "WEBP"),
    "gif": ("image", "GIF"), "bmp": ("image", "BMP"), "tiff": ("image", "TIFF"),
    "heic": ("image", "HEIC"), "ico": ("favicon", None),
    "mp3": ("audio", "MP3"), "wav": ("audio", "WAV"), "flac": ("audio", "FLAC"),
    "ogg": ("audio", "OGG"), "m4a": ("audio", "M4A"), "aac": ("audio", "AAC"),
    "opus": ("audio", "OPUS"),
    "mp4": ("video", "MP4"), "mkv": ("video", "MKV"), "avi": ("video", "AVI"),
    "mov": ("video", "MOV"), "webm": ("video", "WEBM"),
}

LUCIDE_NAMES = [
    "arrow-left-right", "file-text", "image", "clapperboard", "scan-text", "rotate-ccw-clock",
    "settings", "search", "scissors", "merge", "split", "rotate-cw", "shrink", "lock",
    "lock-open", "stamp", "info", "type", "images", "file-minus", "file-output",
    "arrow-up-down", "crop", "scaling", "eraser", "volume-2", "timer", "folder-open",
    "pin", "upload", "file", "x", "plus", "check", "chevron-down", "chevron-right",
    "arrow-right", "gauge", "combine", "audio-lines", "trash", "external-link", "layers",
    "list", "file-search",
]

UI_COLORS = {"muted": "#9AA6B5", "accent": "#F5A524", "dark": "#14181D", "text": "#E6EAF0"}


def fetch(url, dest):
    if dest.exists() and dest.stat().st_size > 0:
        return dest.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": "FileConverterAssets/1.0 (personal project)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if b"<svg" not in data[:4000]:
        raise ValueError(f"не SVG: {url}")
    if len(data) > 2_000_000:
        raise ValueError(f"слишком большой файл: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return data


def svg_to_image(svg_bytes, size):
    doc = pymupdf.open(stream=svg_bytes, filetype="svg")
    page = doc[0]
    zoom = size / max(page.rect.width, page.rect.height)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
    return canvas


def add_label(img, text):
    size = img.width
    img = img.copy()
    draw = ImageDraw.Draw(img)
    font_size = max(7, int(size * (0.26 if len(text) <= 3 else 0.21)))
    try:
        font = ImageFont.truetype(str(FONTS / "IBMPlexMono-SemiBold.ttf"), font_size)
    except OSError:
        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    pad = max(1, size // 16)
    x0 = (size - tw) // 2 - pad
    y0 = size - th - pad * 3
    draw.rounded_rectangle([x0, y0, x0 + tw + pad * 2, size - 1], radius=pad, fill="#F5A524")
    draw.text((x0 + pad - box[0], y0 + pad - box[1]), text, font=font, fill="#14181D")
    return img


def make_format_icons():
    sources = {}
    for key, name in WIKI_FILES.items():
        sources[key] = fetch(WIKI + name, RAW / f"{key}.svg")
    for key in VSI_FILES:
        sources[key] = fetch(VSI + f"file_type_{key}.svg", RAW / f"{key}.svg")
    ICONS.mkdir(parents=True, exist_ok=True)
    for ext, (base, label) in FORMATS.items():
        for size in (32, 48):
            img = svg_to_image(sources[base], size)
            if label:
                img = add_label(img, label)
            img.save(ICONS / f"{ext}_{size}.png")
    file_svg = fetch(LUCIDE + "file.svg", RAW / "lucide" / "file.svg")
    for size in (32, 48):
        svg = file_svg.replace(b"currentColor", b"#9AA6B5")
        svg_to_image(svg, size).save(ICONS / f"generic_{size}.png")


def make_ui_icons():
    UI_ICONS.mkdir(parents=True, exist_ok=True)
    for name in LUCIDE_NAMES:
        try:
            svg = fetch(LUCIDE + f"{name}.svg", RAW / "lucide" / f"{name}.svg")
        except Exception as e:
            print("пропущена иконка", name, e)
            continue
        for cname, color in UI_COLORS.items():
            data = svg.replace(b"currentColor", color.encode())
            svg_to_image(data, 48).save(UI_ICONS / f"{name}_{cname}.png")


def draw_app_icon(size):
    s = 4  # рисуем крупнее и уменьшаем, чтобы края были ровными
    big = size * s
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, big - 1, big - 1], radius=int(big * 0.18), fill="#14181D")
    amber = "#F5A524"
    w = max(2 * s, int(big * 0.085))
    m = big * 0.2
    y1, y2 = big * 0.36, big * 0.64
    head = big * 0.13
    d.line([(m, y1), (big - m - head * 0.6, y1)], fill=amber, width=w)
    d.polygon([(big - m, y1), (big - m - head, y1 - head), (big - m - head, y1 + head)], fill=amber)
    d.line([(m + head * 0.6, y2), (big - m, y2)], fill=amber, width=w)
    d.polygon([(m, y2), (m + head, y2 - head), (m + head, y2 + head)], fill=amber)
    return img.resize((size, size), Image.LANCZOS)


def make_app_icon():
    sizes = [16, 32, 48, 256]
    images = [draw_app_icon(s) for s in sizes]
    images[-1].save(ROOT / "assets" / "app.ico", sizes=[(s, s) for s in sizes], append_images=images[:-1])
    images[-1].save(ROOT / "assets" / "app_256.png")
    draw_app_icon(64).save(ROOT / "assets" / "logo_64.png")


if __name__ == "__main__":
    make_format_icons()
    make_ui_icons()
    make_app_icon()
    print("готово")
    sys.exit(0)
