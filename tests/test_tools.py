import pymupdf
import pytest
from PIL import Image

from fileconverter.engines.base import Context, ConvertError
from fileconverter.naming import Namer
from fileconverter.tools import TOOLS_BY_ID


def run_tool(tool_id, files, out_dir, engines, **params):
    tool = TOOLS_BY_ID[tool_id]
    if not engines.available(tool.engine):
        pytest.skip(f"нет движка {tool.engine}")
    ctx = Context(namer=Namer(str(out_dir)))
    return tool.func(engines, files, ctx, params)


def pages(path, password=None):
    with pymupdf.open(str(path)) as doc:
        if password:
            doc.authenticate(password)
        return doc.page_count


def test_merge_split(data_dir, out_dir, engines):
    pdf = data_dir / "документ.pdf"
    merged = run_tool("pdf_merge", [pdf, pdf], out_dir, engines)[0]
    assert pages(merged) == 4
    parts = run_tool("pdf_split", [merged], out_dir, engines)
    assert len(parts) == 4
    parts = run_tool("pdf_split", [merged], out_dir, engines, ranges="1-2; 3-")
    assert [pages(p) for p in parts] == [2, 2]
    with pytest.raises(ConvertError):
        run_tool("pdf_merge", [pdf], out_dir, engines)


def test_page_tools(data_dir, out_dir, engines):
    pdf = data_dir / "документ.pdf"
    assert pages(run_tool("pdf_extract", [pdf], out_dir, engines, pages="2")[0]) == 1
    assert pages(run_tool("pdf_delete", [pdf], out_dir, engines, pages="1")[0]) == 1
    with pytest.raises(ConvertError):
        run_tool("pdf_delete", [pdf], out_dir, engines, pages="1-2")
    rotated = run_tool("pdf_rotate", [pdf], out_dir, engines, angle="90")[0]
    with pymupdf.open(str(rotated)) as doc:
        assert doc[0].rotation == 90
    reordered = run_tool("pdf_reorder", [pdf], out_dir, engines, order="2,1")[0]
    with pymupdf.open(str(reordered)) as doc:
        assert "Страница 2" in doc[0].get_text()


def test_password(data_dir, out_dir, engines):
    pdf = data_dir / "документ.pdf"
    locked = run_tool("pdf_encrypt", [pdf], out_dir, engines, password="секрет1")[0]
    with pymupdf.open(str(locked)) as doc:
        assert doc.needs_pass
    with pytest.raises(ConvertError):
        run_tool("pdf_decrypt", [locked], out_dir, engines, password="wrong")
    opened = run_tool("pdf_decrypt", [locked], out_dir, engines, password="секрет1")[0]
    with pymupdf.open(str(opened)) as doc:
        assert not doc.needs_pass


def test_content_tools(data_dir, out_dir, engines):
    pdf = data_dir / "документ.pdf"
    wm = run_tool("pdf_watermark", [pdf], out_dir, engines, text="ЧЕРНОВИК", opacity="0.25")[0]
    with pymupdf.open(str(wm)) as doc:
        assert "ЧЕРНОВИК" in doc[0].get_text()
    comp = run_tool("pdf_compress", [pdf], out_dir, engines, level="medium")[0]
    assert comp.stat().st_size > 0
    meta = run_tool("pdf_meta", [pdf], out_dir, engines, title="Отчёт", author="Иван")[0]
    with pymupdf.open(str(meta)) as doc:
        assert doc.metadata["title"] == "Отчёт"
    txt = run_tool("pdf_text", [pdf], out_dir, engines)[0]
    assert "Страница 1" in txt.read_text(encoding="utf-8")
    img_pdf = run_tool("img_to_pdf", [data_dir / "картинка.png", data_dir / "фото.jpg"], out_dir, engines)[0]
    assert pages(img_pdf) == 2
    imgs = run_tool("pdf_images", [img_pdf], out_dir, engines)
    assert len(imgs) >= 1
    with pytest.raises(ConvertError):
        run_tool("pdf_images", [pdf], out_dir, engines)


def test_image_tools(data_dir, out_dir, engines):
    png = data_dir / "картинка.png"
    out = run_tool("img_resize", [png], out_dir, engines, mode="percent", value="50")[0]
    assert Image.open(out).size == (160, 100)
    out = run_tool("img_resize", [png], out_dir, engines, mode="width", value="100")[0]
    assert Image.open(out).size[0] == 100
    out = run_tool("img_crop", [png], out_dir, engines, left="10", top="10", right="10", bottom="10")[0]
    assert Image.open(out).size == (300, 180)
    with pytest.raises(ConvertError):
        run_tool("img_crop", [png], out_dir, engines, left="400")
    out = run_tool("img_rotate", [png], out_dir, engines, angle="90")[0]
    assert Image.open(out).size == (200, 320)
    out = run_tool("img_compress", [data_dir / "фото.jpg"], out_dir, engines, level="high")[0]
    assert out.suffix == ".jpg"
    out = run_tool("img_watermark", [png], out_dir, engines, text="test")[0]
    assert out.exists()
    out = run_tool("img_exif", [data_dir / "фото.jpg"], out_dir, engines)[0]
    assert not Image.open(out).info.get("exif")


def test_media_tools(data_dir, out_dir, engines):
    wav = data_dir / "звук.wav"
    mp4 = data_dir / "видео.mp4"
    if not mp4.exists():
        pytest.skip("нет тестового видео")
    from fileconverter.engines.ffmpeg import probe_duration
    out = run_tool("media_trim", [wav], out_dir, engines, start="0:00.5", end="1.5")[0]
    assert abs(probe_duration(engines, out) - 1.0) < 0.2
    out = run_tool("media_concat", [wav, wav], out_dir, engines)[0]
    assert probe_duration(engines, out) > 3.5
    out = run_tool("media_volume", [wav], out_dir, engines, factor="0.5")[0]
    assert out.exists()
    out = run_tool("media_compress", [mp4], out_dir, engines, level="high")[0]
    assert out.suffix == ".mp4"
    out = run_tool("media_concat", [mp4, mp4], out_dir, engines)[0]
    assert probe_duration(engines, out) > 3.5
    out = run_tool("media_audio", [mp4], out_dir, engines, format="mp3")[0]
    assert out.suffix == ".mp3"
    out = run_tool("media_volume", [mp4], out_dir, engines, factor="2")[0]
    assert out.suffix == ".mp4"


def test_ocr(data_dir, out_dir, engines):
    if not engines.available("tesseract"):
        pytest.skip("Tesseract не найден на этом компьютере")
    out = run_tool("ocr_txt", [data_dir / "картинка.png"], out_dir, engines)[0]
    assert out.exists()


def test_jobs_queue(data_dir, tmp_path, engines):
    from fileconverter.config import Settings
    from fileconverter.jobs import DONE, ERROR, JobQueue
    from fileconverter.registry import registry
    from fileconverter.stats import History, Stats

    settings = Settings(tmp_path / "s.json")
    settings.set("output_dir", str(tmp_path / "out"))
    stats = Stats(tmp_path / "stats.json")
    history = History(tmp_path / "h.json")
    q = JobQueue(engines, settings, stats, history)
    job, fut = q.convert(data_dir / "картинка.png", registry.get("png", "jpg", engines))
    fut.result(timeout=60)
    assert job.status == DONE and job.outputs[0].exists()
    assert stats.count("png", "jpg") == 1
    assert history.items[0]["status"] == DONE
    assert any("Готово" in line for line in job.log)
    job, fut = q.convert(tmp_path / "нет такого.png", registry.get("png", "jpg", engines))
    fut.result(timeout=60)
    assert job.status == ERROR and "не найден" in job.error
    q.shutdown()


def test_cancel_jobs(data_dir, tmp_path, engines):
    import subprocess
    import time
    from fileconverter.config import Settings
    from fileconverter.jobs import CANCEL, JobQueue
    from fileconverter.registry import registry

    if not engines.available("ffmpeg"):
        pytest.skip("нет FFmpeg")
    long = tmp_path / "длинное.mp4"
    subprocess.run([str(engines.path("ffmpeg")), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=duration=60:size=640x360:rate=25", "-c:v", "libx264", "-preset", "ultrafast", str(long)],
                   check=True, creationflags=0x08000000)
    out = tmp_path / "out"
    settings = Settings(tmp_path / "s.json")
    settings.set("output_dir", str(out))
    q = JobQueue(engines, settings, workers=1)
    running, _ = q.convert(long, registry.get("mp4", "webm", engines))
    waiting, _ = q.convert(data_dir / "картинка.png", registry.get("png", "jpg", engines))
    end = time.time() + 30
    while running.status != "run" and time.time() < end:
        time.sleep(0.05)
    time.sleep(1.5)
    q.cancel(waiting)
    q.cancel(running)
    running.result(timeout=30)
    waiting.result(timeout=30)
    assert running.status == CANCEL and waiting.status == CANCEL
    # незаконченный WEBM удалён, JPG не создавался
    assert not out.exists() or list(out.iterdir()) == []
    q.shutdown()
