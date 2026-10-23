from pathlib import Path

from .base import ConvertError, ensure_output, last_lines, run

READERS = {"md": "markdown", "html": "html", "docx": "docx", "odt": "odt", "txt": "markdown",
           "epub": "epub", "rtf": "rtf"}
WRITERS = {"md": "markdown", "html": "html", "docx": "docx", "odt": "odt", "txt": "plain",
           "epub": "epub3", "rtf": "rtf"}
FORMATS = list(READERS)


def build_command(pandoc, src, dst):
    src, dst = Path(src), Path(dst)
    src_ext = src.suffix.lower().lstrip(".")
    dst_ext = dst.suffix.lower().lstrip(".")
    if src_ext not in READERS or dst_ext not in WRITERS:
        raise ConvertError(f"Pandoc не поддерживает {src_ext.upper()} в {dst_ext.upper()}")
    cmd = [str(pandoc), "-f", READERS[src_ext], "-t", WRITERS[dst_ext], "-s", "-o", str(dst)]
    if dst_ext in ("html", "epub"):
        cmd += ["--metadata", f"title={src.stem}"]
    if dst_ext == "html":
        cmd.append("--embed-resources")
    cmd.append(str(src))
    return cmd


def convert(engines, src, dst, ctx):
    pandoc = engines.path("pandoc")
    if not pandoc:
        raise ConvertError("Pandoc не найден. Положите pandoc.exe в папку engines рядом с программой.")
    ctx.log(f"Pandoc: {Path(src).suffix.lstrip('.').upper()} в {Path(dst).suffix.lstrip('.').upper()}")
    ctx.progress(0.2)
    code, out = run(build_command(pandoc, src, dst), timeout=300, cwd=str(Path(src).parent))
    if code != 0:
        raise ConvertError("Pandoc не смог конвертировать файл: " + last_lines(out))
    ctx.progress(1.0)
    return [ensure_output(dst)]
