import customtkinter as ctk

from ..engines.finder import ENGINE_TITLES
from ..tools import SECTION_TITLES, section_tools
from . import theme as t
from .convert_page import LogView
from .widgets import (Flow, Popover, ResponsiveGrid, accent_button, caption, holder, label, make_clickable,
                      mono_label, on_event, outline_button)

SECTION_ICONS = {"pdf": "file-text", "images": "image", "media": "clapperboard", "ocr": "scan-text"}


class ToolsPage(ctk.CTkFrame):
    """Раздел инструментов: карточки прокручиваются, панель действия всегда видна внизу."""

    def __init__(self, parent, app, section):
        super().__init__(parent, fg_color=t.MAIN, corner_radius=0)
        self.app = app
        self.section = section
        self.tools = section_tools(section)
        self.selected = self.tools[0]
        self.cards = {}
        self.log = None
        self.painted = None
        self.chips_for = None

        self.action = ctk.CTkFrame(self, fg_color=t.BAR, corner_radius=0)
        self.action.pack(side="bottom", fill="x")
        ctk.CTkFrame(self, fg_color=t.BORDER, height=1, width=1, corner_radius=0).pack(side="bottom", fill="x")
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=t.MAIN, corner_radius=0, scrollbar_button_color=t.BORDER,
                                             scrollbar_button_hover_color=t.BORDER_BTN)
        self.scroll.pack(side="top", fill="both", expand=True)

        b = ctk.CTkFrame(self.scroll, fg_color=t.MAIN)
        b.pack(fill="both", expand=True, padx=28, pady=22)
        label(b, SECTION_TITLES[section], 22, weight="bold").pack(anchor="w")
        label(b, "Работают с файлами, выбранными в очереди. Ctrl + клик выбирает несколько файлов.",
              13, t.MUTED, wraplength=440, justify="left").pack(anchor="w", pady=(2, 12))
        if section == "ocr" and not app.engines.available("tesseract"):
            warn = ctk.CTkFrame(b, fg_color=t.CARD, corner_radius=t.RADIUS, border_width=1, border_color=t.ERROR)
            warn.pack(fill="x", pady=(0, 12))
            label(warn, "Tesseract не найден, распознавание недоступно. Установите Tesseract OCR с языками rus и eng "
                        "и нажмите «Найти заново» в настройках.", 12, wraplength=600, justify="left").pack(
                anchor="w", padx=14, pady=10)
        self.chips = holder(b, t.MAIN)
        self.chips.pack(fill="x", pady=(0, 6))

        groups = []
        for tool in self.tools:
            if tool.group not in groups:
                groups.append(tool.group)
        for g in groups:
            caption(b, g).pack(anchor="w", pady=(16, 8))
            grid = ResponsiveGrid(b, min_width=210, max_cols=3)
            grid.pack(fill="x")
            for tool in self.tools:
                if tool.group == g:
                    grid.add(self.tool_card(grid, tool))

        self.run_btn = accent_button(self.action, "Выполнить", self.run, width=150)
        self.run_btn.pack(side="right", padx=(10, 28), pady=10)
        text_box = ctk.CTkFrame(self.action, fg_color=t.BAR, corner_radius=0)
        text_box.pack(side="left", fill="x", expand=True, padx=(28, 0), pady=8)
        self.action_text = label(text_box, "", 14, weight="bold", anchor="w", justify="left")
        self.action_text.pack(anchor="w")
        self.action_hint = mono_label(text_box, "", 11, anchor="w")
        self.action_hint.pack(anchor="w")
        self.log_holder = holder(b, t.MAIN)
        self.log_holder.pack(fill="x", pady=(14, 0))
        self.refresh()

    def tool_card(self, parent, tool):
        ok = self.app.engines.available(tool.engine)
        card = ctk.CTkFrame(parent, fg_color=t.CARD, corner_radius=t.RADIUS, border_width=1, border_color=t.BORDER,
                            height=72)
        card.grid_columnconfigure(1, weight=1)
        box = ctk.CTkFrame(card, fg_color=t.CARD, corner_radius=t.RADIUS, border_width=1,
                           border_color=t.BORDER_BTN, width=44, height=44)
        box.grid(row=0, column=0, rowspan=2, padx=12, pady=12)
        box.grid_propagate(False)
        icon = ctk.CTkLabel(box, text="", image=t.ui_icon(tool.icon, "muted", 20))
        icon.place(relx=0.5, rely=0.5, anchor="center")
        title = label(card, tool.title, 13, t.TEXT if ok else t.MUTED, "bold", anchor="w", justify="left",
                      wraplength=180)
        title.grid(row=0, column=1, sticky="sw", pady=(12, 0), padx=(0, 8))
        desc = tool.desc if ok else f"Нужен {ENGINE_TITLES.get(tool.engine, tool.engine)}"
        desc_label = label(card, desc, 11, t.MUTED, anchor="w", wraplength=180, justify="left")
        desc_label.grid(row=1, column=1, sticky="nw", pady=(0, 12), padx=(0, 8))

        def rewrap(event):
            # перенос по ширине карточки, иначе в узком окне текст обрезается справа
            scale = ctk.ScalingTracker.get_widget_scaling(card)
            width = max(80, int(event.width / scale) - 84)
            for lbl in (title, desc_label):
                if lbl.cget("wraplength") != width:
                    lbl.configure(wraplength=width)

        card.bind("<Configure>", on_event(rewrap), add="+")
        card.icon = icon
        card.box = box
        self.cards[tool.id] = card

        def hover(on):
            if tool is not self.selected:
                card.configure(fg_color=t.CARD_SEL if on else t.CARD)
                box.configure(fg_color=t.CARD_SEL if on else t.CARD)

        make_clickable(card, lambda: self.select(tool), lambda: hover(True), lambda: hover(False))
        return card

    def select(self, tool):
        self.selected = tool
        self.refresh()

    def files(self):
        return [i for i in self.app.queue_panel.selected if self.selected.accepts(i.path)]

    def refresh(self):
        # перекрашиваются только карточки, у которых изменился выбор: перекраска всех занимала до 150 мс
        if self.painted != self.selected.id:
            for tid in (self.painted, self.selected.id):
                card = self.cards.get(tid)
                if card is None:
                    continue
                on = tid == self.selected.id
                card.configure(border_color=t.ACCENT if on else t.BORDER, fg_color=t.CARD_SEL if on else t.CARD)
                card.box.configure(fg_color=t.CARD_SEL if on else t.CARD,
                                   border_color=t.ACCENT if on else t.BORDER_BTN)
                tool = next(x for x in self.tools if x.id == tid)
                card.icon.configure(image=t.ui_icon(tool.icon, "accent" if on else "muted", 20))
            self.painted = self.selected.id
        selected = self.app.queue_panel.selected
        accepted = [i for i in selected if any(tool.accepts(i.path) for tool in self.tools)]
        chips_for = tuple(id(i) for i in accepted)
        if chips_for != self.chips_for:
            self.chips_for = chips_for
            self.show_chips(accepted)
        self.update_action()

    def show_chips(self, accepted):
        for w in self.chips.winfo_children():
            w.destroy()
        if not accepted:
            row = ctk.CTkFrame(self.chips, fg_color=t.MAIN)
            row.pack(fill="x")
            mono_label(row, "Файлы не выбраны. Выберите их в очереди слева или добавьте новые.", 12).pack(side="left")
            outline_button(row, "Добавить файлы", self.app.pick_files, width=150, size=12).pack(side="right")
        else:
            row = Flow(self.chips)
            row.pack(fill="x")
            for i in accepted[:6]:
                chip = ctk.CTkFrame(row, fg_color=t.CARD, corner_radius=t.RADIUS, border_width=1,
                                    border_color=t.BORDER_BTN, width=1, height=1)
                row.add(chip)
                ctk.CTkLabel(chip, text="", image=t.get_icon(i.ext, 18)).pack(side="left", padx=(8, 4), pady=6)
                name = i.path.name if len(i.path.name) < 24 else i.path.name[:20] + "..."
                label(chip, name, 12).pack(side="left", padx=(0, 10))
            if len(accepted) > 6:
                row.add(mono_label(row, f"+{len(accepted) - 6}", 12))

    def update_action(self):
        files = self.files()
        tool = self.selected
        self.action_text.configure(text=tool.action_text(len(files)))
        hint = ""
        if not self.app.engines.available(tool.engine):
            hint = f"нет движка {ENGINE_TITLES.get(tool.engine, tool.engine)}"
        elif len(files) < tool.min_files:
            hint = f"нужно файлов: {tool.min_files}" if tool.min_files > 1 else "выберите файл"
        self.action_hint.configure(text=hint, text_color=t.ERROR if hint.startswith("нет") else t.MUTED)
        self.run_btn.configure(text=tool.verb or "Выполнить",
                               state="normal" if not hint else "disabled",
                               fg_color=t.ACCENT if not hint else t.BORDER)

    def run(self):
        files = self.files()
        tool = self.selected
        if len(files) < tool.min_files or not self.app.engines.available(tool.engine):
            Popover(self.run_btn, "Выберите подходящие файлы в очереди", below=False)
            return
        self.app.run_tool(tool, files)

    def show_log(self, job):
        if self.log is None:
            self.log = LogView(self.log_holder, self.app)
            self.log.pack(fill="x")
        self.log.show_job(job)
