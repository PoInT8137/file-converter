import threading
import time
from pathlib import Path

from .config import data_dir, read_json, write_json

DEFAULT_PAIRS = [
    ("pdf", "docx"), ("docx", "pdf"), ("pptx", "pdf"), ("xlsx", "pdf"),
    ("jpg", "pdf"), ("png", "jpg"), ("heic", "jpg"), ("mp4", "mp3"),
]


def pair_key(src, dst):
    return f"{src}>{dst}"


class Stats:
    """Счётчики конвертаций, закреплённые плитки и последние результаты."""

    def __init__(self, path=None):
        self.path = Path(path) if path else data_dir() / "stats.json"
        self.lock = threading.Lock()
        data = read_json(self.path, {})
        if not isinstance(data, dict):
            data = {}
        self.counts = dict(data.get("counts", {}))
        self.pinned = list(data.get("pinned", []))
        self.recent = list(data.get("recent", []))

    def save(self):
        try:
            write_json(self.path, {"counts": self.counts, "pinned": self.pinned, "recent": self.recent})
        except OSError:
            pass

    def add(self, src, dst, result_path=None):
        with self.lock:
            key = pair_key(src, dst)
            self.counts[key] = self.counts.get(key, 0) + 1
            if result_path:
                self.recent.insert(0, {"path": str(result_path), "time": time.time()})
                self.recent = self.recent[:10]
            self.save()

    def add_recent(self, result_path):
        with self.lock:
            self.recent.insert(0, {"path": str(result_path), "time": time.time()})
            self.recent = self.recent[:10]
            self.save()

    def count(self, src, dst):
        return self.counts.get(pair_key(src, dst), 0)

    def is_pinned(self, src, dst):
        return pair_key(src, dst) in self.pinned

    def toggle_pin(self, src, dst):
        with self.lock:
            key = pair_key(src, dst)
            if key in self.pinned:
                self.pinned.remove(key)
            else:
                self.pinned.append(key)
            self.save()

    def reset(self):
        with self.lock:
            self.counts = {}
            self.pinned = []
            self.save()

    def top_pairs(self, n=8):
        # копии под блокировкой: счётчики меняются из потоков задач
        with self.lock:
            pinned = list(self.pinned)
            counts = dict(self.counts)
        result = []
        for key in pinned:
            src, _, dst = key.partition(">")
            if (src, dst) not in result:
                result.append((src, dst))
        used = sorted(((c, k) for k, c in counts.items() if c > 0), key=lambda x: (-x[0], x[1]))
        for _, key in used:
            src, _, dst = key.partition(">")
            if (src, dst) not in result:
                result.append((src, dst))
        for pair in DEFAULT_PAIRS:
            if pair not in result:
                result.append(pair)
        return result[:n]

    def best_target(self, src, targets):
        """Самый частый формат результата для этого типа файла, иначе None."""
        best, best_count = None, 0
        for dst in targets:
            c = self.count(src, dst)
            if c > best_count:
                best, best_count = dst, c
        return best

    def recent_items(self, n=3):
        with self.lock:
            return list(self.recent[:n])


class History:
    def __init__(self, path=None, limit=500):
        self.path = Path(path) if path else data_dir() / "history.json"
        self.limit = limit
        self.lock = threading.Lock()
        data = read_json(self.path, [])
        self.items = data if isinstance(data, list) else []

    def add(self, source, result, status, message=""):
        with self.lock:
            self.items.insert(0, {
                "time": time.time(), "source": str(source), "result": str(result or ""),
                "status": status, "message": message,
            })
            self.items = self.items[: self.limit]
            try:
                write_json(self.path, self.items)
            except OSError:
                pass

    def clear(self):
        with self.lock:
            self.items = []
            try:
                write_json(self.path, self.items)
            except OSError:
                pass
