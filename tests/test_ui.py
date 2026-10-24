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
def app(shared_app):
    from fileconverter.config import DEFAULTS
    a = shared_app
    for key, value in DEFAULTS.items():
        a.settings.set(key, value)
    a.stats.reset()
    a.stats.recent = []
    a.history.clear()
    a.queue_panel.clear()
    a.queue_panel.select([])
    a.errors.clear()
    a.show_section("convert")
    a.pages["convert"].show_home()
    pump(a, 0.1)
    return a


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


def test_poll_survives_errors(app, data_dir, tmp_path):
    app.settings.set("output_dir", str(tmp_path / "out"))

    def boom():
        raise RuntimeError("проверка")

    app.call_soon(boom)
    pump(app, 0.3)
    items = app.add_files([data_dir / "картинка.png"])
    app.start_conversion(items, "jpg")
    wait_job(app, items[0])
    assert items[0].status == "done"
    assert len(app.errors) == 1
    app.errors.clear()


def test_ctrl_k_keeps_entry_text(app):
    app.show_section("settings")
    pump(app, 0.2)
    e = app.pages["settings"].path_entries["tesseract_path"]
    e.insert(0, "abcdef")
    e._entry.icursor(3)
    e._entry.focus_force()
    pump(app, 0.2)
    e._entry.event_generate("<Control-Key-k>", keycode=75)
    pump(app, 0.2)
    assert e.get() == "abcdef"
    assert app.focus_get() == app.search._entry


def test_settings_rescan_and_refresh(app):
    app.show_section("settings")
    pump(app, 0.2)
    page = app.pages["settings"]
    page.path_entries["libreoffice_path"].insert(0, r"D:\нет\soffice.exe")
    page.rescan()
    assert app.settings.get("libreoffice_path") == r"D:\нет\soffice.exe"
    app.settings.set("libreoffice_path", "")
    app.show_section("convert")
    app.settings.set("open_after", True)
    app.show_section("settings")
    pump(app, 0.2)
    from fileconverter.ui.widgets import walk
    boxes = [w for w in walk(app.pages["settings"]) if isinstance(w, ctk.CTkCheckBox)]
    assert boxes[0].get() == 1


def test_unknown_file(app, tmp_path):
    f = tmp_path / "что-то.xyz"
    f.write_text("x")
    items = app.add_files([f])
    pump(app, 0.05)
    assert app.pages["convert"].item is items[0]
    assert not app.errors
