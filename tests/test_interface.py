"""Новый интерфейс: темы, переходы, палитра команд, уведомления, узкое окно."""
import pytest

ctk = pytest.importorskip("customtkinter")

from test_ui import app, pump  # noqa: F401  общая подготовка окна


def test_theme_switch_repaints(app):
    from fileconverter.ui import theme as t
    try:
        for mode, dark in (("light", False), ("dark", True)):
            app.set_theme(mode)
            pump(app, 0.2)
            assert t.is_dark() is dark
            assert app.settings.get("theme") == mode
            assert app.cget("bg").lower() == t.color(t.BG).lower()
            canvas = app.queue_panel.list._parent_canvas
            assert canvas.cget("bg").lower() == t.color(t.QUEUE).lower()
    finally:
        app.set_theme("system")
    assert not app.errors


def test_light_icons_differ_from_dark():
    from fileconverter.ui import theme as t
    img = t.ui_icon("search", "muted", 16)
    light, dark = img.cget("light_image"), img.cget("dark_image")
    assert light.getpixel((24, 24)) != dark.getpixel((24, 24)) or light.tobytes() != dark.tobytes()


def test_sections_switch_instantly(app):
    for key in ["pdf", "history", "convert"]:
        app.show_section(key)
        outer = getattr(app.current, "_parent_frame", app.current)
        assert outer.winfo_manager() == "grid"
    pump(app, 0.1)
    for key, page in app.pages.items():
        if page is not app.current:
            assert not getattr(page, "_parent_frame", page).winfo_ismapped(), key


def test_nav_colors_follow_selection(app):
    from fileconverter.ui import theme as t
    app.show_section("history")
    pump(app, 0.1)
    assert app.nav["history"][0].cget("fg_color") == t.CARD_SEL
    assert app.nav["history"][0].cget("text_color") == t.TEXT
    assert app.nav["convert"][0].cget("fg_color") == t.BAR
    assert app.nav["convert"][0].cget("text_color") == t.MUTED


def test_nav_fade_reaches_target_colors():
    from fileconverter.ui import motion
    assert motion.mix("#000000", "#ffffff", 0.5) == "#808080"
    assert motion.mix("#14181d", "#14181d", 0.3) == "#14181d"


def test_dialog_backdrop_and_cleanup(app):
    from fileconverter.ui.widgets import Dialog
    before = app.tk.call("bind", app._w, "<Configure>")
    d = Dialog(app, "Проверка")
    d.buttons("Готово", "Отмена")
    seen = {}

    def answer():
        seen["backdrop"] = d.backdrop is not None and d.backdrop.winfo_exists()
        d.ok("да")

    app.after(200, answer)
    assert d.show() == "да"
    assert seen["backdrop"]
    assert not d.winfo_exists()
    # обработчик слежения за окном снят, остальные (CustomTkinter, узкий режим) на месте
    def lines(script):
        return [line for line in script.split("\n") if line.strip()]

    assert lines(app.tk.call("bind", app._w, "<Configure>")) == lines(before)
    assert not app.errors


def test_marker_follows_section(app):
    app.show_section("settings")
    pump(app, 0.2)
    btn = app.nav["settings"][0]
    scale = ctk.ScalingTracker.get_widget_scaling(app.side)
    centre = (btn.winfo_y() + btn.winfo_height() / 2) / scale
    assert abs(app.marker_y + 10 - centre) < 2


def test_palette_keyboard(app):
    calls = []
    app.palette.open()
    pump(app, 0.1)
    assert app.palette.is_open
    assert len(app.palette.rows) > 3
    app.palette.entry.insert(0, "сжать")
    app.palette.refresh()
    assert any("Сжать" in r[1] for r in app.palette.results)
    app.palette.results[0] = ("Т", "проверка", lambda: calls.append(1))
    app.palette.move(1)
    app.palette.move(-1)
    app.palette.pick(app.palette.index)
    pump(app, 0.1)
    assert calls == [1]
    assert not app.palette.is_open


def test_palette_closes_on_outside_click(app):
    from test_clicks import real_click
    app.palette.open()
    pump(app, 0.1)
    real_click(app.queue_panel.count._label)
    pump(app, 0.1)
    assert not app.palette.is_open


def test_hotkeys_switch_sections(app):
    from types import SimpleNamespace
    # обработчик напрямую: клавиатурные события доходят только до активного окна, а окно тестов прозрачное
    assert app.on_ctrl_key(SimpleNamespace(keycode=50)) == "break"
    pump(app, 0.1)
    assert app.current_key == "pdf"
    app.on_ctrl_key(SimpleNamespace(keycode=49))
    pump(app, 0.1)
    assert app.current_key == "convert"
    assert app.on_ctrl_key(SimpleNamespace(keycode=65)) is None


def test_toasts_stack_and_merge(app, data_dir, tmp_path):
    app.toasts.clear()
    for i in range(5):
        app.toasts.show(f"сообщение {i}")
    pump(app, 0.1)
    assert len(app.toasts.items) == app.toasts.LIMIT
    app.toasts.clear()

    class Job:
        status, error, tool = "done", "", None

    a, b = Job(), Job()
    a.outputs, b.outputs = [tmp_path / "a.docx"], [tmp_path / "b.docx"]
    app.notify_done(a, [])
    app.notify_done(b, [])
    assert len(app.toasts.items) == 1
    assert "2" in app.toasts.items[0].text.cget("text")
    app.toasts.clear()


def test_compact_sidebar(app):
    app.set_compact(True)
    pump(app, 0.1)
    assert app.nav["convert"][0].cget("text") == ""
    app.set_compact(False)
    pump(app, 0.1)
    assert app.nav["convert"][0].cget("text") == "Конвертация"


def test_engines_panel_lists_engines(app):
    from fileconverter.ui.widgets import walk
    app.engines_panel.open()
    pump(app, 0.1)
    texts = [w.cget("text") for w in walk(app.engines_panel) if isinstance(w, ctk.CTkLabel)]
    for _, title, _ in app.engines.status():
        assert title in texts
    app.engines_panel.close()
    assert not app.engines_panel.is_open


def test_settings_not_rebuilt_without_changes(app):
    app.show_section("settings")
    pump(app, 0.1)
    body = app.pages["settings"].body
    app.show_section("convert")
    app.show_section("settings")
    assert app.pages["settings"].body is body
    app.show_section("convert")
    app.settings.set("open_after", True)
    app.show_section("settings")
    assert app.pages["settings"].body is not body


def test_scrollbar_draws_once_after_layout(app):
    from customtkinter.windows.widgets.ctk_scrollbar import CTkScrollbar
    from fileconverter.ui import ctk_patches
    assert CTkScrollbar.set is ctk_patches._set
    bar = app.queue_panel.list._scrollbar
    calls = []
    original = bar._draw
    bar._draw = lambda *a, **k: (calls.append(1), original(*a, **k))
    try:
        for i in range(10):
            bar.set(0, 0.5 + i / 100)
        assert calls == []
        pump(app, 0.05)
        assert len(calls) == 1
    finally:
        del bar._draw


def test_prebuild_builds_pages_under_current(app):
    for key in list(app.pages):
        if key not in ("convert", "settings"):
            app.pages.pop(key).destroy()
    app.prebuild_next()
    pump(app, 0.05)
    built = [k for k in app.PREBUILD if k in app.pages]
    assert built
    assert app.current is app.pages["convert"]
    for key in built:
        outer = getattr(app.pages[key], "_parent_frame", app.pages[key])
        assert not outer.winfo_ismapped(), key
