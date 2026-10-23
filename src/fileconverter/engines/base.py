import os
import subprocess
import tempfile
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class ConvertError(Exception):
    """Ошибка с понятным пользователю текстом."""


class Context:
    def __init__(self, quality="high", on_progress=None, on_log=None, namer=None):
        from ..naming import Namer
        self.quality = quality
        self.on_progress = on_progress
        self.on_log = on_log
        self.namer = namer or Namer()
        self.cancelled = False

    def dpi(self):
        return {"high": 200, "medium": 150, "low": 100}.get(self.quality, 200)

    def jpeg_quality(self):
        return {"high": 92, "medium": 82, "low": 65}.get(self.quality, 92)

    def progress(self, value):
        if self.on_progress:
            self.on_progress(max(0.0, min(1.0, float(value))))

    def log(self, text):
        if self.on_log:
            self.on_log(text)

    def tempdir(self):
        return tempfile.TemporaryDirectory(prefix="fc_")


def run(cmd, timeout=None, cwd=None, on_line=None, env=None):
    """Запускает внешнюю программу без окна консоли и возвращает (код, вывод)."""
    cmd = [str(c) for c in cmd]
    startupinfo = None
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            cwd=cwd, env=env, creationflags=CREATE_NO_WINDOW, startupinfo=startupinfo,
        )
    except FileNotFoundError:
        raise ConvertError(f"Не найдена программа: {Path(cmd[0]).name}")
    except OSError as e:
        raise ConvertError(f"Не удалось запустить {Path(cmd[0]).name}: {e}")

    lines = []
    try:
        if on_line:
            for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                lines.append(line)
                on_line(line)
            proc.wait(timeout=timeout)
        else:
            out, _ = proc.communicate(timeout=timeout)
            lines = out.decode("utf-8", errors="replace").splitlines()
    except subprocess.TimeoutExpired:
        proc.kill()
        raise ConvertError(f"{Path(cmd[0]).name} не ответил вовремя, процесс остановлен")
    return proc.returncode, "\n".join(lines)


def last_lines(text, n=3):
    lines = [l for l in text.splitlines() if l.strip()]
    return " | ".join(lines[-n:])


def ensure_output(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        raise ConvertError("Движок завершил работу, но файл результата не появился")
    return path
