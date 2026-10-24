from dataclasses import dataclass, field

from .engines import ffmpeg, images, ocr, pdf
from .registry import ext_of

IMAGE_EXTS = ["png", "jpg", "webp", "bmp", "gif", "tiff", "heic", "ico"]
MEDIA_EXTS = ffmpeg.AUDIO + ffmpeg.VIDEO


@dataclass
class Field:
    key: str
    label: str
    kind: str = "text"
    default: str = ""
    options: list = field(default_factory=list)
    hint: str = ""
    required: bool = False


@dataclass
class Tool:
    id: str
    title: str
    desc: str
    section: str
    group: str
    icon: str
    func: object
    exts: list
    engine: str = "pymupdf"
    min_files: int = 1
    fields: list = field(default_factory=list)
    verb: str = ""

    def accepts(self, path):
        return ext_of(path) in self.exts

    def action_text(self, count):
        verb = self.verb or self.title
        if self.id in ("pdf_merge", "media_concat", "img_to_pdf"):
            return f"{verb}: {count} {plural(count)} в один"
        return f"{verb}: {count} {plural(count)}"


def plural(n):
    if n % 10 == 1 and n % 100 != 11:
        return "файл"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "файла"
    return "файлов"


def _ocr_each(kind):
    def run(engines, files, ctx, params):
        func = {"txt": ocr.to_txt, "docx": ocr.to_docx, "pdf": ocr.to_pdf}[kind]
        outputs = []
        for src in files:
            dst = ctx.namer.file(src, kind, "ocr" if kind == "pdf" else "")
            outputs += func(engines, src, dst, ctx)
        return outputs
    return run


def _extract_audio(engines, files, ctx, params):
    outputs = []
    for src in files:
        dst = ctx.namer.file(src, params.get("format", "mp3"))
        outputs += ffmpeg.convert(engines, src, dst, ctx)
    return outputs


def _images_to_pdf(engines, files, ctx, params):
    dst = ctx.namer.file(files[0], "pdf", "картинки")
    return pdf.images_to_pdf(engines, files, dst, ctx)


PAGES = Field("pages", "Страницы", hint="Например: 1-3, 5, 8-", required=True)
LEVEL = Field("level", "Степень сжатия", "choice", "medium",
              [("low", "Слабое"), ("medium", "Среднее"), ("high", "Сильное")])
ANGLE = Field("angle", "Поворот", "choice", "90",
              [("90", "90 по часовой"), ("180", "180"), ("270", "90 против часовой")])

TOOLS = [
    Tool("pdf_merge", "Объединить", "Несколько PDF в один файл", "pdf", "СТРАНИЦЫ", "merge",
         pdf.merge, ["pdf"], min_files=2, verb="Объединить"),
    Tool("pdf_split", "Разделить", "По страницам или по диапазонам", "pdf", "СТРАНИЦЫ", "split",
         pdf.split, ["pdf"], verb="Разделить",
         fields=[Field("ranges", "Диапазоны через точку с запятой",
                       hint="Пусто: каждая страница отдельно. Пример: 1-3; 4-6; 7-")]),
    Tool("pdf_extract", "Извлечь страницы", "Выбранные страницы в новый PDF", "pdf", "СТРАНИЦЫ", "file-output",
         pdf.extract_pages, ["pdf"], fields=[PAGES], verb="Извлечь страницы"),
    Tool("pdf_delete", "Удалить страницы", "Убрать лишние страницы", "pdf", "СТРАНИЦЫ", "file-minus",
         pdf.delete_pages, ["pdf"], fields=[PAGES], verb="Удалить страницы"),
    Tool("pdf_rotate", "Повернуть", "Все или выбранные страницы", "pdf", "СТРАНИЦЫ", "rotate-cw",
         pdf.rotate, ["pdf"], fields=[ANGLE, Field("pages", "Страницы", hint="Пусто: все страницы")],
         verb="Повернуть"),
    Tool("pdf_reorder", "Переставить страницы", "Новый порядок страниц", "pdf", "СТРАНИЦЫ", "arrow-up-down",
         pdf.reorder, ["pdf"], fields=[Field("order", "Новый порядок", hint="Например: 3, 1, 2, 4-", required=True)],
         verb="Переставить страницы"),
    Tool("pdf_compress", "Сжать", "Уменьшить размер файла", "pdf", "ОПТИМИЗАЦИЯ И ЗАЩИТА", "shrink",
         pdf.compress, ["pdf"], fields=[LEVEL], verb="Сжать"),
    Tool("pdf_encrypt", "Поставить пароль", "Шифрование AES-256", "pdf", "ОПТИМИЗАЦИЯ И ЗАЩИТА", "lock",
         pdf.encrypt, ["pdf"], fields=[Field("password", "Пароль", "password", required=True)], verb="Поставить пароль"),
    Tool("pdf_decrypt", "Снять пароль", "Если пароль известен", "pdf", "ОПТИМИЗАЦИЯ И ЗАЩИТА", "lock-open",
         pdf.decrypt, ["pdf"], fields=[Field("password", "Текущий пароль", "password", required=True)], verb="Снять пароль"),
    Tool("pdf_watermark", "Водяной знак", "Текст по диагонали страницы", "pdf", "ОПТИМИЗАЦИЯ И ЗАЩИТА", "stamp",
         pdf.watermark, ["pdf"], verb="Добавить водяной знак",
         fields=[Field("text", "Текст", default="ЧЕРНОВИК", required=True),
                 Field("opacity", "Прозрачность", "choice", "0.25",
                       [("0.15", "Едва заметно"), ("0.25", "Обычно"), ("0.45", "Заметно")])]),
    Tool("pdf_meta", "Метаданные", "Название, автор, тема", "pdf", "СОДЕРЖИМОЕ", "info",
         pdf.set_metadata, ["pdf"], verb="Изменить метаданные",
         fields=[Field("title", "Название"), Field("author", "Автор"), Field("subject", "Тема"),
                 Field("keywords", "Ключевые слова")]),
    Tool("pdf_text", "Извлечь текст", "Весь текст в TXT", "pdf", "СОДЕРЖИМОЕ", "type",
         pdf.extract_text, ["pdf"], verb="Извлечь текст"),
    Tool("pdf_images", "Извлечь картинки", "Встроенные изображения в папку", "pdf", "СОДЕРЖИМОЕ", "images",
         pdf.extract_images, ["pdf"], verb="Извлечь картинки"),

    Tool("img_resize", "Изменить размер", "В процентах или по ширине", "images", "ПРЕОБРАЗОВАНИЕ", "scaling",
         images.resize, IMAGE_EXTS, "pillow", verb="Изменить размер",
         fields=[Field("mode", "Способ", "choice", "percent", [("percent", "В процентах"), ("width", "Ширина в пикселях")]),
                 Field("value", "Значение", default="50", required=True)]),
    Tool("img_crop", "Обрезать", "Срезать поля в пикселях", "images", "ПРЕОБРАЗОВАНИЕ", "crop",
         images.crop, IMAGE_EXTS, "pillow", verb="Обрезать",
         fields=[Field("left", "Слева", default="0"), Field("top", "Сверху", default="0"),
                 Field("right", "Справа", default="0"), Field("bottom", "Снизу", default="0")]),
    Tool("img_rotate", "Повернуть", "На 90, 180 или 270 градусов", "images", "ПРЕОБРАЗОВАНИЕ", "rotate-cw",
         images.rotate, IMAGE_EXTS, "pillow", fields=[ANGLE], verb="Повернуть"),
    Tool("img_compress", "Сжать", "JPG или WEBP меньшего размера", "images", "ОПТИМИЗАЦИЯ", "shrink",
         images.compress, IMAGE_EXTS, "pillow", fields=[LEVEL], verb="Сжать"),
    Tool("img_exif", "Удалить EXIF", "Убрать метаданные и геометки", "images", "ОПТИМИЗАЦИЯ", "eraser",
         images.strip_exif, IMAGE_EXTS, "pillow", verb="Удалить EXIF"),
    Tool("img_watermark", "Водяной знак", "Текст в углу картинки", "images", "ОФОРМЛЕНИЕ", "stamp",
         images.watermark, IMAGE_EXTS, "pillow", verb="Добавить водяной знак",
         fields=[Field("text", "Текст", required=True)]),
    Tool("img_to_pdf", "Собрать в PDF", "Несколько картинок в один PDF", "images", "ОФОРМЛЕНИЕ", "file-text",
         _images_to_pdf, IMAGE_EXTS, "pymupdf", verb="Собрать PDF"),

    Tool("media_trim", "Обрезать по времени", "Вырезать фрагмент", "media", "РЕДАКТИРОВАНИЕ", "scissors",
         ffmpeg.trim, MEDIA_EXTS, "ffmpeg", verb="Обрезать",
         fields=[Field("start", "Начало", default="0:00", hint="Формат: минуты:секунды"),
                 Field("end", "Конец", hint="Пусто: до конца файла")]),
    Tool("media_concat", "Склеить", "Несколько файлов подряд", "media", "РЕДАКТИРОВАНИЕ", "combine",
         ffmpeg.concat, MEDIA_EXTS, "ffmpeg", min_files=2, verb="Склеить"),
    Tool("media_volume", "Громкость", "Тише или громче", "media", "РЕДАКТИРОВАНИЕ", "volume-2",
         ffmpeg.volume, MEDIA_EXTS, "ffmpeg", verb="Изменить громкость",
         fields=[Field("factor", "Множитель", "choice", "1.5",
                       [("0.5", "Тише в 2 раза"), ("0.75", "Немного тише"), ("1.5", "Громче в 1.5 раза"),
                        ("2", "Громче в 2 раза")])]),
    Tool("media_compress", "Сжать видео", "Пресеты качества, результат MP4", "media", "ОПТИМИЗАЦИЯ", "shrink",
         ffmpeg.compress_video, ffmpeg.VIDEO, "ffmpeg", verb="Сжать видео",
         fields=[Field("level", "Пресет", "choice", "medium",
                       [("low", "Высокое качество"), ("medium", "Баланс, до 1080p"), ("high", "Маленький файл, до 720p")])]),
    Tool("media_audio", "Извлечь звук", "Звуковая дорожка из видео", "media", "ОПТИМИЗАЦИЯ", "audio-lines",
         _extract_audio, ffmpeg.VIDEO, "ffmpeg", verb="Извлечь звук",
         fields=[Field("format", "Формат", "choice", "mp3", [("mp3", "MP3"), ("m4a", "M4A"), ("wav", "WAV")])]),

    Tool("ocr_txt", "Распознать в TXT", "Текст с картинки или скана", "ocr", "РАСПОЗНАВАНИЕ ТЕКСТА", "scan-text",
         _ocr_each("txt"), ocr.IMAGE_EXTS + ["pdf"], "tesseract", verb="Распознать в TXT"),
    Tool("ocr_docx", "Распознать в DOCX", "Текст в документ Word", "ocr", "РАСПОЗНАВАНИЕ ТЕКСТА", "file-text",
         _ocr_each("docx"), ocr.IMAGE_EXTS + ["pdf"], "tesseract", verb="Распознать в DOCX"),
    Tool("ocr_pdf", "PDF с поиском", "Скан с невидимым текстовым слоем", "ocr", "РАСПОЗНАВАНИЕ ТЕКСТА", "file-search",
         _ocr_each("pdf"), ocr.IMAGE_EXTS + ["pdf"], "tesseract", verb="Сделать PDF с поиском"),
]

TOOLS_BY_ID = {t.id: t for t in TOOLS}

SECTION_TITLES = {"pdf": "Инструменты PDF", "images": "Изображения", "media": "Аудио и видео", "ocr": "Распознавание"}

# быстрые действия на экране файла: категория источника -> id инструментов
QUICK = {
    "pdf": ["ocr_pdf", "pdf_compress", "pdf_merge", "pdf_split", "pdf_rotate"],
    "images": ["img_resize", "img_compress", "img_rotate", "img_crop", "ocr_txt"],
    "audio": ["media_trim", "media_volume", "media_concat"],
    "video": ["media_audio", "media_compress", "media_trim", "media_volume", "media_concat"],
}


def section_tools(section):
    return [t for t in TOOLS if t.section == section]


def section_for_ext(ext):
    from .registry import category
    if ext == "pdf":
        return "pdf"
    cat = category(ext)
    if cat == "images":
        return "images"
    if cat in ("audio", "video"):
        return "media"
    return None
