"""Повреждённые, пустые и анимированные файлы, тексты ошибок и сбои установщика."""
import re
import sys
from pathlib import Path

import pytest
from PIL import Image

from fileconverter.engines.base import Context, ConvertError
from fileconverter.naming import Namer
from fileconverter.registry import registry

ROOT = Path(__file__).resolve().parents[1]


def run(engines, src, dst, out_dir):
    ctx = Context(namer=Namer(str(out_dir)))
    conv = registry.get(src.suffix, dst, engines)
    if conv is None:
        pytest.skip(f"нет движка для {src.suffix} в {dst}")
    return conv.run(engines, src, ctx.namer.file(src, dst), ctx)


@pytest.fixture
def animated(tmp_path):
    frames = [Image.new("RGB", (120, 80), c) for c in ("red", "green", "blue")]
    gif = tmp_path / "анимация.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=200, loop=0)
    webp = tmp_path / "анимация.webp"
    frames[0].save(webp, save_all=True, append_images=frames[1:], duration=200, loop=0)
    return gif, webp


def frames(path):
    with Image.open(path) as im:
        return getattr(im, "n_frames", 1)


def test_animation_kept_between_gif_and_webp(engines, animated, tmp_path):
    gif, webp = animated
    assert frames(run(engines, gif, "webp", tmp_path / "o")[0]) == 3
    assert frames(run(engines, webp, "gif", tmp_path / "o")[0]) == 3


def test_animation_to_static_takes_first_frame(engines, animated, tmp_path):
    out = run(engines, animated[0], "png", tmp_path / "o")[0]
    assert Image.open(out).convert("RGB").getpixel((5, 5)) == (255, 0, 0)


def test_gif_to_webm(engines, animated, tmp_path):
    if not engines.available("ffmpeg"):
        pytest.skip("нет FFmpeg")
    out = run(engines, animated[0], "webm", tmp_path / "o")[0]
    assert out.read_bytes()[:4] == b"\x1a\x45\xdf\xa3"


RAW_ENGINE_TEXT = re.compile(r"[A-Za-z]{4,} [A-Za-z]{4,}|@ 0x|\[in#|[A-Z]:\\")


@pytest.mark.parametrize("name,dst", [("картинка.png", "jpg"), ("документ.pdf", "txt"), ("видео.mp4", "mp3"),
                                      ("документ.docx", "pdf"), ("документ.docx", "md")])
def test_corrupted_files_give_russian_errors(engines, data_dir, tmp_path, name, dst):
    src = tmp_path / f"обрезан_{name}"
    data = (data_dir / name).read_bytes()
    src.write_bytes(data[: len(data) // 3] if not name.endswith(".pdf") else b"%PDF-1.4 broken")
    try:
        run(engines, src, dst, tmp_path / "o")
    except ConvertError as e:
        text = str(e)
        assert re.search("[а-яА-Я]", text), text
        assert not RAW_ENGINE_TEXT.search(text), f"в сообщении сырой текст движка: {text}"
        return
    # некоторые движки умеют прочитать обрезанный файл частично, это тоже допустимо


def test_empty_file_is_rejected(engines, tmp_path):
    from fileconverter.config import Settings
    from fileconverter.jobs import ERROR, JobQueue
    empty = tmp_path / "пустой.docx"
    empty.write_bytes(b"")
    settings = Settings(tmp_path / "s.json")
    settings.set("output_dir", str(tmp_path / "out"))
    q = JobQueue(engines, settings, workers=1)
    job, _ = q.convert(empty, registry.get("docx", "txt", engines) or registry.get("docx", "md", engines))
    job.result(timeout=60)
    q.shutdown()
    assert job.status == ERROR
    assert "пустой" in job.error
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").iterdir())


def test_long_video_gif_is_limited(engines, tmp_path):
    import subprocess
    from fileconverter.engines import ffmpeg
    if not engines.available("ffmpeg"):
        pytest.skip("нет FFmpeg")
    src = tmp_path / "длинное.mp4"
    subprocess.run([str(engines.path("ffmpeg")), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=duration=70:size=160x120:rate=5", "-c:v", "libx264", "-preset", "ultrafast", str(src)],
                   check=True, creationflags=0x08000000)
    log = []
    ctx = Context(on_log=log.append, namer=Namer(str(tmp_path / "o")))
    out = registry.get("mp4", "gif", engines).run(engines, src, ctx.namer.file(src, "gif"), ctx)[0]
    assert ffmpeg.probe_duration(engines, out) <= ffmpeg.GIF_MAX_SECONDS + 1
    assert any("только начало" in line for line in log)


def test_installer_unexpected_error_reaches_window(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "installer"))
    import setup_app

    payload = ROOT / "build" / "payload" / "payload.zip"
    if not payload.exists():
        pytest.skip("нет build/payload/payload.zip, сначала build.bat")
    monkeypatch.setattr(setup_app, "base_dir", lambda: payload.parent)

    def broken_shortcuts(*a):
        raise RuntimeError("PowerShell сломан")

    monkeypatch.setattr(setup_app, "make_shortcuts", broken_shortcuts)
    w = setup_app.Wizard("install")
    w.withdraw()
    target = tmp_path / "File Converter"
    try:
        w.install_worker(target, False, False)
        kinds = []
        while not w.events.empty():
            kinds.append(w.events.get_nowait())
        assert kinds[-1][0] == "error"
        assert "неожиданной ошибки" in kinds[-1][1]
        assert setup_app.registered_dir() != target
    finally:
        w.destroy()


def test_installer_shortcut_timeout_is_not_fatal(monkeypatch):
    sys.path.insert(0, str(ROOT / "installer"))
    import subprocess

    import setup_app

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired("powershell", 60)

    monkeypatch.setattr(setup_app.subprocess, "run", timeout)
    assert setup_app.run_powershell("Write-Output 1") is False
