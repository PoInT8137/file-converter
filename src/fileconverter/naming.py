import re
import threading
import time
from pathlib import Path

BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

_reserved = set()
_lock = threading.Lock()


def _taken(path):
    return path.exists() or str(path).lower() in _reserved


def unique_path(path, is_dir=False):
    """Свободное имя: file.pdf, file (1).pdf, file (2).pdf и так далее."""
    path = Path(path)
    with _lock:
        candidate = path
        n = 1
        while _taken(candidate):
            if is_dir:
                candidate = path.with_name(f"{path.name} ({n})")
            else:
                candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
            n += 1
        _reserved.add(str(candidate).lower())
        return candidate


def release(path):
    with _lock:
        _reserved.discard(str(path).lower())


def apply_template(template, src):
    src = Path(src)
    now = time.localtime()
    try:
        name = (template or "{name}").format(
            name=src.stem, ext=src.suffix.lstrip(".").lower(),
            date=time.strftime("%Y-%m-%d", now), time=time.strftime("%H-%M", now),
        )
    except (KeyError, IndexError, ValueError):
        name = src.stem
    name = BAD_CHARS.sub("_", name).strip(" .")
    return name or src.stem


class Namer:
    def __init__(self, output_dir="", template="{name}"):
        self.output_dir = output_dir
        self.template = template

    def folder_for(self, src):
        if self.output_dir:
            d = Path(self.output_dir)
            try:
                d.mkdir(parents=True, exist_ok=True)
                return d
            except OSError:
                pass
        return Path(src).parent

    def file(self, src, ext, tag=""):
        src = Path(src)
        stem = apply_template(self.template, src)
        if tag:
            stem = f"{stem}_{tag}"
        path = self.folder_for(src) / f"{stem}.{ext.lower()}"
        if path.resolve() == src.resolve():
            path = path.with_name(f"{stem} (1).{ext.lower()}")
        return unique_path(path)

    def folder(self, src, tag=""):
        src = Path(src)
        stem = apply_template(self.template, src)
        if tag:
            stem = f"{stem}_{tag}"
        return unique_path(self.folder_for(src) / stem, is_dir=True)


def pages_folder(dst):
    """Папка для многостраничного результата рядом с запланированным файлом."""
    dst = Path(dst)
    folder = unique_path(dst.with_suffix(""), is_dir=True)
    folder.mkdir(parents=True, exist_ok=True)
    return folder
