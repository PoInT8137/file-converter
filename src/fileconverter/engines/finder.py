import importlib.util
import os
import shutil
import threading
from pathlib import Path

from ..config import engines_dirs
from .base import run

# имя движка: (exe, папки установки по умолчанию)
EXTERNAL = {
    "libreoffice": ("soffice.exe", [r"LibreOffice\program"]),
    "tesseract": ("tesseract.exe", [r"Tesseract-OCR"]),
    "ffmpeg": ("ffmpeg.exe", []),
    "ffprobe": ("ffprobe.exe", []),
    "pandoc": ("pandoc.exe", [r"Pandoc"]),
}

PYTHON_LIBS = {"pdf2docx": "pdf2docx", "pymupdf": "pymupdf"}

ENGINE_TITLES = {
    "libreoffice": "LibreOffice", "pdf2docx": "pdf2docx", "pymupdf": "PyMuPDF",
    "pandoc": "Pandoc", "ffmpeg": "FFmpeg", "tesseract": "Tesseract", "pillow": "Pillow",
}

DOWNLOAD_HINTS = {
    "libreoffice": "Установите LibreOffice с сайта libreoffice.org. Нужен для документов, таблиц и презентаций.",
    "tesseract": "Установите Tesseract OCR (сборка UB Mannheim с github.com/UB-Mannheim/tesseract) "
                 "с языками rus и eng. Нужен для распознавания текста.",
    "ffmpeg": "Скачайте FFmpeg с gyan.dev и положите ffmpeg.exe и ffprobe.exe в папку engines рядом с программой.",
    "pandoc": "Скачайте Pandoc с github.com/jgm/pandoc/releases и положите pandoc.exe в папку engines.",
    "pdf2docx": "Библиотека pdf2docx входит в сборку. Если её нет, переустановите программу.",
    "pymupdf": "Библиотека PyMuPDF входит в сборку. Если её нет, переустановите программу.",
}


def program_files_dirs():
    result = []
    for var in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432", "LOCALAPPDATA"):
        value = os.environ.get(var)
        if value:
            result.append(Path(value))
            if var == "LOCALAPPDATA":
                result.append(Path(value) / "Programs")
    return result


def candidate_paths(name, custom=None):
    exe, install_dirs = EXTERNAL[name]
    paths = [d / exe for d in engines_dirs()]
    found = shutil.which(exe)
    if found:
        paths.append(Path(found))
    for root in program_files_dirs():
        for sub in install_dirs:
            paths.append(root / sub / exe)
    if custom:
        custom = Path(custom)
        paths.append(custom / exe if custom.is_dir() else custom)
    return paths


def find_tool(name, custom=None):
    for p in candidate_paths(name, custom):
        try:
            if p.is_file():
                return p
        except OSError:
            continue
    return None


class Engines:
    """Найденные движки. Поиск выполняется один раз и по кнопке «Найти заново»."""

    def __init__(self, settings=None):
        self.settings = settings
        self.lock = threading.Lock()
        self.paths = {}
        self.libs = {}
        self.tess_langs = []
        self.refresh()

    def refresh(self):
        custom = {}
        if self.settings:
            custom["libreoffice"] = self.settings.get("libreoffice_path")
            custom["tesseract"] = self.settings.get("tesseract_path")
        paths = {}
        for name in EXTERNAL:
            paths[name] = find_tool(name, custom.get(name))
        libs = {name: importlib.util.find_spec(mod) is not None for name, mod in PYTHON_LIBS.items()}
        langs = []
        if paths.get("tesseract"):
            try:
                _, out = run([paths["tesseract"], "--list-langs"], timeout=20)
                langs = [l.strip() for l in out.splitlines()[1:] if l.strip()]
            except Exception:
                langs = []
        with self.lock:
            self.paths = paths
            self.libs = libs
            self.tess_langs = langs

    def path(self, name):
        return self.paths.get(name)

    def available(self, name):
        if name in ("pillow", "pptx"):
            return True
        if name in PYTHON_LIBS:
            return self.libs.get(name, False)
        if name == "ocr":
            return self.paths.get("tesseract") is not None
        return self.paths.get(name) is not None

    def status(self):
        names = ["libreoffice", "pdf2docx", "pymupdf", "pandoc", "ffmpeg", "tesseract"]
        return [(n, ENGINE_TITLES[n], self.available(n)) for n in names]

    def describe(self, name):
        if self.available(name):
            p = self.paths.get(name)
            text = f"{ENGINE_TITLES[name]} найден"
            if p:
                text += f": {p}"
            if name == "tesseract" and self.tess_langs:
                text += f"\nЯзыки: {', '.join(self.tess_langs)}"
            return text
        return f"{ENGINE_TITLES[name]} не найден.\n{DOWNLOAD_HINTS.get(name, '')}"
