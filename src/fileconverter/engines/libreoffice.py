import shutil
import threading
from pathlib import Path

from ..config import data_dir
from .base import ConvertError, ensure_output, last_lines, run

# один экземпляр soffice за раз, иначе общий профиль блокируется
_lock = threading.Lock()

WRITER = {"doc", "docx", "odt", "rtf", "txt", "html"}
CALC = {"xls", "xlsx", "ods", "csv"}
IMPRESS = {"ppt", "pptx", "odp"}

FILTERS = {
    ("writer", "txt"): "txt:Text (encoded):UTF8",
    ("writer", "html"): "html:XHTML Writer File:UTF8",
    ("writer", "docx"): "docx:MS Word 2007 XML",
    ("writer", "doc"): "doc:MS Word 97",
    ("writer", "rtf"): "rtf:Rich Text Format",
    ("writer", "odt"): "odt:writer8",
    ("writer", "pdf"): "pdf:writer_pdf_Export",
    # точка с запятой и UTF-8: так CSV ждёт русский Excel, BOM дописывается после конвертации
    ("calc", "csv"): "csv:Text - txt - csv (StarCalc):59,34,76,1",
    ("calc", "html"): "html:HTML (StarCalc)",
    ("calc", "xlsx"): "xlsx:Calc MS Excel 2007 XML",
    ("calc", "ods"): "ods:calc8",
    ("calc", "pdf"): "pdf:calc_pdf_Export",
    ("impress", "pdf"): "pdf:impress_pdf_Export",
    ("impress", "pptx"): "pptx:Impress MS PowerPoint 2007 XML",
    ("impress", "odp"): "odp:impress8",
}


def family(ext):
    if ext in CALC:
        return "calc"
    if ext in IMPRESS:
        return "impress"
    return "writer"


def profile_url():
    path = data_dir() / "lo_profile"
    path.mkdir(parents=True, exist_ok=True)
    return path.as_uri()


def read_text_any(path):
    """Текст файла в UTF-8 или cp1251 (так сохраняют старые программы и русский Excel)."""
    data = Path(path).read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1251", errors="replace")


def detect_separator(text):
    lines = [l for l in text.splitlines()[:20] if l.strip()]
    if not lines:
        return ","
    best, best_score = ",", -1
    for sep in (";", ",", "\t"):
        counts = [l.count(sep) for l in lines]
        # разделитель встречается в каждой строке одинаковое число раз
        score = min(counts) if len(set(counts)) == 1 else min(counts) - 1
        if score > best_score:
            best, best_score = sep, score
    return best


def build_command(soffice, src, dst_ext, outdir, profile=None, separator=","):
    src = Path(src)
    fam = family(src.suffix.lower().lstrip("."))
    target = FILTERS.get((fam, dst_ext), dst_ext)
    cmd = [str(soffice), "--headless", "--norestore", "--nologo", "--nodefault", "--nolockcheck",
           f"-env:UserInstallation={profile or profile_url()}"]
    if src.suffix.lower() == ".csv":
        options = f"{ord(separator)},34,76,1"
        if separator == ";":
            # с точкой с запятой обычно русский формат чисел: 250,5
            options += ",,1049"
        cmd.append(f"--infilter=Text - txt - csv (StarCalc):{options}")
    elif src.suffix.lower() == ".txt":
        cmd.append("--infilter=Text (encoded):UTF8")
    elif src.suffix.lower() in (".html", ".htm"):
        cmd.append("--infilter=HTML (StarWriter)")
    cmd += ["--convert-to", target, "--outdir", str(outdir), str(src)]
    return cmd


def convert(engines, src, dst, ctx):
    soffice = engines.path("libreoffice")
    if not soffice:
        raise ConvertError("LibreOffice не найден. Установите его или укажите путь в настройках.")
    src, dst = Path(src), Path(dst)
    dst_ext = dst.suffix.lower().lstrip(".")
    with ctx.tempdir() as tmp:
        tmp = Path(tmp)
        # копия с простым именем: soffice плохо переносит некоторые символы в путях
        work = tmp / ("input" + src.suffix.lower())
        separator = ","
        if src.suffix.lower() == ".csv":
            # LibreOffice получает CSV всегда в UTF-8, разделитель определяем сами
            text = read_text_any(src)
            separator = detect_separator(text)
            work.write_text(text, encoding="utf-8", newline="")
        else:
            shutil.copy2(src, work)
        outdir = tmp / "out"
        outdir.mkdir()
        cmd = build_command(soffice, work, dst_ext, outdir, separator=separator)
        ctx.log(f"LibreOffice: {src.suffix.lstrip('.').upper()} в {dst_ext.upper()}")
        ctx.progress(0.1)
        with _lock:
            code, out = run(cmd, timeout=600)
        produced = list(outdir.glob("input.*"))
        if code != 0 or not produced:
            raise ConvertError("LibreOffice не смог конвертировать файл. " + last_lines(out))
        result = ensure_output(produced[0])
        if dst_ext == "csv":
            data = result.read_bytes()
            if not data.startswith(b"\xef\xbb\xbf"):
                result.write_bytes(b"\xef\xbb\xbf" + data)
        shutil.move(str(result), str(dst))
    ctx.progress(1.0)
    return [dst]
