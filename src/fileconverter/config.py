import json
import os
import sys
import threading
from pathlib import Path


def base_dir():
    """Папка с ресурсами: в сборке PyInstaller это _MEIPASS, иначе корень проекта."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def exe_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return base_dir()


def assets_dir():
    return base_dir() / "assets"


def engines_dirs():
    dirs = [exe_dir() / "engines", base_dir() / "engines"]
    result = []
    for d in dirs:
        if d not in result:
            result.append(d)
    return result


def data_dir():
    root = os.environ.get("FILECONVERTER_DATA")
    if root:
        path = Path(root)
    else:
        path = Path(os.environ.get("APPDATA", Path.home())) / "FileConverter"
    path.mkdir(parents=True, exist_ok=True)
    return path


DEFAULTS = {
    "output_dir": "",
    "quality": "high",
    "open_after": False,
    "delete_source": False,
    "name_template": "{name}",
    "libreoffice_path": "",
    "tesseract_path": "",
    "params_open": False,
    "theme": "system",
    "animations": True,
}

QUALITY_NAMES = {"high": "высокое", "medium": "среднее", "low": "низкое"}


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    tmp = Path(str(path) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


class Settings:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_dir() / "settings.json"
        self.lock = threading.Lock()
        self.values = dict(DEFAULTS)
        loaded = read_json(self.path, {})
        if isinstance(loaded, dict):
            for k, v in loaded.items():
                if k in DEFAULTS:
                    self.values[k] = v

    def get(self, key):
        return self.values.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        with self.lock:
            self.values[key] = value
            try:
                write_json(self.path, self.values)
            except OSError:
                pass

    def summary(self):
        folder = self.get("output_dir") or "рядом с исходным"
        if self.get("output_dir"):
            folder = Path(folder).name or folder
        parts = [f"качество: {QUALITY_NAMES.get(self.get('quality'), 'высокое')}", f"папка: {folder}"]
        if self.get("open_after"):
            parts.append("открыть после")
        if self.get("delete_source"):
            parts.append("удалить исходный")
        return ", ".join(parts)
