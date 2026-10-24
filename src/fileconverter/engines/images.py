from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageSequence, UnidentifiedImageError

from ..config import assets_dir
from .base import ConvertError, ensure_output

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:
    HEIF_OK = False

PIL_FORMATS = {
    "png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "webp": "WEBP", "bmp": "BMP",
    "gif": "GIF", "tiff": "TIFF", "tif": "TIFF", "ico": "ICO",
}


def open_error(path, e):
    if Path(path).suffix.lower() in (".heic", ".heif") and not HEIF_OK:
        return ConvertError("Нет поддержки HEIC: не установлена библиотека pillow-heif")
    text = str(e).lower()
    if isinstance(e, UnidentifiedImageError):
        return ConvertError("Это не картинка или её формат не поддерживается.", detail=str(e))
    if "truncated" in text:
        return ConvertError("Картинка повреждена: файл обрезан или скачан не до конца.", detail=str(e))
    return ConvertError("Не удалось открыть картинку, файл повреждён.", detail=str(e))


def open_image(path):
    try:
        img = Image.open(str(path))
        img.load()
    except Exception as e:
        raise open_error(path, e)
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    return img


def flatten(img, color="white"):
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, color)
        bg.paste(img, mask=img.split()[3])
        return bg
    return img.convert("RGB")


def save_image(img, dst, ctx, keep_exif=None):
    dst = Path(dst)
    ext = dst.suffix.lower().lstrip(".")
    fmt = PIL_FORMATS.get(ext)
    if not fmt:
        raise ConvertError(f"Формат {ext.upper()} не поддерживается для сохранения")
    kw = {}
    if fmt == "JPEG":
        img = flatten(img)
        kw = {"quality": ctx.jpeg_quality(), "optimize": True}
    elif fmt == "WEBP":
        kw = {"quality": ctx.jpeg_quality(), "method": 4}
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
    elif fmt == "BMP":
        img = flatten(img) if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")
    elif fmt == "GIF":
        if img.mode not in ("P", "L"):
            img = img.convert("RGBA").convert("P", palette=Image.ADAPTIVE, colors=255)
    elif fmt == "ICO":
        img = img.convert("RGBA")
        side = max(img.size)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(img, ((side - img.width) // 2, (side - img.height) // 2))
        img = square.resize((256, 256), Image.LANCZOS) if side > 256 else square
        sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256) if s <= img.width]
        kw = {"sizes": sizes or [(img.width, img.width)]}
    elif fmt == "TIFF":
        kw = {"compression": "tiff_lzw"}
        if img.mode == "P":
            img = img.convert("RGBA")
    elif fmt == "PNG":
        kw = {"optimize": True}
        if img.mode == "CMYK":
            img = img.convert("RGB")
    if keep_exif and fmt in ("JPEG", "WEBP", "PNG", "TIFF"):
        kw["exif"] = keep_exif
    try:
        img.save(str(dst), fmt, **kw)
    except Exception as e:
        raise ConvertError("Не удалось сохранить картинку в этом формате.", detail=str(e))
    return ensure_output(dst)


def frame_count(path):
    try:
        with Image.open(str(path)) as im:
            return getattr(im, "n_frames", 1)
    except Exception:
        return 1


def save_animation(src, dst, ctx):
    """GIF и WEBP с несколькими кадрами сохраняются целиком, с исходной скоростью."""
    fmt = PIL_FORMATS[Path(dst).suffix.lower().lstrip(".")]
    try:
        with Image.open(str(src)) as im:
            frames, durations = [], []
            for frame in ImageSequence.Iterator(im):
                frames.append(frame.convert("RGBA"))
                durations.append(frame.info.get("duration", im.info.get("duration", 100)) or 100)
            loop = im.info.get("loop", 0)
    except Exception as e:
        raise open_error(src, e)
    kw = {"save_all": True, "append_images": frames[1:], "duration": durations, "loop": loop}
    if fmt == "WEBP":
        kw.update(quality=ctx.jpeg_quality(), method=4)
    else:
        kw["disposal"] = 2
    try:
        frames[0].save(str(dst), fmt, **kw)
    except Exception as e:
        raise ConvertError("Не удалось сохранить анимацию.", detail=str(e))
    ctx.log(f"Анимация сохранена: кадров {len(frames)}")
    return ensure_output(dst)


def convert(engines, src, dst, ctx):
    # многостраничный TIFF тоже даёт несколько кадров, но это не анимация
    frames = frame_count(src) if Path(src).suffix.lower() in (".gif", ".webp", ".png") else 1
    fmt = PIL_FORMATS.get(Path(dst).suffix.lower().lstrip("."))
    if frames > 1 and fmt in ("GIF", "WEBP"):
        save_animation(src, dst, ctx)
        ctx.progress(1.0)
        return [dst]
    if frames > 1:
        ctx.log(f"В файле {frames} кадров анимации, в {fmt} сохранён только первый")
    img = open_image(src)
    ctx.progress(0.4)
    exif = img.info.get("exif")
    save_image(img, dst, ctx, keep_exif=exif)
    ctx.progress(1.0)
    return [dst]


def _each(files, ctx, tag, func, ext=None):
    outputs = []
    for i, src in enumerate(files):
        img = open_image(src)
        img = func(img)
        out_ext = ext or Path(src).suffix.lower().lstrip(".")
        if out_ext in ("heic", "heif"):
            out_ext = "jpg"
        dst = ctx.namer.file(src, out_ext, tag)
        save_image(img, dst, ctx)
        outputs.append(dst)
        ctx.progress((i + 1) / len(files))
    return outputs


def resize(engines, files, ctx, params):
    mode = params.get("mode", "percent")
    value = float(params.get("value") or 50)
    if value <= 0:
        raise ConvertError("Размер должен быть больше нуля")

    def f(img):
        if mode == "percent":
            w, h = int(img.width * value / 100), int(img.height * value / 100)
        else:
            w = int(value)
            h = int(img.height * w / img.width)
        if w < 1 or h < 1 or w > 30000 or h > 30000:
            raise ConvertError("Слишком маленький или слишком большой размер")
        return img.resize((w, h), Image.LANCZOS)

    return _each(files, ctx, "размер", f)


def crop(engines, files, ctx, params):
    left, top, right, bottom = (int(params.get(k) or 0) for k in ("left", "top", "right", "bottom"))

    def f(img):
        box = (left, top, img.width - right, img.height - bottom)
        if box[0] < 0 or box[1] < 0 or box[2] <= box[0] or box[3] <= box[1]:
            raise ConvertError("Обрезка больше, чем сама картинка")
        return img.crop(box)

    return _each(files, ctx, "обрезка", f)


def rotate(engines, files, ctx, params):
    angle = int(params.get("angle", 90))
    return _each(files, ctx, "поворот", lambda img: img.rotate(-angle, expand=True))


def compress(engines, files, ctx, params):
    level = params.get("level", "medium")
    quality = {"low": 85, "medium": 70, "high": 50}.get(level, 70)
    outputs = []
    for i, src in enumerate(files):
        img = open_image(src)
        ext = Path(src).suffix.lower().lstrip(".")
        if ext not in ("jpg", "jpeg", "webp"):
            ext = "jpg"
        dst = ctx.namer.file(src, ext, "сжатый")
        if ext == "webp":
            img.save(str(dst), "WEBP", quality=quality, method=6)
        else:
            flatten(img).save(str(dst), "JPEG", quality=quality, optimize=True, progressive=True)
        ctx.log(f"{Path(src).name}: {Path(src).stat().st_size // 1024} КБ -> {dst.stat().st_size // 1024} КБ")
        outputs.append(ensure_output(dst))
        ctx.progress((i + 1) / len(files))
    return outputs


def watermark(engines, files, ctx, params):
    text = (params.get("text") or "").strip()
    if not text:
        raise ConvertError("Текст водяного знака не указан")
    opacity = int(255 * float(params.get("opacity", 0.35)))

    def f(img):
        base = img.convert("RGBA")
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        size = max(14, int(min(base.size) / 12))
        try:
            font = ImageFont.truetype(str(assets_dir() / "fonts" / "IBMPlexMono-SemiBold.ttf"), size)
        except OSError:
            font = ImageFont.load_default()
        draw = ImageDraw.Draw(layer)
        box = draw.textbbox((0, 0), text, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        x, y = base.width - tw - size, base.height - th - size
        draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, opacity // 2))
        draw.text((x, y), text, font=font, fill=(255, 255, 255, opacity))
        return Image.alpha_composite(base, layer)

    return _each(files, ctx, "водяной знак", f)


def strip_exif(engines, files, ctx, params):
    def f(img):
        clean = Image.frombytes(img.mode, img.size, img.tobytes())
        if img.mode == "P":
            clean.putpalette(img.getpalette())
        return clean

    return _each(files, ctx, "без exif", f)


def image_info(path):
    try:
        with Image.open(str(path)) as img:
            return {"width": img.width, "height": img.height}
    except Exception:
        return {}
