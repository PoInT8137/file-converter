from dataclasses import dataclass, field
from pathlib import Path

from .engines import ffmpeg, images, libreoffice, pandoc, pdf
from .engines.base import Context

ALIASES = {"jpeg": "jpg", "tif": "tiff", "htm": "html", "heif": "heic", "markdown": "md"}

# расширение: (название, категория)
FORMATS = {
    "pdf": ("Документ PDF", "docs"), "docx": ("Word", "docs"), "doc": ("Word 97-2003", "docs"),
    "odt": ("OpenDocument", "docs"), "rtf": ("Rich Text", "docs"), "epub": ("Электронная книга", "docs"),
    "txt": ("Обычный текст", "text"), "html": ("Веб-страница", "text"), "md": ("Markdown", "text"),
    "xlsx": ("Excel", "tables"), "xls": ("Excel 97-2003", "tables"), "ods": ("OpenDocument таблица", "tables"),
    "csv": ("Таблица CSV", "tables"),
    "pptx": ("PowerPoint", "slides"), "ppt": ("PowerPoint 97-2003", "slides"), "odp": ("OpenDocument слайды", "slides"),
    "png": ("Картинка PNG", "images"), "jpg": ("Картинка JPG", "images"), "webp": ("Картинка WEBP", "images"),
    "bmp": ("Картинка BMP", "images"), "gif": ("Анимация GIF", "images"), "tiff": ("Картинка TIFF", "images"),
    "ico": ("Значок ICO", "images"), "heic": ("Фото HEIC", "images"),
    "mp3": ("Аудио MP3", "audio"), "wav": ("Аудио WAV", "audio"), "flac": ("Аудио FLAC", "audio"),
    "ogg": ("Аудио OGG", "audio"), "m4a": ("Аудио M4A", "audio"), "aac": ("Аудио AAC", "audio"),
    "opus": ("Аудио OPUS", "audio"),
    "mp4": ("Видео MP4", "video"), "mkv": ("Видео MKV", "video"), "avi": ("Видео AVI", "video"),
    "mov": ("Видео MOV", "video"), "webm": ("Видео WEBM", "video"),
}

CATEGORIES = [
    ("docs", "Документы"), ("tables", "Таблицы"), ("slides", "Презентации"), ("images", "Изображения"),
    ("text", "Текст и веб"), ("audio", "Аудио"), ("video", "Видео"),
]
CATEGORY_NAMES = dict(CATEGORIES)

ENGINE_LABELS = {
    "libreoffice": "LibreOffice", "pdf2docx": "pdf2docx", "pymupdf": "PyMuPDF", "pillow": "Pillow",
    "ffmpeg": "FFmpeg", "pandoc": "Pandoc", "tesseract": "Tesseract",
}

NOTES = {
    ("pdf", "docx"): "Вёрстка может немного поехать, это особенность формата PDF.",
    ("pdf", "pptx"): "Слайды будут картинками, текст не редактируется.",
    ("pdf", "xlsx"): "Переносятся только найденные на страницах таблицы.",
    ("pdf", "txt"): "Для сканов без текстового слоя используйте распознавание (OCR).",
}


def norm(ext):
    ext = (ext or "").lower().lstrip(".")
    return ALIASES.get(ext, ext)


def ext_of(path):
    return norm(Path(path).suffix)


def category(ext):
    return FORMATS.get(norm(ext), ("", "other"))[1]


def title(ext):
    return FORMATS.get(norm(ext), (norm(ext).upper(), "other"))[0]


@dataclass
class Conversion:
    src: str
    dst: str
    engine: str
    func: object = None
    steps: list = field(default_factory=list)

    @property
    def engines_needed(self):
        if self.steps:
            return [s.engine for s in self.steps]
        return [self.engine]

    @property
    def engine_label(self):
        names = []
        for e in self.engines_needed:
            label = ENGINE_LABELS.get(e, e)
            if label not in names:
                names.append(label)
        return " + ".join(names)

    @property
    def label(self):
        return f"{self.src.upper()} в {self.dst.upper()}"

    @property
    def note(self):
        if self.steps:
            return f"Через промежуточный {self.steps[0].dst.upper()}."
        return NOTES.get((self.src, self.dst), "")

    def available(self, engines):
        return all(engines.available(e) for e in self.engines_needed)

    def run(self, engines, src, dst, ctx):
        if not self.steps:
            return self.func(engines, Path(src), Path(dst), ctx)
        first, second = self.steps
        with ctx.tempdir() as tmp:
            mid = Path(tmp) / f"{Path(src).stem}.{first.dst}"
            sub = Context(ctx.quality, lambda p: ctx.progress(p * 0.5), ctx.log, ctx.namer)
            first.run(engines, src, mid, sub)
            sub = Context(ctx.quality, lambda p: ctx.progress(0.5 + p * 0.5), ctx.log, ctx.namer)
            return second.run(engines, mid, dst, sub)


# промежуточный формат: для каких результатов разрешена цепочка
CHAIN_RULES = [("pdf", {"png", "jpg"}), ("docx", {"pdf", "odt", "rtf"}), ("html", {"pdf"})]


class Registry:
    def __init__(self):
        self.table = {}

    def add(self, sources, targets, engine, func):
        for s in sources:
            for d in targets:
                if s == d:
                    continue
                self.table.setdefault((s, d), []).append(Conversion(s, d, engine, func))

    def direct(self, src, dst, engines=None):
        options = self.table.get((norm(src), norm(dst)), [])
        if engines is None:
            return options[0] if options else None
        for c in options:
            if c.available(engines):
                return c
        return None

    def chain(self, src, dst, engines=None):
        src, dst = norm(src), norm(dst)
        for mid, allowed in CHAIN_RULES:
            if dst not in allowed or mid in (src, dst):
                continue
            a = self.direct(src, mid, engines)
            b = self.direct(mid, dst, engines)
            if a and b:
                return Conversion(src, dst, a.engine, steps=[a, b])
        return None

    def get(self, src, dst, engines=None):
        return self.direct(src, dst, engines) or self.chain(src, dst, engines)

    def sources(self):
        return sorted({s for s, _ in self.table})

    def accepts(self, ext):
        return norm(ext) in self.sources()

    def targets(self, src, engines=None):
        """Все возможные форматы результата для файла, сначала прямые, потом цепочки."""
        src = norm(src)
        result = []
        seen = set()
        dsts = [d for (s, d) in self.table if s == src]
        for _, allowed in CHAIN_RULES:
            dsts += sorted(allowed)
        for d in dsts:
            if d in seen or d == src:
                continue
            c = self.get(src, d, engines)
            if c:
                result.append(c)
                seen.add(d)
        order = list(FORMATS)
        result.sort(key=lambda c: (bool(c.steps), order.index(c.dst) if c.dst in order else 99))
        return result

    def all_conversions(self, engines=None):
        result = []
        for s in self.sources():
            result += self.targets(s, engines)
        return result


DOC_SRC = ["doc", "docx", "odt", "rtf", "txt"]
DOC_DST = ["pdf", "docx", "odt", "rtf", "txt", "html"]
SLIDE_SRC = ["ppt", "pptx", "odp"]
TABLE_SRC = ["xls", "xlsx", "ods", "csv"]
IMG_SRC = ["png", "jpg", "webp", "bmp", "gif", "tiff", "ico", "heic"]
IMG_DST = ["png", "jpg", "webp", "bmp", "gif", "tiff", "ico"]


def build():
    r = Registry()
    r.add(DOC_SRC, DOC_DST, "libreoffice", libreoffice.convert)
    r.add(["html"], ["pdf", "docx", "odt"], "libreoffice", libreoffice.convert)
    r.add(SLIDE_SRC, ["pdf", "odp", "pptx"], "libreoffice", libreoffice.convert)
    r.add(TABLE_SRC, ["pdf", "xlsx", "ods", "csv", "html"], "libreoffice", libreoffice.convert)
    r.add(["pdf"], ["docx"], "pdf2docx", pdf.to_docx)
    r.add(["pdf"], ["txt"], "pymupdf", pdf.to_txt)
    r.add(["pdf"], ["html"], "pymupdf", pdf.to_html)
    r.add(["pdf"], ["png", "jpg"], "pymupdf", pdf.to_images)
    r.add(["pdf"], ["pptx"], "pymupdf", pdf.to_pptx)
    r.add(["pdf"], ["xlsx"], "pymupdf", pdf.to_xlsx)
    r.add(IMG_SRC, IMG_DST, "pillow", images.convert)
    r.add(IMG_SRC, ["pdf"], "pymupdf", pdf.image_to_pdf)
    r.add(ffmpeg.AUDIO, ffmpeg.AUDIO, "ffmpeg", ffmpeg.convert)
    r.add(ffmpeg.VIDEO, ffmpeg.VIDEO + ["mp3", "m4a", "wav", "gif"], "ffmpeg", ffmpeg.convert)
    r.add(["gif"], ["mp4", "webm"], "ffmpeg", ffmpeg.convert)
    r.add(pandoc.FORMATS, pandoc.FORMATS, "pandoc", pandoc.convert)
    return r


registry = build()
