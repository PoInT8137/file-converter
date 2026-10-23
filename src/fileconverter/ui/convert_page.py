import threading
import time
import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from ..engines import ffmpeg as ffmpeg_engine
from ..engines.pdf import pdf_info
from ..engines.images import image_info
from ..osutils import human_size, show_in_folder
from ..registry import CATEGORIES, CATEGORY_NAMES, category, registry, title
from ..tools import QUICK, SECTION_TITLES, TOOLS_BY_ID, section_for_ext, section_tools
from . import theme as t
from .widgets import (DashedBox, on_event, Flow, Popover, ResponsiveGrid, TabBar, accent_button, caption, holder, label,
                      make_clickable, mono_label, outline_button)

DEFAULT_TARGET = {
    "pdf": "docx", "docx": "pdf", "doc": "pdf", "odt": "pdf", "rtf": "pdf", "txt": "pdf",
    "pptx": "pdf", "ppt": "pdf", "odp": "pdf", "xlsx": "pdf", "xls": "pdf", "ods": "pdf", "csv": "xlsx",
    "jpg": "pdf", "png": "jpg", "heic": "jpg", "webp": "png", "gif": "mp4", "bmp": "png", "tiff": "pdf",
    "mp4": "mp3", "mov": "mp4", "mkv": "mp4", "avi": "mp4", "webm": "mp4",
    "wav": "mp3", "flac": "mp3", "m4a": "mp3", "ogg": "mp3", "md": "docx", "html": "pdf", "epub": "docx",
}


def times(n):
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} раза"
    return f"{n} раз"


class LogView(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=t.BAR, corner_radius=t.RADIUS, border_width=1, border_color=t.BORDER)
        self.app = app
        caption(self, "ЖУРНАЛ").pack(anchor="w", padx=14, pady=(10, 4))
        # обычный tk.Text вместо CTkTextbox: тот каждые 200 мс ставит after() с lambda и не снимает его
        # при удалении, а такой зависший вызов потом срабатывает на чужом обработчике
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        self.text = tk.Text(self, height=7, bg=t.BAR, fg=t.CAPTION, font=(t.MONO, -round(12 * scale)),
                            relief="flat", borderwidth=0, highlightthickness=0, wrap="word",
                            insertbackground=t.CAPTION, selectbackground=t.BORDER_BTN)
        self.text.pack(fill="x", padx=14)
        self.text.tag_config("ok", foreground=t.SUCCESS)
        self.text.tag_config("err", foreground=t.ERROR)
        self.footer = holder(self, t.BAR)
        self.footer.pack(fill="x", padx=14, pady=(4, 10))
        self.footer_for = None

    def show_job(self, job):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for line in job.log:
            tag = "ok" if "Готово:" in line else ("err" if "Ошибка:" in line else None)
            self.text.insert("end", line + "\n", tag)
        self.text.see("end")
        self.text.configure(state="disabled")
        if self.footer_for == (job.id, job.status):
            return
        self.footer_for = (job.id, job.status)
        for w in self.footer.winfo_children():
            w.destroy()
        if job.status == "done" and job.outputs:
            first = job.outputs[0]
            outline_button(self.footer, "Открыть папку", lambda: show_in_folder(first), width=150,
                           image=t.ui_icon("folder-open", "muted", 16), compound="left").pack(side="left")


class ConvertPage(ctk.CTkScrollableFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=t.MAIN, corner_radius=0, scrollbar_button_color=t.BORDER,
                         scrollbar_button_hover_color=t.BORDER_BTN)
        self.app = app
        self.item = None
        self.selected_dst = None
        self.log = None
        self.go = None
        self.body = None
        self.params_open = app.settings.get("params_open")
        self.show_home()

    def clear(self):
        if self.body is not None:
            self.body.destroy()
        self.body = ctk.CTkFrame(self, fg_color=t.MAIN, corner_radius=0)
        self.body.pack(fill="both", expand=True, padx=28, pady=22)
        self.log = None
        self.go = None
        self._parent_canvas.yview_moveto(0)
        return self.body

    def show_home(self):
        self.item = None
        b = self.clear()
        label(b, "Конвертация файла", 22, weight="bold").pack(anchor="w")
        label(b, "Перетащите файлы в окно и выберите формат. Результат появится рядом с исходным файлом.",
              13, t.MUTED, wraplength=440, justify="left").pack(anchor="w", pady=(2, 16))

        drop = DashedBox(b, height=150)
        drop.pack(fill="x")
        ctk.CTkLabel(drop.inner, text="", image=t.ui_icon("upload", "accent", 30)).pack()
        label(drop.inner, "Перетащите файлы сюда", 15, weight="bold").pack(pady=(6, 2))
        mono_label(drop.inner, "PDF, DOCX, XLSX, PPTX, JPG, PNG, HEIC, MP3, MP4 и другие", 11).pack(pady=(0, 8))
        outline_button(drop.inner, "Выбрать файлы", self.app.pick_files, width=170).pack()

        head = ctk.CTkFrame(b, fg_color=t.MAIN)
        head.pack(fill="x", pady=(26, 10))
        caption(head, "ЧАСТЫЕ КОНВЕРТАЦИИ").pack(side="left")
        outline_button(head, "Все конвертации", self.app.show_all_conversions, width=160, size=12,
                       image=t.ui_icon("list", "muted", 16), compound="left").pack(side="right")

        grid = ResponsiveGrid(b, min_width=150, max_cols=4)
        grid.pack(fill="x")
        self.tiles = []
        for src, dst in self.app.stats.top_pairs(8):
            tile = self.make_tile(grid, src, dst)
            grid.add(tile)
            self.tiles.append(tile)

        recent = self.app.stats.recent_items(3)
        caption(b, "НЕДАВНИЕ").pack(anchor="w", pady=(18, 6))
        if not recent:
            mono_label(b, "Здесь появятся последние результаты", 11).pack(anchor="w")
        for r in recent:
            self.recent_row(b, r)

    def make_tile(self, parent, src, dst):
        conv = registry.get(src, dst, self.app.engines)
        stats = self.app.stats
        pinned = stats.is_pinned(src, dst)
        tile = ctk.CTkFrame(parent, fg_color=t.CARD, corner_radius=t.RADIUS, border_width=1,
                            border_color=t.BORDER, height=104)
        tile.pair = (src, dst)
        icons = ctk.CTkFrame(tile, fg_color="transparent")
        icons.pack(anchor="w", padx=14, pady=(14, 6))
        ctk.CTkLabel(icons, text="", image=t.get_icon(src, 30)).pack(side="left")
        ctk.CTkLabel(icons, text="", image=t.ui_icon("arrow-right", "muted", 16)).pack(side="left", padx=6)
        ctk.CTkLabel(icons, text="", image=t.get_icon(dst, 30)).pack(side="left")
        name = label(tile, f"{src.upper()} в {dst.upper()}", 14, t.TEXT if conv else t.MUTED, "bold")
        name.pack(anchor="w", padx=14)
        count = stats.count(src, dst)
        info = times(count)
        if conv is None:
            info = "нет движка"
        mono_label(tile, info, 11).pack(anchor="w", padx=14, pady=(0, 12))
        pin = ctk.CTkButton(tile, text="", width=30, height=30, corner_radius=t.RADIUS,
                            image=t.ui_icon("pin", "accent" if pinned else "muted", 15),
                            fg_color="transparent", hover_color=t.BORDER,
                            command=lambda: self.toggle_pin(src, dst))
        if pinned:
            pin.place(relx=1.0, x=-6, y=6, anchor="ne")

        def enter():
            tile.configure(fg_color=t.CARD_SEL, border_color=t.BORDER_BTN)
            pin.place(relx=1.0, x=-6, y=6, anchor="ne")

        def leave():
            tile.configure(fg_color=t.CARD, border_color=t.BORDER)
            if not stats.is_pinned(src, dst):
                pin.place_forget()

        def click():
            if conv is None:
                self.explain_missing(tile, src, dst)
            else:
                self.app.pick_and_convert(src, dst)

        make_clickable(tile, click, enter, leave)
        pin.configure(cursor="hand2")
        self.app.register_drop(tile, lambda paths, d=dst: self.app.convert_paths(paths, d))
        return tile

    def explain_missing(self, widget, src, dst):
        conv = registry.get(src, dst)
        need = conv.engine_label if conv else "движок"
        Popover(widget, f"Для {src.upper()} в {dst.upper()} нужен {need}. Он не найден на компьютере.\n"
                        "Подробности в нижней панели ДВИЖКИ.", below=True)

    def toggle_pin(self, src, dst):
        self.app.stats.toggle_pin(src, dst)
        self.show_home()

    def recent_row(self, parent, r):
        path = Path(r["path"])
        row = ctk.CTkFrame(parent, fg_color=t.MAIN)
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(row, text="", image=t.get_icon(path.suffix, 22)).pack(side="left", padx=(0, 8))
        label(row, path.name, 13).pack(side="left")
        mono_label(row, time.strftime("%d.%m %H:%M", time.localtime(r.get("time", 0))), 11).pack(side="left", padx=10)
        outline_button(row, "Открыть папку", lambda: show_in_folder(path), width=130, size=12).pack(side="right")

    def show_file(self, item):
        self.item = item
        b = self.clear()
        ext = item.ext
        targets = registry.targets(ext, self.app.engines)

        head = ctk.CTkFrame(b, fg_color=t.MAIN)
        head.pack(fill="x")
        head.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(head, text="", image=t.get_icon(ext, 48)).grid(row=0, column=0, rowspan=2, padx=(0, 14))
        name = item.path.name if len(item.path.name) < 48 else item.path.name[:44] + "..."
        label(head, name, 18, weight="bold", anchor="w", wraplength=360, justify="left").grid(
            row=0, column=1, sticky="w")
        self.props = mono_label(head, self.props_text(item, {}), 12, wraplength=360, justify="left")
        self.props.grid(row=1, column=1, sticky="w")
        back = outline_button(head, "", self.app.go_home, width=t.H, image=t.ui_icon("x", "muted", 16))
        back.grid(row=0, column=2, rowspan=2, sticky="ne")
        back.bind("<Enter>", on_event(lambda e: Popover(back, "Закрыть файл и вернуться на главную", timeout=1500)), add="+")
        self.load_props(item)

        if not targets:
            msg = "Для этого типа файла нет доступных конвертаций."
            if not registry.accepts(ext):
                msg = f"Формат {ext.upper() or 'без расширения'} не поддерживается."
            label(b, msg, 14, t.MUTED).pack(anchor="w", pady=30)
            self.quick_actions(b, item)
            return

        best = self.app.stats.best_target(ext, [c.dst for c in targets])
        if best is None:
            default = DEFAULT_TARGET.get(ext)
            best = default if default in [c.dst for c in targets] else targets[0].dst
        self.best = best
        self.targets = targets
        self.selected_dst = best

        caption(b, "КОНВЕРТИРОВАТЬ В").pack(anchor="w", pady=(22, 4))
        cats = []
        for key, cname in CATEGORIES:
            n = sum(1 for c in targets if category(c.dst) == key)
            if n:
                cats.append((key, f"{cname}  {n}"))
        self.tabs = TabBar(b, cats, self.show_category, active=category(best))
        self.tabs.pack(fill="x")
        self.cards_frame = holder(b)
        self.cards_frame.pack(fill="x", pady=(12, 0))
        self.note = label(b, "", 12, t.ACCENT, justify="left", wraplength=600)
        self.scan_row = holder(b)
        self.scan_row.pack(fill="x")
        self.show_category(category(best))

        self.quick_actions(b, item)
        self.params_block(b)

        buttons = ctk.CTkFrame(b, fg_color=t.MAIN)
        buttons.pack(fill="x", pady=(20, 0))
        self.go = accent_button(buttons, "", self.start, height=52, size=15, width=300)
        self.go.pack(side="left")
        outline_button(buttons, "Вся очередь", self.start_all, height=52, width=160).pack(side="left", padx=10)
        self.update_go()

        self.log_holder = holder(b)
        self.log_holder.pack(fill="x", pady=(18, 0))
        if item.jobs:
            self.show_log(item.jobs[-1])

    def props_text(self, item, extra):
        parts = [human_size(item.size), item.ext.upper() or "?"]
        if "pages" in extra:
            parts.append(f"{extra['pages']} стр.")
        if "size" in extra:
            parts.append(extra["size"])
        if "duration" in extra:
            parts.append(extra["duration"])
        if "text" in extra:
            parts.append(extra["text"])
        return "  /  ".join(parts)

    def load_props(self, item):
        def work():
            extra = {}
            try:
                if item.ext == "pdf":
                    info = pdf_info(item.path)
                    if info["encrypted"]:
                        extra["text"] = "защищён паролем"
                    else:
                        extra["pages"] = info["pages"]
                        extra["text"] = "найден текстовый слой" if info["has_text"] else "похоже на скан"
                        extra["scan"] = not info["has_text"]
                elif category(item.ext) == "images":
                    info = image_info(item.path)
                    if info:
                        extra["size"] = f"{info['width']}x{info['height']} px"
                elif category(item.ext) in ("audio", "video") and self.app.engines.available("ffmpeg"):
                    d = ffmpeg_engine.probe_duration(self.app.engines, item.path)
                    if d:
                        extra["duration"] = ffmpeg_engine.format_time(d)
            except Exception:
                pass
            self.app.call_soon(lambda: self.apply_props(item, extra))

        threading.Thread(target=work, daemon=True).start()

    def apply_props(self, item, extra):
        if self.item is not item:
            return
        try:
            self.props.configure(text=self.props_text(item, extra))
            if extra.get("scan"):
                self.show_scan_hint()
        except Exception:
            pass

    def show_scan_hint(self):
        for w in self.scan_row.winfo_children():
            w.destroy()
        box = ctk.CTkFrame(self.scan_row, fg_color=t.CARD, corner_radius=t.RADIUS, border_width=1,
                           border_color=t.ACCENT)
        box.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(box, text="", image=t.ui_icon("scan-text", "accent", 20)).pack(side="left", padx=(14, 8), pady=10)
        label(box, "Похоже на скан без текста: DOCX и TXT будут пустыми. Лучше распознать текст (OCR).",
              12, wraplength=420, justify="left").pack(side="left", pady=10)
        if self.app.engines.available("tesseract"):
            accent_button(box, "Распознать", lambda: self.app.run_quick("ocr_docx", [self.item]), width=130,
                          size=13).pack(side="right", padx=10, pady=8)
        else:
            mono_label(box, "Tesseract не найден", 11, t.ERROR).pack(side="right", padx=14)

    def show_category(self, key):
        for w in self.cards_frame.winfo_children():
            w.destroy()
        cards = [c for c in self.targets if category(c.dst) == key]
        cards.sort(key=lambda c: c.dst != self.best)
        grid = ResponsiveGrid(self.cards_frame, min_width=190, max_cols=3)
        grid.pack(fill="x")
        self.cards = {}
        for conv in cards:
            grid.add(self.format_card(grid, conv))
        if self.selected_dst not in [c.dst for c in cards] and cards:
            self.selected_dst = cards[0].dst
        self.paint_cards()
        self.update_go()

    def format_card(self, parent, conv):
        card = ctk.CTkFrame(parent, fg_color=t.CARD, corner_radius=t.RADIUS, border_width=1,
                            border_color=t.BORDER, height=80)
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(card, text="", image=t.get_icon(conv.dst, 34)).grid(row=0, column=0, rowspan=3,
                                                                       padx=(12, 10), pady=12)
        code = ctk.CTkLabel(card, text=conv.dst.upper(), font=t.mono(17, "bold"), anchor="w")
        code.grid(row=0, column=1, sticky="w", pady=(10, 0))
        name = ctk.CTkLabel(card, text=title(conv.dst), font=t.font(12), anchor="w")
        name.grid(row=1, column=1, sticky="w")
        eng = ctk.CTkLabel(card, text=conv.engine_label, font=t.mono(10), anchor="w")
        eng.grid(row=2, column=1, sticky="w", pady=(0, 10))
        badge = None
        if conv.dst == self.best:
            badge = ctk.CTkLabel(card, text="ЧАСТО", font=t.mono(9, "bold"), corner_radius=4, height=18)
            badge.grid(row=0, column=2, sticky="ne", padx=8, pady=8)
        card.parts = (code, name, eng, badge)
        card.conv = conv
        self.cards[conv.dst] = card

        def hover(on):
            if conv.dst != self.selected_dst:
                card.configure(fg_color=t.CARD_SEL if on else t.CARD)

        make_clickable(card, lambda: self.select_card(conv.dst), lambda: hover(True), lambda: hover(False))
        return card

    def paint_cards(self):
        for dst, card in self.cards.items():
            code, name, eng, badge = card.parts
            on = dst == self.selected_dst
            card.configure(fg_color=t.ACCENT if on else t.CARD, border_color=t.ACCENT if on else t.BORDER)
            code.configure(text_color=t.ON_ACCENT if on else t.TEXT)
            name.configure(text_color=t.ON_ACCENT if on else t.CAPTION)
            eng.configure(text_color="#4A3B1E" if on else t.MUTED)
            if badge is not None:
                badge.configure(fg_color=t.ON_ACCENT if on else t.ACCENT, text_color=t.ACCENT if on else t.ON_ACCENT)
        conv = self.current_conv()
        if conv and conv.note:
            self.note.configure(text=conv.note)
            self.note.pack(anchor="w", after=self.cards_frame)
        else:
            self.note.pack_forget()

    def select_card(self, dst):
        self.selected_dst = dst
        self.paint_cards()
        self.update_go()

    def current_conv(self):
        for c in getattr(self, "targets", []):
            if c.dst == self.selected_dst:
                return c
        return None

    def update_go(self):
        if self.go is not None and self.selected_dst:
            self.go.configure(text=f"Конвертировать в {self.selected_dst.upper()}")

    def quick_actions(self, parent, item):
        cat = "pdf" if item.ext == "pdf" else category(item.ext)
        ids = QUICK.get(cat, [])
        if not ids:
            return
        caption(parent, "БЫСТРЫЕ ДЕЙСТВИЯ").pack(anchor="w", pady=(22, 8))
        row = Flow(parent)
        row.pack(fill="x")
        for tid in ids:
            tool = TOOLS_BY_ID[tid]
            ok = self.app.engines.available(tool.engine)
            short = {"ocr_pdf": "Распознать текст", "ocr_txt": "Распознать текст"}.get(tid, tool.title)
            row.add(outline_button(row, short, lambda i=tid: self.app.run_quick(i, [item]), size=12,
                                   image=t.ui_icon(tool.icon, "muted", 16), compound="left", width=40,
                                   color=t.TEXT if ok else t.MUTED))
        section = section_for_ext(item.ext)
        if section:
            extra = len(section_tools(section)) - len([i for i in ids if TOOLS_BY_ID[i].section == section])
            name = SECTION_TITLES[section]
            text = f"Все {name[0].lower() + name[1:]}" if section != "pdf" else "Все инструменты PDF"
            if extra > 0:
                text += f" +{extra}"
            row.add(outline_button(row, text, lambda: self.app.show_section(section), size=12, border=t.ACCENT,
                                   color=t.ACCENT, width=40))

    def params_block(self, parent):
        box = ctk.CTkFrame(parent, fg_color=t.CARD, corner_radius=t.RADIUS, border_width=1, border_color=t.BORDER)
        box.pack(fill="x", pady=(18, 0))
        head = ctk.CTkFrame(box, fg_color="transparent", height=t.H)
        head.pack(fill="x", padx=12)
        arrow = ctk.CTkLabel(head, text="", image=t.ui_icon("chevron-down" if self.params_open else "chevron-right",
                                                            "muted", 16))
        arrow.pack(side="left", pady=12)
        caption(head, "ПАРАМЕТРЫ").pack(side="left", padx=(6, 12))
        summary = mono_label(head, self.app.settings.summary(), 11)
        summary.pack(side="left")
        inner = ctk.CTkFrame(box, fg_color="transparent")
        if self.params_open:
            inner.pack(fill="x", padx=16, pady=(0, 14))
            self.app.build_params(inner, on_change=lambda: summary.configure(text=self.app.settings.summary()))

        def toggle():
            self.params_open = not self.params_open
            self.app.settings.set("params_open", self.params_open)
            if self.params_open:
                inner.pack(fill="x", padx=16, pady=(0, 14))
                if not inner.winfo_children():
                    self.app.build_params(inner, on_change=lambda: summary.configure(text=self.app.settings.summary()))
            else:
                inner.pack_forget()
            arrow.configure(image=t.ui_icon("chevron-down" if self.params_open else "chevron-right", "muted", 16))

        make_clickable(head, toggle)

    def start(self):
        conv = self.current_conv()
        if self.item is None or conv is None:
            return
        self.app.start_conversion([self.item], conv.dst)

    def start_all(self):
        if self.selected_dst:
            self.app.start_conversion(list(self.app.queue_panel.items), self.selected_dst, batch=True)

    def show_log(self, job):
        if self.log is None:
            self.log = LogView(self.log_holder, self.app)
            self.log.pack(fill="x")
        self.log.show_job(job)
