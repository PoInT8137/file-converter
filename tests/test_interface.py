"""Новый интерфейс: темы, переходы, палитра команд, уведомления, узкое окно."""
import pytest

ctk = pytest.importorskip("customtkinter")

from test_ui import app, pump  # noqa: F401  общая подготовка окна


@pytest.fixture
def animated(app):
    """Анимации включены так, как у пользователя, хотя окно в тестах прозрачное."""
    from fileconverter.ui import motion, theme as t
    hidden, enabled = t.HIDDEN, motion.enabled
    t.HIDDEN, motion.enabled, motion.too_slow = False, True, False
    yield app
    app.transition.finish()
    t.HIDDEN, motion.enabled = hidden, enabled


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


def test_animated_transition_ends_on_grid(animated):
    app = animated
    for key in ["pdf", "history", "convert", "settings", "convert"]:
        app.show_section(key)
        pump(app, 0.02)
    # раздел назначен сразу, анимация только догоняет
    assert app.current is app.pages["convert"]
    pump(app, 0.6)
    frame = app.current._parent_frame
    assert frame.winfo_manager() == "grid"
    for key, page in app.pages.items():
        if page is not app.current:
            outer = getattr(page, "_parent_frame", page)
            assert not outer.winfo_ismapped(), key
    assert app.transition.overlay is None
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
