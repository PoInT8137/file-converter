"""Проверки интерфейса через настоящие события мыши Tk.

Клик здесь проходит тот же путь, что и клик пользователя: наведение, нажатие и отпускание
на конкретной внутренней части виджета (метке, иконке, фону). Вызов методов напрямую
такие ошибки не ловит: так раньше один клик по плитке открывал выбор файла дважды.
"""
import shutil
import time

import pytest

ctk = pytest.importorskip("customtkinter")

from test_ui import pump, wait_job


def real_click(target, state=0, release_at=None):
    """Нажатие и отпускание левой кнопки мыши над tk-виджетом target."""
    target.update_idletasks()
    x, y = target.winfo_width() // 2, target.winfo_height() // 2
    rx, ry = target.winfo_rootx() + x, target.winfo_rooty() + y
    target.event_generate("<Enter>", x=x, y=y)
    target.event_generate("<Motion>", x=x, y=y)
    target.event_generate("<ButtonPress-1>", x=x, y=y, rootx=rx, rooty=ry, state=state)
    if release_at is not None:
        rx, ry = release_at
    try:
        target.event_generate("<ButtonRelease-1>", x=x, y=y, rootx=rx, rooty=ry, state=state)
    except Exception:
        pass  # виджет уже удалён: экран перестроился по нажатию


def part(widget, name="_label"):
    return getattr(widget, name, None) or widget._canvas


def labels(root):
    from fileconverter.ui.widgets import walk
    return [w for w in walk(root) if isinstance(w, ctk.CTkLabel)]


@pytest.fixture
def app(shared_app):
    from fileconverter.config import DEFAULTS
    a = shared_app
    for key, value in DEFAULTS.items():
        a.settings.set(key, value)
    a.stats.reset()
    a.queue_panel.clear()
    a.queue_panel.select([])
    a.errors.clear()
    a.show_section("convert")
    a.pages["convert"].show_home()
    pump(a, 0.1)
    yield a
    if hasattr(a, "_orig_pick"):
        a.pick_and_convert = a._orig_pick
        del a._orig_pick


@pytest.fixture
def files(data_dir, tmp_path):
    for name in ["документ.pdf", "картинка.png"]:
        shutil.copy2(data_dir / name, tmp_path / name)
    shutil.copy2(data_dir / "документ.pdf", tmp_path / "второй.pdf")
    return tmp_path


def count_picks(app):
    calls = []
    app._orig_pick = app.pick_and_convert
    app.pick_and_convert = lambda src, dst: calls.append((src, dst))
    app.pages["convert"].show_home()
    pump(app, 0.2)
    return calls


@pytest.mark.parametrize("where", ["надпись", "иконка", "фон"])
def test_tile_click_opens_picker_once(app, where):
    calls = count_picks(app)
    tile = app.pages["convert"].tiles[0]
    lbls = labels(tile)
    target = {"надпись": part(lbls[3]), "иконка": part(lbls[0]), "фон": tile._canvas}[where]
    real_click(target)
    pump(app, 0.2)
    assert calls == [tile.pair]


def test_pin_click_pins_without_opening_picker(app):
    calls = count_picks(app)
    page = app.pages["convert"]
    tile = page.tiles[3]
    real_click(tile._canvas, release_at=(0, 0))  # наведение показывает булавку, клик мимо не считается
    pin = [w for w in tile.winfo_children() if isinstance(w, ctk.CTkButton)][0]
    pump(app, 0.1)
    real_click(part(pin, "_canvas"))
    pump(app, 0.3)
    assert app.stats.is_pinned(*tile.pair)
    assert page.tiles[0].pair == tile.pair
    assert calls == []


def test_release_outside_tile_is_not_a_click(app):
    calls = count_picks(app)
    tile = app.pages["convert"].tiles[0]
    real_click(part(labels(tile)[3]), release_at=(tile.winfo_rootx() - 50, tile.winfo_rooty() - 50))
    pump(app, 0.2)
    assert calls == []


def test_params_header_click_toggles(app, files):
    app.add_files([files / "документ.pdf"])
    pump(app, 0.3)
    page = app.pages["convert"]
    head = [w for w in labels(page.body) if w.cget("text") == "ПАРАМЕТРЫ"][0]
    assert page.params_open is False
    real_click(part(head))
    pump(app, 0.2)
    assert page.params_open is True
    head = [w for w in labels(page.body) if w.cget("text") == "ПАРАМЕТРЫ"][0]
    real_click(part(head))
    pump(app, 0.2)
    assert page.params_open is False


def test_format_card_click_selects(app, files):
    app.add_files([files / "документ.pdf"])
    pump(app, 0.3)
    page = app.pages["convert"]
    for dst, card in list(page.cards.items()):
        real_click(part(card.parts[1]))
        pump(app, 0.1)
        assert page.selected_dst == dst
        assert dst.upper() in page.go.cget("text")


def test_ctrl_click_selects_two_and_merges(app, files):
    import pymupdf
    a, b = app.add_files([files / "документ.pdf", files / "второй.pdf"])
    pump(app, 0.3)
    rows = app.queue_panel.rows
    real_click(part(rows[id(a)].name))
    real_click(part(rows[id(b)].name), state=0x0004)
    pump(app, 0.2)
    assert app.queue_panel.selected == [a, b]
    real_click(part(app.nav["pdf"][0], "_text_label"))
    pump(app, 0.3)
    tools = app.pages["pdf"]
    assert app.current is tools
    real_click(tools.cards["pdf_merge"]._canvas)
    pump(app, 0.2)
    assert tools.selected.id == "pdf_merge"
    assert "2" in tools.action_text.cget("text")
    real_click(part(tools.run_btn, "_text_label"))
    wait_job(app, a)
    assert a.status == "done", a.error
    merged = a.outputs[0]
    with pymupdf.open(str(merged)) as doc:
        assert doc.page_count == 4


def test_plain_click_replaces_selection(app, files):
    a, b = app.add_files([files / "документ.pdf", files / "второй.pdf"])
    pump(app, 0.3)
    rows = app.queue_panel.rows
    real_click(part(rows[id(a)].name))
    real_click(part(rows[id(b)].name))
    pump(app, 0.2)
    assert app.queue_panel.selected == [b]


def test_queue_cross_removes_file(app, files):
    item = app.add_files([files / "картинка.png"])[0]
    pump(app, 0.3)
    real_click(part(app.queue_panel.rows[id(item)].remove, "_canvas"))
    pump(app, 0.2)
    assert item not in app.queue_panel.items


def test_fields_dialog_requires_password(app):
    from fileconverter.tools import TOOLS_BY_ID
    from fileconverter.ui.widgets import FieldsDialog, walk
    d = FieldsDialog(app, "Пароль", TOOLS_BY_ID["pdf_encrypt"].fields)
    d.deiconify()
    pump(app, 0.4)
    ok = [w for w in walk(d) if isinstance(w, ctk.CTkButton) and w.cget("text") == "Выполнить"][0]
    real_click(part(ok, "_text_label"))
    pump(app, 0.2)
    assert d.winfo_exists() and d.result is None
    assert any(w.cget("text") == "Заполните это поле" and w.winfo_ismapped() for w in labels(d))
    entry = [w for w in walk(d) if isinstance(w, ctk.CTkEntry)][0]
    entry.insert(0, "секрет")
    real_click(part(ok, "_text_label"))
    pump(app, 0.2)
    assert d.result == {"password": "секрет"}


def test_sidebar_buttons_open_sections(app):
    from fileconverter.app import SECTION_NAMES
    for key in SECTION_NAMES:
        real_click(part(app.nav[key][0], "_text_label"))
        pump(app, 0.1)
        assert app.current is app.pages[key]
    assert not app.errors


def test_tools_action_bar_always_visible(app):
    real_click(part(app.nav["pdf"][0], "_text_label"))
    pump(app, 0.3)
    tools = app.pages["pdf"]
    # панель действия вне прокручиваемой области: кнопка внутри видимой части раздела
    page_bottom = tools.winfo_rooty() + tools.winfo_height()
    assert tools.run_btn.winfo_ismapped()
    assert tools.run_btn.winfo_rooty() + tools.run_btn.winfo_height() <= page_bottom
