import itertools
import queue
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .engines.base import Context, ConvertError
from .naming import Namer, release
from .osutils import open_path, send_to_trash, show_in_folder
from .registry import ext_of

WAIT, RUN, DONE, ERROR = "wait", "run", "done", "error"

_ids = itertools.count(1)


def friendly_error(e):
    if isinstance(e, ConvertError):
        return str(e)
    if isinstance(e, PermissionError):
        return "Нет доступа к файлу. Возможно, он открыт в другой программе."
    if isinstance(e, FileNotFoundError):
        return "Файл не найден. Возможно, его переместили или удалили."
    if isinstance(e, MemoryError):
        return "Не хватило памяти для обработки файла."
    if isinstance(e, OSError):
        return f"Ошибка при работе с файлом: {e.strerror or e}"
    return f"Не удалось выполнить операцию: {e}"


class Job:
    def __init__(self, files, title, conversion=None, tool=None, params=None):
        self.id = next(_ids)
        self.files = [Path(f) for f in files]
        self.title = title
        self.conversion = conversion
        self.tool = tool
        self.params = params or {}
        self.status = WAIT
        self.progress = 0.0
        self.log = []
        self.outputs = []
        self.error = ""
        self.started = None
        self.finished = None

    @property
    def dst_ext(self):
        return self.conversion.dst if self.conversion else ""


class JobQueue:
    """Очередь задач. Потоки только кладут события в self.events, UI забирает их через after()."""

    def __init__(self, engines, settings, stats=None, history=None, workers=2):
        self.engines = engines
        self.settings = settings
        self.stats = stats
        self.history = history
        self.events = queue.Queue()
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")
        self.jobs = []
        self.lock = threading.Lock()

    def submit(self, job):
        with self.lock:
            self.jobs.append(job)
        self.events.put(("update", job))
        return self.pool.submit(self._run, job)

    def convert(self, path, conversion):
        job = Job([path], f"{Path(path).name} в {conversion.dst.upper()}", conversion=conversion)
        return job, self.submit(job)

    def run_tool(self, files, tool, params):
        job = Job(files, tool.title, tool=tool, params=params)
        return job, self.submit(job)

    def _log(self, job, text):
        line = f"{time.strftime('%H:%M:%S')}  {text}"
        job.log.append(line)
        self.events.put(("log", job, line))

    def _progress(self, job, value):
        if value - job.progress >= 0.01 or value >= 1.0:
            job.progress = value
            self.events.put(("update", job))

    def _run(self, job):
        job.status = RUN
        job.started = time.time()
        self.events.put(("update", job))
        namer = Namer(self.settings.get("output_dir"), self.settings.get("name_template"))
        ctx = Context(self.settings.get("quality"), lambda p: self._progress(job, p),
                      lambda t: self._log(job, t), namer)
        planned = None
        try:
            for f in job.files:
                if not f.exists():
                    raise FileNotFoundError(str(f))
            if job.conversion:
                src = job.files[0]
                self._log(job, f"Старт: {src.name} в {job.conversion.dst.upper()} ({job.conversion.engine_label})")
                planned = namer.file(src, job.conversion.dst)
                job.outputs = job.conversion.run(self.engines, src, planned, ctx)
            else:
                self._log(job, f"Старт: {job.tool.title}, файлов: {len(job.files)}")
                job.outputs = job.tool.func(self.engines, job.files, ctx, job.params)
            job.outputs = [Path(p) for p in job.outputs if Path(p).exists()]
            if not job.outputs:
                raise ConvertError("Результат не получен")
            job.status = DONE
            job.progress = 1.0
            self._after_success(job)
        except Exception as e:
            job.status = ERROR
            job.error = friendly_error(e)
            self._log(job, f"Ошибка: {job.error}")
            if not isinstance(e, ConvertError):
                detail = traceback.format_exc(limit=3).strip().splitlines()[-1]
                job.log.append(f"           {detail}")
            if self.history:
                self.history.add(job.files[0] if job.files else "", "", ERROR, job.error)
        finally:
            if planned is not None:
                release(planned)
            job.finished = time.time()
            self.events.put(("done", job))

    def _after_success(self, job):
        first = job.outputs[0]
        if len(job.outputs) > 1:
            self._log(job, f"Готово: {len(job.outputs)} файлов в {first.parent.name}")
        else:
            self._log(job, f"Готово: {first.name}")
        if job.conversion and self.stats:
            self.stats.add(ext_of(job.files[0]), job.conversion.dst, first)
        elif self.stats:
            self.stats.recent.insert(0, {"path": str(first), "time": time.time()})
            self.stats.recent = self.stats.recent[:10]
            self.stats.save()
        if self.history:
            for src in job.files:
                self.history.add(src, first, DONE)
        if self.settings.get("open_after"):
            if len(job.outputs) > 1:
                show_in_folder(first)
            else:
                open_path(first)
        if self.settings.get("delete_source"):
            for src in job.files:
                if src in job.outputs:
                    continue
                if send_to_trash(src):
                    self._log(job, f"Исходный файл перемещён в корзину: {src.name}")

    def shutdown(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
