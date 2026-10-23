import time

import pytest

ctk = pytest.importorskip("customtkinter")


def pump(app, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def wait_job(app, item, timeout=60):
    end = time.time() + timeout
    while time.time() < end and item.status not in ("done", "error"):
        pump(app, 0.05)
    pump(app, 0.2)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("FILECONVERTER_DATA", str(tmp_path / "data"))
    from fileconverter.app import App
    a = App(selftest=True)
    pump(a)
    yield a
    a.on_close()


def test_sections_open(app):
    from fileconverter.app import SECTION_NAMES
    for key in SECTION_NAMES:
        app.show_section(key)
        pump(app, 0.05)
        assert app.current is app.pages[key]
    assert not app.errors


def test_tiles_from_stats(app):
    from fileconverter.stats import DEFAULT_PAIRS
    page = app.pages["convert"]
    assert [t.pair for t in page.tiles] == DEFAULT_PAIRS
    app.stats.add("wav", "mp3")
    app.stats.add("wav", "mp3")
    app.stats.toggle_pin("png", "webp")
    page.show_home()
    pump(app, 0.05)
    pairs = [t.pair for t in page.tiles]
    assert pairs[:2] == [("png", "webp"), ("wav", "mp3")]
    assert len(pairs) == 8


def test_file_view_and_convert(app, data_dir, tmp_path):
    app.settings.set("output_dir", str(tmp_path / "out"))
    items = app.add_files([data_dir / "документ.pdf"])
    pump(app)
    page = app.pages["convert"]
    assert page.item is items[0]
    assert page.selected_dst == "docx"
    page.select_card("docx")
    page.start()
    wait_job(app, items[0], 120)
    assert items[0].status == "done", items[0].error
    assert page.log is not None
    text = page.log.text.get("1.0", "end")
    assert "Готово:" in text
    assert app.stats.count("pdf", "docx") == 1
    assert not app.errors


def test_tool_without_fields(app, data_dir, tmp_path):
    from fileconverter.tools import TOOLS_BY_ID
    app.settings.set("output_dir", str(tmp_path / "out"))
    items = app.add_files([data_dir / "документ.pdf"])
    app.show_section("pdf")
    page = app.pages["pdf"]
    page.select(TOOLS_BY_ID["pdf_text"])
    pump(app, 0.05)
    assert page.files() == items
    page.run()
    wait_job(app, items[0])
    assert items[0].status == "done"
    assert page.log is not None
    assert not app.errors


def test_search_and_all_conversions(app):
    from fileconverter.ui.other_pages import AllConversions
    found = app.search_items("сжать")
    assert any("Сжать" in r[1] for r in found)
    found = app.search_items("pdf docx")
    assert any(r[1] == "PDF в DOCX" for r in found)
    assert app.search_items("") == []
    d = AllConversions(app)
    d.entry.insert(0, "jpg png")
    d.fill()
    assert len(d.list.winfo_children()) >= 2
    pump(app, 0.05)
    d.destroy()


def test_unknown_file(app, tmp_path):
    f = tmp_path / "что-то.xyz"
    f.write_text("x")
    items = app.add_files([f])
    pump(app, 0.05)
    assert app.pages["convert"].item is items[0]
    assert not app.errors
