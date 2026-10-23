from pathlib import Path

import pytest

from fileconverter.engines import libreoffice, ocr, pandoc
from fileconverter.engines.base import ConvertError
from fileconverter.engines.ffmpeg import parse_time
from fileconverter.engines.pdf import parse_pages
from fileconverter.naming import Namer, apply_template, release, unique_path
from fileconverter.registry import Registry, norm, registry
from fileconverter.stats import DEFAULT_PAIRS, Stats


class FakeEngines:
    def __init__(self, missing=()):
        self.missing = set(missing)

    def available(self, name):
        return name not in self.missing

    def path(self, name):
        return None if name in self.missing else Path(f"C:/fake/{name}.exe")


def test_norm():
    assert norm(".JPEG") == "jpg"
    assert norm("tif") == "tiff"
    assert norm(".heif") == "heic"


def test_targets_for_pdf():
    dsts = [c.dst for c in registry.targets("pdf", FakeEngines())]
    for d in ("docx", "txt", "html", "png", "jpg", "pptx", "xlsx"):
        assert d in dsts
    assert "pdf" not in dsts


def test_chain_pptx_to_png():
    conv = registry.get("pptx", "png", FakeEngines())
    assert conv is not None
    assert [s.dst for s in conv.steps] == ["pdf", "png"]
    assert conv.engine_label == "LibreOffice + PyMuPDF"


def test_no_libreoffice_hides_doc_targets():
    eng = FakeEngines(missing={"libreoffice"})
    dsts = [c.dst for c in registry.targets("docx", eng)]
    assert "pdf" not in dsts
    # pandoc остаётся
    assert "md" in dsts and "html" in dsts
    assert registry.get("pptx", "png", eng) is None


def test_fallback_engine_order():
    r = Registry()
    r.add(["a"], ["b"], "first", None)
    r.add(["a"], ["b"], "second", None)
    assert r.get("a", "b", FakeEngines()).engine == "first"
    assert r.get("a", "b", FakeEngines(missing={"first"})).engine == "second"


def test_unknown_source():
    assert registry.targets("xyz", FakeEngines()) == []
    assert not registry.accepts("xyz")
    assert registry.accepts("heic")


def test_unique_path(tmp_path):
    src = tmp_path / "отчёт.docx"
    src.write_text("x")
    (tmp_path / "отчёт.pdf").write_text("x")
    (tmp_path / "отчёт (1).pdf").write_text("x")
    namer = Namer()
    p = namer.file(src, "pdf")
    assert p.name == "отчёт (2).pdf"
    p2 = namer.file(src, "pdf")
    assert p2.name == "отчёт (3).pdf"
    release(p)
    release(p2)


def test_never_overwrites_source(tmp_path):
    src = tmp_path / "фото.jpg"
    src.write_text("x")
    p = Namer().file(src, "jpg")
    assert p != src
    assert p.name == "фото (1).jpg"
    release(p)


def test_output_dir_and_template(tmp_path):
    src = tmp_path / "a" / "файл.txt"
    src.parent.mkdir()
    src.write_text("x")
    out = tmp_path / "out"
    p = Namer(str(out), "{name}_conv").file(src, "pdf")
    assert p.parent == out and p.name == "файл_conv.pdf"
    release(p)
    assert apply_template("{bad", src) == "файл"
    assert apply_template('{name}:?', src) == "файл__"


def test_unique_dir(tmp_path):
    (tmp_path / "x").mkdir()
    assert unique_path(tmp_path / "x", is_dir=True).name == "x (1)"


def test_stats_defaults(tmp_path):
    s = Stats(tmp_path / "stats.json")
    assert s.top_pairs() == DEFAULT_PAIRS


def test_stats_order_and_pin(tmp_path):
    s = Stats(tmp_path / "stats.json")
    for _ in range(3):
        s.add("png", "webp")
    s.add("mp3", "wav")
    top = s.top_pairs()
    assert top[0] == ("png", "webp")
    assert top[1] == ("mp3", "wav")
    assert len(top) == 8
    s.toggle_pin("doc", "odt")
    assert s.top_pairs()[0] == ("doc", "odt")
    s2 = Stats(tmp_path / "stats.json")
    assert s2.count("png", "webp") == 3
    assert s2.is_pinned("doc", "odt")
    s2.toggle_pin("doc", "odt")
    assert not s2.is_pinned("doc", "odt")
    assert s2.best_target("png", ["jpg", "webp"]) == "webp"
    s2.reset()
    assert s2.top_pairs() == DEFAULT_PAIRS


def test_stats_recent(tmp_path):
    s = Stats(tmp_path / "stats.json")
    for i in range(5):
        s.add("png", "jpg", tmp_path / f"{i}.jpg")
    assert [Path(r["path"]).name for r in s.recent_items()] == ["4.jpg", "3.jpg", "2.jpg"]


def test_parse_pages():
    assert parse_pages("1-3, 5", 10) == [0, 1, 2, 4]
    assert parse_pages("8-", 10) == [7, 8, 9]
    with pytest.raises(ConvertError):
        parse_pages("0-2", 5)
    with pytest.raises(ConvertError):
        parse_pages("abc", 5)


def test_parse_time():
    assert parse_time("90") == 90
    assert parse_time("1:30") == 90
    assert parse_time("0:01:30.5") == 90.5
    assert parse_time("") is None
    with pytest.raises(ConvertError):
        parse_time("x")


def test_libreoffice_command(tmp_path):
    cmd = libreoffice.build_command(Path("C:/Program Files/LibreOffice/program/soffice.exe"),
                                    tmp_path / "мой файл.csv", "xlsx", tmp_path / "out", "file:///p")
    assert cmd[0].endswith("soffice.exe")
    assert "--headless" in cmd and "-env:UserInstallation=file:///p" in cmd
    assert cmd[cmd.index("--convert-to") + 1] == "xlsx:Calc MS Excel 2007 XML"
    assert any(c.startswith("--infilter=") for c in cmd)
    assert cmd[-1].endswith("мой файл.csv")
    cmd = libreoffice.build_command("soffice.exe", tmp_path / "a.docx", "txt", tmp_path)
    assert cmd[cmd.index("--convert-to") + 1] == "txt:Text (encoded):UTF8"


def test_ocr_command():
    cmd = ocr.build_command("C:/Tesseract-OCR/tesseract.exe", "C:/скан 1.png", "C:/out", "rus+eng", "pdf")
    assert cmd[1:5] == ["C:/скан 1.png", "C:/out", "-l", "rus+eng"]
    assert cmd[-1] == "pdf"
    assert ocr.build_command("t.exe", "a.png", "o", "eng", "txt")[-1] != "pdf"


def test_ocr_languages():
    class E:
        tess_langs = ["eng", "osd", "rus"]
    assert ocr.languages(E()) == "rus+eng"
    E.tess_langs = ["eng"]
    assert ocr.languages(E()) == "eng"


def test_pandoc_command():
    cmd = pandoc.build_command("pandoc.exe", Path("C:/a b/текст.md"), Path("C:/a b/текст.html"))
    assert cmd[cmd.index("-f") + 1] == "markdown"
    assert cmd[cmd.index("-t") + 1] == "html"
    assert "-s" in cmd
    with pytest.raises(ConvertError):
        pandoc.build_command("pandoc.exe", Path("a.pdf"), Path("a.md"))


def test_finder_candidates(monkeypatch, tmp_path):
    from fileconverter.engines import finder
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "PF"))
    paths = [str(p) for p in finder.candidate_paths("libreoffice", str(tmp_path / "custom"))]
    assert any(p.endswith(r"LibreOffice\program\soffice.exe") for p in paths)
    assert paths[-1].endswith(r"custom\soffice.exe") or paths[-1].endswith("custom")
    target = tmp_path / "PF" / "Tesseract-OCR" / "tesseract.exe"
    target.parent.mkdir(parents=True)
    target.write_text("")
    monkeypatch.setattr(finder.shutil, "which", lambda name: None)
    monkeypatch.setattr(finder, "engines_dirs", lambda: [tmp_path / "none"])
    assert finder.find_tool("tesseract") == target

def test_csv_separator_and_encoding(tmp_path):
    assert libreoffice.detect_separator("Имя;Сумма\nИван;250,5\n") == ";"
    assert libreoffice.detect_separator("a,b,c\n1,2,3\n") == ","
    assert libreoffice.detect_separator("a\tb\n1\t2\n") == "\t"
    f = tmp_path / "ru.csv"
    f.write_bytes("Имя;Город".encode("cp1251"))
    assert libreoffice.read_text_any(f) == "Имя;Город"
    f.write_bytes(b"\xef\xbb\xbf" + "Имя".encode("utf-8"))
    assert libreoffice.read_text_any(f) == "Имя"
    cmd = libreoffice.build_command("soffice.exe", tmp_path / "a.csv", "xlsx", tmp_path, "file:///p", separator=";")
    assert "--infilter=Text - txt - csv (StarCalc):59,34,76,1,,1049" in cmd


def test_namer_release_all(tmp_path):
    from fileconverter.naming import _reserved
    src = tmp_path / "a.png"
    src.write_text("x")
    namer = Namer()
    p = namer.file(src, "jpg")
    assert str(p).lower() in _reserved
    namer.release_all()
    assert str(p).lower() not in _reserved
    assert Namer().file(src, "jpg").name == "a.jpg"
