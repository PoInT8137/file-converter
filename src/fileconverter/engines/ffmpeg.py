import re
from pathlib import Path

from .base import ConvertError, ensure_output, last_lines, run

AUDIO = ["mp3", "wav", "flac", "ogg", "m4a", "aac", "opus"]
VIDEO = ["mp4", "mkv", "avi", "mov", "webm"]

AUDIO_ARGS = {
    "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    "wav": ["-c:a", "pcm_s16le"],
    "flac": ["-c:a", "flac"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "5"],
    "m4a": ["-c:a", "aac", "-b:a", "192k"],
    "aac": ["-c:a", "aac", "-b:a", "192k", "-f", "adts"],
    "opus": ["-c:a", "libopus", "-b:a", "128k"],
}

VIDEO_ARGS = {
    "mp4": ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"],
    "mkv": ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k"],
    "mov": ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k"],
    "avi": ["-c:v", "mpeg4", "-q:v", "4", "-c:a", "libmp3lame", "-q:a", "3"],
    # без yuv420p VP9 не принимает картинку с прозрачностью из GIF (формат gbrap) и падает
    "webm": ["-c:v", "libvpx-vp9", "-crf", "33", "-b:v", "0", "-pix_fmt", "yuv420p", "-row-mt", "1",
             "-deadline", "good", "-cpu-used", "4", "-c:a", "libopus", "-b:a", "128k"],
}

# GIF из длинного видео выходит огромным (10 минут дают около 100 МБ), поэтому берётся начало
GIF_MAX_SECONDS = 60

# типовые ответы FFmpeg и что они значат для пользователя
FFMPEG_ERRORS = [
    ("Invalid data found when processing input", "Файл повреждён или это не аудио и не видео."),
    ("does not contain any stream", "В файле нет подходящей дорожки: например, в видео нет звука."),
    ("matches no streams", "В файле нет подходящей дорожки: например, в видео нет звука."),
    ("No space left on device", "На диске не хватает места."),
    ("Permission denied", "Нет доступа к файлу. Возможно, он открыт в другой программе."),
    ("No such file or directory", "Файл не найден."),
]


def explain(errors_text):
    for marker, text in FFMPEG_ERRORS:
        if marker in errors_text:
            return text
    return "FFmpeg не смог обработать файл. Возможно, он повреждён или формат не поддерживается."


def tool(engines):
    path = engines.path("ffmpeg")
    if not path:
        raise ConvertError("FFmpeg не найден. Положите ffmpeg.exe в папку engines рядом с программой.")
    return path


def probe_duration(engines, src):
    """Длительность в секундах или 0, если узнать не удалось."""
    probe = engines.path("ffprobe")
    try:
        if probe:
            code, out = run([probe, "-v", "error", "-show_entries", "format=duration",
                             "-of", "default=nw=1:nk=1", str(src)], timeout=30)
            if code == 0:
                return float(out.strip().splitlines()[0])
        ff = engines.path("ffmpeg")
        if ff:
            _, out = run([ff, "-hide_banner", "-i", str(src)], timeout=30)
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
            if m:
                return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except (ConvertError, ValueError, IndexError):
        pass
    return 0.0


def has_video(engines, src):
    probe = engines.path("ffprobe")
    if not probe:
        return Path(src).suffix.lower().lstrip(".") in VIDEO
    try:
        _, out = run([probe, "-v", "error", "-select_streams", "v", "-show_entries", "stream=codec_type",
                      "-of", "csv=p=0", str(src)], timeout=30)
        return "video" in out
    except ConvertError:
        return False


def execute(engines, args, ctx, duration=0.0, out=None):
    cmd = [tool(engines), "-hide_banner", "-y", "-nostdin", "-progress", "pipe:1", "-nostats"] + args
    errors = []

    def on_line(line):
        if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
            try:
                us = int(line.split("=", 1)[1])
            except ValueError:
                return
            if duration > 0:
                ctx.progress(us / 1_000_000 / duration)
        elif not re.match(r"^\w+=", line):
            errors.append(line)

    code, output = run(cmd, timeout=None, on_line=on_line)
    if code != 0:
        text = "\n".join(errors) or output
        raise ConvertError(explain(text), detail=last_lines(text, 6))
    if out:
        ensure_output(out)
    ctx.progress(1.0)


def convert(engines, src, dst, ctx):
    dst = Path(dst)
    ext = dst.suffix.lower().lstrip(".")
    duration = probe_duration(engines, src)
    ctx.log(f"FFmpeg: длительность {format_time(duration)}" if duration else "FFmpeg: обработка")
    if ext in AUDIO:
        args = ["-i", str(src), "-vn"] + AUDIO_ARGS[ext] + [str(dst)]
    elif ext in VIDEO:
        args = ["-i", str(src)] + VIDEO_ARGS[ext] + [str(dst)]
    elif ext == "gif":
        vf = "fps=12,scale='min(640,iw)':-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=192[p];[b][p]paletteuse=dither=bayer"
        args = ["-i", str(src), "-vf", vf, "-loop", "0"]
        if duration > GIF_MAX_SECONDS:
            ctx.log(f"Видео длиннее {GIF_MAX_SECONDS} секунд: в GIF попадёт только начало, иначе файл будет огромным. "
                    "Нужный фрагмент можно вырезать в разделе Аудио и видео")
            args += ["-t", str(GIF_MAX_SECONDS)]
            duration = GIF_MAX_SECONDS
        args.append(str(dst))
    else:
        raise ConvertError(f"FFmpeg не умеет сохранять в {ext.upper()}")
    execute(engines, args, ctx, duration, dst)
    return [dst]


def format_time(seconds):
    seconds = int(round(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_time(text):
    """Принимает 90, 1:30 или 0:01:30 и возвращает секунды."""
    text = (text or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        parts = [float(p) for p in text.split(":")]
    except ValueError:
        raise ConvertError(f"Непонятное время: {text}. Пример: 1:30")
    if len(parts) > 3 or any(p < 0 for p in parts):
        raise ConvertError(f"Непонятное время: {text}. Пример: 1:30")
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def codec_args(ext):
    if ext in AUDIO:
        return AUDIO_ARGS[ext]
    return VIDEO_ARGS.get(ext, VIDEO_ARGS["mp4"])


def trim(engines, files, ctx, params):
    start = parse_time(params.get("start")) or 0.0
    end = parse_time(params.get("end"))
    outputs = []
    for src in files:
        duration = probe_duration(engines, src)
        if end is not None and end <= start:
            raise ConvertError("Конец фрагмента должен быть позже начала")
        if duration and start >= duration:
            raise ConvertError("Начало фрагмента позже конца файла")
        ext = Path(src).suffix.lower().lstrip(".")
        dst = ctx.namer.file(src, ext, "фрагмент")
        args = ["-ss", str(start), "-i", str(src)]
        if end is not None:
            args += ["-t", str(end - start)]
        args += codec_args(ext) + [str(dst)]
        length = (end or duration) - start
        execute(engines, args, ctx, length, dst)
        outputs.append(dst)
    return outputs


def concat(engines, files, ctx, params):
    if len(files) < 2:
        raise ConvertError("Для склейки выберите хотя бы два файла")
    ext = Path(files[0]).suffix.lower().lstrip(".")
    dst = ctx.namer.file(files[0], ext, "склейка")
    total = sum(probe_duration(engines, f) for f in files)
    video = ext in VIDEO
    args = []
    for f in files:
        args += ["-i", str(f)]
    n = len(files)
    if video:
        # приводим все ролики к размеру первого, иначе concat не склеит
        filters = []
        for i in range(n):
            filters.append(f"[{i}:v]scale=1280:720:force_original_aspect_ratio=decrease,"
                           f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}]")
            filters.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
        joined = "".join(f"[v{i}][a{i}]" for i in range(n))
        filters.append(f"{joined}concat=n={n}:v=1:a=1[v][a]")
        args += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]"]
    else:
        filters = [f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]" for i in range(n)]
        joined = "".join(f"[a{i}]" for i in range(n))
        filters.append(f"{joined}concat=n={n}:v=0:a=1[a]")
        args += ["-filter_complex", ";".join(filters), "-map", "[a]"]
    args += codec_args(ext) + [str(dst)]
    try:
        execute(engines, args, ctx, total, dst)
    except ConvertError as e:
        if video:
            raise ConvertError(str(e) + ". Возможно, в одном из роликов нет звуковой дорожки.")
        raise
    return [dst]


def compress_video(engines, files, ctx, params):
    level = params.get("level", "medium")
    crf = {"low": "26", "medium": "30", "high": "34"}.get(level, "30")
    height = {"low": None, "medium": 1080, "high": 720}.get(level)
    outputs = []
    for src in files:
        dst = ctx.namer.file(src, "mp4", "сжатый")
        args = ["-i", str(src), "-c:v", "libx264", "-preset", "medium", "-crf", crf, "-pix_fmt", "yuv420p"]
        if height:
            args += ["-vf", f"scale=-2:'min({height},ih)'"]
        args += ["-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(dst)]
        execute(engines, args, ctx, probe_duration(engines, src), dst)
        ctx.log(f"{Path(src).name}: {Path(src).stat().st_size // 1024} КБ -> {dst.stat().st_size // 1024} КБ")
        outputs.append(dst)
    return outputs


def volume(engines, files, ctx, params):
    try:
        factor = float(str(params.get("factor", "1.5")).replace(",", "."))
    except ValueError:
        raise ConvertError("Громкость указывается числом, например 1.5")
    if factor <= 0 or factor > 10:
        raise ConvertError("Множитель громкости должен быть от 0.1 до 10")
    outputs = []
    for src in files:
        ext = Path(src).suffix.lower().lstrip(".")
        dst = ctx.namer.file(src, ext, "громкость")
        args = ["-i", str(src), "-af", f"volume={factor}"]
        codec = codec_args(ext)
        if ext in VIDEO:
            args += ["-c:v", "copy"] + codec[codec.index("-c:a"):]
        else:
            args += codec
        args.append(str(dst))
        execute(engines, args, ctx, probe_duration(engines, src), dst)
        outputs.append(dst)
    return outputs
