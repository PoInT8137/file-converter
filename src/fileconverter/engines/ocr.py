import os
from pathlib import Path

from .base import ConvertError, ensure_output, last_lines, run

IMAGE_EXTS = ["png", "jpg", "jpeg", "tiff", "tif", "bmp", "webp", "gif", "heic"]


def languages(engines):
    have = set(engines.tess_langs)
    wanted = [l for l in ("rus", "eng") if l in have]
    if not wanted:
        wanted = ["eng"] if not have else [sorted(have)[0]]
    return "+".join(wanted)


def tess_env(tesseract):
    env = dict(os.environ)
    tessdata = Path(tesseract).parent / "tessdata"
    if tessdata.is_dir() and "TESSDATA_PREFIX" not in env:
        env["TESSDATA_PREFIX"] = str(tessdata)
    return env


def build_command(tesseract, image, outbase, langs, kind):
    cmd = [str(tesseract), str(image), str(outbase), "-l", langs, "--psm", "3"]
    if kind == "pdf":
        cmd.append("pdf")
    return cmd


def recognize(engines, image, outbase, kind, ctx):
    tesseract = engines.path("tesseract")
    if not tesseract:
        raise ConvertError("Tesseract не найден. Установите Tesseract OCR с языками rus и eng.")
    cmd = build_command(tesseract, image, outbase, languages(engines), kind)
    code, out = run(cmd, timeout=600, env=tess_env(tesseract))
    result = Path(f"{outbase}.{'pdf' if kind == 'pdf' else 'txt'}")
    if code != 0 or not result.exists():
        raise ConvertError("Tesseract не смог распознать текст: " + last_lines(out))
    return result


def page_images(src, tmp, ctx):
    """Готовит картинки для распознавания: страницы PDF рендерятся в 300 dpi."""
    src = Path(src)
    ext = src.suffix.lower().lstrip(".")
    if ext == "pdf":
        from .pdf import open_pdf
        doc = open_pdf(src)
        images = []
        with doc:
            for i, page in enumerate(doc):
                target = Path(tmp) / f"page{i:04d}.png"
                page.get_pixmap(dpi=300, alpha=False).save(str(target))
                images.append(target)
        return images
    from .images import flatten, open_image
    img = flatten(open_image(src))
    target = Path(tmp) / "image.png"
    img.save(target)
    return [target]


def ocr_text(engines, src, ctx):
    texts = []
    with ctx.tempdir() as tmp:
        images = page_images(src, tmp, ctx)
        for i, img in enumerate(images):
            ctx.log(f"Распознавание страницы {i + 1} из {len(images)}")
            out = recognize(engines, img, Path(tmp) / f"out{i}", "txt", ctx)
            texts.append(out.read_text(encoding="utf-8", errors="replace"))
            ctx.progress((i + 1) / len(images) * 0.95)
    return texts


def to_txt(engines, src, dst, ctx):
    texts = ocr_text(engines, src, ctx)
    Path(dst).write_text("\n\n".join(t.strip() for t in texts), encoding="utf-8")
    ctx.progress(1.0)
    return [ensure_output(dst)]


def to_docx(engines, src, dst, ctx):
    from docx import Document

    texts = ocr_text(engines, src, ctx)
    document = Document()
    for i, text in enumerate(texts):
        if i:
            document.add_page_break()
        for para in text.split("\n\n"):
            para = " ".join(para.split())
            if para:
                document.add_paragraph(para)
    document.save(str(dst))
    ctx.progress(1.0)
    return [ensure_output(dst)]


def to_pdf(engines, src, dst, ctx):
    import pymupdf

    out = pymupdf.open()
    with ctx.tempdir() as tmp:
        images = page_images(src, tmp, ctx)
        for i, img in enumerate(images):
            ctx.log(f"Распознавание страницы {i + 1} из {len(images)}")
            part = recognize(engines, img, Path(tmp) / f"out{i}", "pdf", ctx)
            with pymupdf.open(str(part)) as doc:
                out.insert_pdf(doc)
            ctx.progress((i + 1) / len(images) * 0.95)
        out.save(str(dst), garbage=3, deflate=True)
    out.close()
    ctx.progress(1.0)
    return [ensure_output(dst)]
