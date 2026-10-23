import itertools
import queue
import threading
import time
import traceback
import shutil
from pathlib import Path

from .engines.base import Cancelled, Context, ConvertError, set_current
from .naming import Namer
from .osutils import open_path, send_to_trash, show_in_folder
from .registry import ext_of

WAIT, RUN, DONE, ERROR, CANCEL = "wait", "run", "done", "error", "cancel"

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
        self.ctx = None
        self.cancel_requested = False
        self.done_event = threading.Event()

    def result(self, timeout=None):
        if not self.done_event.wait(timeout):
            raise TimeoutError("задача не завершилась вовремя")
        return self

    @property
    def dst_ext(self):
        return self.conversion.dst if self.conversion else ""


class JobQueue:
    """Очередь задач. Потоки только кладут события в self.events, UI забирает их через after().

    Рабочие потоки фоновые (daemon), поэтому закрытие окна не ждёт конца долгой конвертации.
    """

    def __init__(self, engines, settings, stats=None, history=None, workers=2):
        self.engines = engines
        self.settings = settings
        self.stats = stats
        self.history = history
        self.events = queue.Queue()
        self.pending = queue.Queue()
        self.jobs = []
        self.lock = threading.Lock()
        self.threads = []
        for i in range(workers):
            th = threading.Thread(target=self._worker, name=f"job{i}", daemon=True)
            th.start()
            self.threads.append(th)

    def _worker(self):
        while True:
            job = self.pending.get()
            if job is None:
                return
            self._run(job)

    def submit(self, job):
        with self.lock:
            self.jobs.append(job)
        self.events.put(("update", job))
        self.pending.put(job)
        return job

    def convert(self, path, conversion):
        job = Job([path], f"{Path(path).name} в {conversion.dst.upper()}", conversion=conversion)
        return job, self.submit(job)

    def run_tool(self, files, tool, params):
        job = Job(files, tool.title, tool=tool, params=params)
        return job, self.submit(job)

    def active(self):
        with self.lock:
            return [j for j in self.jobs if j.status in (WAIT, RUN)]

    def cancel(self, job):
        job.cancel_requested = True
        if job.ctx is not None:
            job.ctx.cancel()

    def cancel_all(self):
        for job in self.active():
            self.cancel(job)

    def _log(self, job, text):
        line = f"{time.strftime('%H:%M:%S')}  {text}"
        job.log.append(line)
        self.events.put(("log", job, line))

    def _progress(self, job, value):
        if value - job.progress >= 0.01 or value >= 1.0:
            job.progress = value
            self.events.put(("update", job))

    def _run(self, job):
        namer = Namer(self.settings.get("output_dir"), self.settings.get("name_template"))
        ctx = Context(self.settings.get("quality"), lambda p: self._progress(job, p),
                      lambda t: self._log(job, t), namer)
        job.ctx = ctx
        set_current(ctx)
        try:
            if job.cancel_requested:
                raise Cancelled()
            job.status = RUN
            job.started = time.time()
            self.events.put(("update", job))
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
            ctx.check()
            job.outputs = [Path(p) for p in job.outputs if Path(p).exists()]
            if not job.outputs:
                raise ConvertError("Результат не получен")
            job.status = DONE
            job.progress = 1.0
            self._after_success(job)
        except Cancelled:
            job.status = CANCEL
            job.error = "Отменено"
            self._remove_partial(namer)
            self._log(job, "Отменено, незаконченные файлы удалены")
        except Exception as e:
            job.status = ERROR
            job.error = friendly_error(e)
            self._remove_partial(namer)
            self._log(job, f"Ошибка: {job.error}")
            if not isinstance(e, ConvertError):
                detail = traceback.format_exc(limit=3).strip().splitlines()[-1]
                job.log.append(f"           {detail}")
            if self.history:
                self.history.add(job.files[0] if job.files else "", "", ERROR, job.error)
        finally:
            set_current(None)
            namer.release_all()
            job.finished = time.time()
            job.done_event.set()
            self.events.put(("done", job))

    @staticmethod
    def _remove_partial(namer):
        # имена занимались только под несуществующие пути, значит всё по ним создала эта задача
        for p in namer.reserved:
            p = Path(p)
            try:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                elif p.exists():
                    p.unlink()
            except OSError:
                pass

    def _after_success(self, job):
        first = job.outputs[0]
        if len(job.outputs) > 1:
            self._log(job, f"Готово: {len(job.outputs)} файлов в {first.parent.name}")
        else:
            self._log(job, f"Готово: {first.name}")
        if job.conversion and self.stats:
            self.stats.add(ext_of(job.files[0]), job.conversion.dst, first)
        elif self.stats:
            self.stats.add_recent(first)
        if self.history:
            for src in job.files:
                self.history.add(src, first, DONE)
        if self.settings.get("open_after"):
            if len(job.outputs) > 1:
                show_in_folder(first)
            else:
                open_path(first)
        # только для конвертации: инструменты вроде объединения не должны отправлять в корзину все исходники
        if job.conversion and self.settings.get("delete_source"):
            src = job.files[0]
            if src not in job.outputs and send_to_trash(src):
                self._log(job, f"Исходный файл перемещён в корзину: {src.name}")

    def shutdown(self):
        self.cancel_all()
        for _ in self.threads:
            self.pending.put(None)