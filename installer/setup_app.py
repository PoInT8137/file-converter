"""Установщик и деинсталлятор File Converter.

С файлом payload.zip внутри сборки работает как установщик, без него как удаление.
"""
import base64
import ctypes
import os
import queue
import shutil
import subprocess
import sys
import threading
import winreg
import zipfile
from ctypes import wintypes
from pathlib import Path
from tkinter import filedialog

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import customtkinter as ctk

from fileconverter import __version__
from fileconverter.config import assets_dir, base_dir
from fileconverter.ui import theme as t
from fileconverter.ui.widgets import accent_button, checkbox, label, outline_button

APP = "File Converter"
EXE = "FileConverter.exe"
UNINSTALL_EXE = "uninstall.exe"
MANIFEST = "files.txt"
REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\FileConverter"
CREATE_NO_WINDOW = 0x08000000
STEPS_INSTALL = ["Начало", "Папка", "Установка", "Готово"]
STEPS_REMOVE = ["Начало", "Удаление", "Готово"]
MUTED_STEP = "#6E7A89"


def payload_path():
    p = base_dir() / "payload.zip"
    return p if p.exists() else None


def default_dir():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
            return Path(winreg.QueryValueEx(k, "InstallLocation")[0])
    except OSError:
        pass
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / APP


def registered_dir():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
            return Path(winreg.QueryValueEx(k, "InstallLocation")[0])
    except OSError:
        return None


def is_installed(folder):
    return (Path(folder) / MANIFEST).exists() and (Path(folder) / EXE).exists()


def special_folder(csidl):
    buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
    return Path(buf.value)


def shortcut_paths():
    return {
        "menu": special_folder(0x02) / f"{APP}.lnk",
        "desktop": special_folder(0x10) / f"{APP}.lnk",
        "sendto": special_folder(0x09) / f"{APP}.lnk",
    }


def run_powershell(script):
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                   creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL, capture_output=True, timeout=60)


def ps_quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def make_shortcuts(target_dir, names):
    exe = target_dir / EXE
    lines = ["$sh = New-Object -ComObject WScript.Shell"]
    for name in names:
        link = shortcut_paths()[name]
        lines += [
            f"$s = $sh.CreateShortcut({ps_quote(link)})",
            f"$s.TargetPath = {ps_quote(exe)}",
            f"$s.WorkingDirectory = {ps_quote(target_dir)}",
            f"$s.IconLocation = {ps_quote(str(exe) + ',0')}",
            "$s.Save()",
        ]
    run_powershell("\n".join(lines))


def register(target_dir, size_kb):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY) as k:
        values = {
            "DisplayName": APP, "DisplayVersion": __version__, "Publisher": APP,
            "InstallLocation": str(target_dir), "DisplayIcon": str(target_dir / EXE),
            "UninstallString": f'"{target_dir / UNINSTALL_EXE}"',
        }
        for name, value in values.items():
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, int(size_kb))
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)


def app_running():
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {EXE}", "/NH"], capture_output=True,
                             creationflags=CREATE_NO_WINDOW, timeout=15).stdout.decode("cp866", "replace")
        return EXE.lower() in out.lower()
    except Exception:
        return False


class Cancelled(Exception):
    pass


class Wizard(ctk.CTk):
    def __init__(self, mode):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=t.MAIN)
        t.load_fonts()
        self.mode = mode
        self.title(f"Установка {APP}" if mode == "install" else f"Удаление {APP}")
        self.geometry("640x428")
        self.resizable(False, False)
        try:
            self.iconbitmap(default=str(assets_dir() / "app.ico"))
        except Exception:
            pass
        self.events = queue.Queue()
        self.cancel_flag = threading.Event()
        self.busy = False
        self.final = False
        self.target = default_dir()
        self.result = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.side = ctk.CTkFrame(self, fg_color=t.BAR, corner_radius=0, width=150)
        self.side.grid(row=0, column=0, sticky="nsw")
        self.side.grid_propagate(False)
        ctk.CTkFrame(self, fg_color=t.BORDER, width=1, corner_radius=0).grid(row=0, column=0, sticky="nse")
        self.body = ctk.CTkFrame(self, fg_color=t.MAIN, corner_radius=0)
        self.body.grid(row=0, column=1, sticky="nsew", padx=28, pady=(24, 10))
        ctk.CTkFrame(self, fg_color=t.BORDER, height=1, corner_radius=0).grid(row=1, column=0, columnspan=2, sticky="ew")
        self.footer = ctk.CTkFrame(self, fg_color=t.MAIN, corner_radius=0, height=72)
        self.footer.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.footer.pack_propagate(False)

        self.steps = STEPS_INSTALL if mode == "install" else STEPS_REMOVE
        self.step_labels = []
        ctk.CTkFrame(self.side, fg_color=t.BAR, height=16, width=1).pack()
        for name in self.steps:
            row = ctk.CTkFrame(self.side, fg_color=t.BAR, corner_radius=0, height=36, width=150)
            row.pack(fill="x")
            row.pack_propagate(False)
            mark = ctk.CTkFrame(row, fg_color=t.BAR, corner_radius=0, width=2)
            mark.pack(side="left", fill="y")
            lbl = ctk.CTkLabel(row, text=name, font=t.font(13), text_color=MUTED_STEP, anchor="w")
            lbl.pack(side="left", padx=16)
            self.step_labels.append((mark, lbl))

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        if mode == "install":
            self.page_start()
        else:
            self.page_remove_start()
        self.after(60, self.poll)

    def set_step(self, index):
        for i, (mark, lbl) in enumerate(self.step_labels):
            if i == index:
                mark.configure(fg_color=t.ACCENT)
                lbl.configure(text_color=t.TEXT)
            else:
                mark.configure(fg_color=t.BAR)
                lbl.configure(text_color=t.MUTED if i < index else MUTED_STEP)

    def clear(self):
        for w in list(self.body.winfo_children()) + list(self.footer.winfo_children()):
            w.destroy()

    def buttons(self, primary=None, secondary=None):
        if primary:
            text, cmd = primary
            accent_button(self.footer, text, cmd, size=13, width=124).pack(side="right", padx=(8, 14), pady=14)
        if secondary:
            text, cmd = secondary
            outline_button(self.footer, text, cmd, size=13, width=104).pack(
                side="right", padx=(0, 0 if primary else 14), pady=14)

    def text(self, value, color=t.MUTED, size=13, pady=(0, 0)):
        lbl = label(self.body, value, size, color, wraplength=420, justify="left", anchor="w")
        lbl.pack(anchor="w", pady=pady)
        return lbl

    def heading(self, value):
        label(self.body, value, 17, weight="bold", anchor="w").pack(anchor="w", pady=(0, 10))

    def page_start(self):
        self.clear()
        self.set_step(0)
        self.heading(f"{APP} {__version__}")
        self.text("Программа будет установлена на этот компьютер. Для документов и презентаций "
                  "нужен LibreOffice, его можно поставить позже.")
        size = self.payload_size()
        if size:
            self.text(f"Нужно места: {size // (1024 * 1024)} МБ", pady=(14, 0))
        self.buttons(("Далее", self.page_folder), ("Отмена", self.on_close))

    def payload_size(self):
        p = payload_path()
        if not p:
            return 0
        with zipfile.ZipFile(p) as z:
            return sum(i.file_size for i in z.infolist())

    def page_folder(self, error=""):
        self.clear()
        self.set_step(1)
        self.text("Куда установить", t.TEXT, pady=(0, 6))
        row = ctk.CTkFrame(self.body, fg_color=t.MAIN)
        row.pack(fill="x")
        self.path_entry = ctk.CTkEntry(row, height=36, corner_radius=t.RADIUS, fg_color=t.BAR, border_width=1,
                                       border_color=t.BORDER_BTN, text_color=t.CAPTION, font=t.mono(11))
        self.path_entry.insert(0, str(self.target))
        self.path_entry.pack(side="left", fill="x", expand=True)
        outline_button(row, "...", self.browse, height=36, width=40).pack(side="left", padx=(6, 0))
        self.var_desktop = getattr(self, "var_desktop", None) or ctk.BooleanVar(value=True)
        self.var_sendto = getattr(self, "var_sendto", None) or ctk.BooleanVar(value=False)
        box = ctk.CTkFrame(self.body, fg_color=t.MAIN)
        box.pack(anchor="w", pady=(10, 0))
        checkbox(box, "Ярлык на рабочем столе", self.var_desktop).pack(anchor="w")
        checkbox(box, "Добавить в меню «Отправить»", self.var_sendto).pack(anchor="w")
        if error:
            self.text(error, t.ERROR, 12, pady=(6, 0))
        self.buttons(("Установить", self.start_install), ("Назад", self.page_start))

    def browse(self):
        path = filedialog.askdirectory(title="Куда установить File Converter", initialdir=str(self.target.parent))
        if path:
            path = Path(path)
            if path.name.lower() != APP.lower():
                path = path / APP
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, str(path))

    def start_install(self):
        target = Path(self.path_entry.get().strip().strip('"'))
        if not target.is_absolute():
            return self.page_folder("Укажите полный путь к папке, например C:\\Программы\\File Converter")
        need = self.payload_size()
        try:
            probe = target
            while not probe.exists():
                probe = probe.parent
            if shutil.disk_usage(probe).free < need + 50 * 1024 * 1024:
                return self.page_folder("На этом диске не хватает места. Выберите другой диск.")
        except OSError:
            return self.page_folder("Не удалось открыть этот путь. Выберите другую папку.")
        if app_running():
            return self.page_folder("File Converter сейчас запущен. Закройте его и нажмите «Установить».")
        self.target = target
        self.page_progress("Копирование файлов...")
        self.busy = True
        self.final = False
        self.cancel_flag.clear()
        threading.Thread(target=self.install_worker, args=(target, self.var_desktop.get(), self.var_sendto.get()),
                         daemon=True).start()

    def page_progress(self, title):
        self.clear()
        self.set_step(2 if self.mode == "install" else 1)
        self.text(title, t.TEXT, pady=(0, 10))
        self.bar = ctk.CTkProgressBar(self.body, height=6, corner_radius=3, fg_color=t.BORDER, progress_color=t.ACCENT)
        self.bar.set(0)
        self.bar.pack(fill="x")
        self.file_label = ctk.CTkLabel(self.body, text="", font=t.mono(11), text_color=t.MUTED, anchor="w")
        self.file_label.pack(anchor="w", fill="x", pady=(8, 0))
        self.cancel_button = None
        if self.mode == "install":
            self.cancel_button = outline_button(self.footer, "Отмена", self.ask_cancel, size=13, width=104)
            self.cancel_button.pack(side="right", padx=14, pady=14)

    def install_worker(self, target, desktop, sendto):
        # сначала распаковываем во временную папку рядом: отмена или ошибка не портят уже установленную программу
        stage = target.parent / f".{target.name}.new"
        made = [d for d in [target.parent, *target.parent.parents] if not d.exists()]
        try:
            shutil.rmtree(stage, ignore_errors=True)
            stage.mkdir(parents=True)
            with zipfile.ZipFile(payload_path()) as z:
                infos = [i for i in z.infolist() if not i.is_dir()]
                total = sum(i.file_size for i in infos) or 1
                done = 0
                for info in infos:
                    if self.cancel_flag.is_set():
                        raise Cancelled()
                    self.events.put(("file", info.filename.replace("/", "\\")))
                    dest = stage / info.filename
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(info) as src, open(dest, "wb") as out:
                        while True:
                            chunk = src.read(1024 * 1024)
                            if not chunk:
                                break
                            out.write(chunk)
                            done += len(chunk)
                            self.events.put(("progress", done / total * 0.9))
                            if self.cancel_flag.is_set():
                                raise Cancelled()
            uninstaller = base_dir() / UNINSTALL_EXE
            if uninstaller.exists():
                shutil.copy2(uninstaller, stage / UNINSTALL_EXE)
            names = [i.filename.replace("/", "\\") for i in infos]

            # дальше отменить нельзя: файлы переносятся на место за секунды
            self.events.put(("final", None))
            old_manifest = target / MANIFEST
            old_names = old_manifest.read_text(encoding="utf-8").splitlines() if old_manifest.exists() else []
            target.mkdir(parents=True, exist_ok=True)
            for name in names + [UNINSTALL_EXE]:
                src = stage / name
                if src.exists():
                    dest = target / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(src, dest)
            for name in set(old_names) - set(names):
                try:
                    (target / name).unlink()
                except OSError:
                    pass
            (target / MANIFEST).write_text("\n".join(names), encoding="utf-8")
            shutil.rmtree(stage, ignore_errors=True)

            self.events.put(("file", "Ярлыки"))
            links = shortcut_paths()
            for name in ("desktop", "sendto"):
                if not {"desktop": desktop, "sendto": sendto}[name] and links[name].exists():
                    links[name].unlink()
            make_shortcuts(target, ["menu"] + (["desktop"] if desktop else []) + (["sendto"] if sendto else []))
            register(target, total // 1024)
            self.events.put(("progress", 1.0))
            self.events.put(("done", None))
        except Cancelled:
            self.cleanup_stage(stage, made)
            self.events.put(("cancelled", None))
        except PermissionError:
            self.cleanup_stage(stage, made)
            self.events.put(("error", "Нет прав на запись в эту папку. Выберите папку в профиле пользователя, "
                                      "например в AppData\\Local\\Programs."))
        except OSError as e:
            self.cleanup_stage(stage, made)
            self.events.put(("error", f"Не удалось скопировать файлы: {e.strerror or e}"))

    @staticmethod
    def cleanup_stage(stage, made):
        shutil.rmtree(stage, ignore_errors=True)
        for d in made:
            try:
                d.rmdir()
            except OSError:
                pass

    def ask_cancel(self):
        if self.busy and self.mode == "install" and not self.final:
            self.cancel_flag.set()
            self.file_label.configure(text="Отмена...")

    def page_done(self):
        self.clear()
        self.set_step(3)
        self.heading("Установка завершена")
        self.text(f"{APP} установлен. Удалить его можно в Параметрах Windows, раздел «Приложения».")
        self.var_run = ctk.BooleanVar(value=True)
        box = ctk.CTkFrame(self.body, fg_color=t.MAIN)
        box.pack(anchor="w", pady=(10, 0))
        checkbox(box, f"Запустить {APP}", self.var_run).pack(anchor="w")
        self.buttons(("Готово", self.finish))

    def finish(self):
        if self.mode == "install" and self.var_run.get():
            try:
                subprocess.Popen([str(self.target / EXE)], cwd=str(self.target))
            except OSError:
                pass
        self.result = "done"
        self.destroy()

    def page_error(self, message):
        self.clear()
        self.heading("Не получилось")
        self.text(message, t.ERROR)
        if self.mode == "install":
            self.buttons(("Назад", self.page_folder), ("Закрыть", self.destroy))
        else:
            self.buttons(("Закрыть", self.destroy))

    def page_remove_start(self):
        self.clear()
        self.set_step(0)
        self.target = Path(sys.executable).parent if getattr(sys, "frozen", False) else default_dir()
        self.heading(f"Удаление {APP}")
        if not is_installed(self.target):
            # деинсталлятор лежит не в папке установленной программы: ничего не трогаем
            self.text("В этой папке нет установленного File Converter. Удалите программу через "
                      "Параметры Windows, раздел «Приложения».", t.ERROR)
            self.buttons(("Закрыть", self.destroy))
            return
        self.text("Программа будет удалена из папки:")
        ctk.CTkLabel(self.body, text=str(self.target), font=t.mono(11), text_color=t.CAPTION, anchor="w",
                     wraplength=420, justify="left").pack(anchor="w", pady=(4, 0))
        self.var_data = ctk.BooleanVar(value=False)
        box = ctk.CTkFrame(self.body, fg_color=t.MAIN)
        box.pack(anchor="w", pady=(12, 0))
        checkbox(box, "Удалить также настройки и историю", self.var_data).pack(anchor="w")
        self.buttons(("Удалить", self.start_remove), ("Отмена", self.on_close))

    def start_remove(self):
        if app_running():
            self.text("File Converter сейчас запущен. Закройте его и нажмите «Удалить».", t.ERROR, 12, pady=(8, 0))
            return
        self.page_progress("Удаление файлов...")
        self.busy = True
        threading.Thread(target=self.remove_worker, args=(self.target, self.var_data.get()), daemon=True).start()

    def remove_worker(self, target, with_data):
        try:
            if not is_installed(target):
                raise OSError("в папке нет установленной программы")
            # ярлыки и запись в реестре трогаем, только если они относятся к этой папке
            if registered_dir() in (None, target):
                for link in shortcut_paths().values():
                    try:
                        link.unlink()
                    except OSError:
                        pass
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY)
                except OSError:
                    pass
            if with_data:
                shutil.rmtree(Path(os.environ.get("APPDATA", "")) / "FileConverter", ignore_errors=True)
            manifest = target / MANIFEST
            names = manifest.read_text(encoding="utf-8").splitlines() if manifest.exists() else []
            for i, name in enumerate(names):
                p = target / name
                self.events.put(("file", name))
                try:
                    p.unlink()
                except OSError:
                    pass
                self.events.put(("progress", (i + 1) / max(len(names), 1)))
            # пустые папки снизу вверх, чужие файлы остаются на месте
            for d in sorted({(target / n).parent for n in names}, key=lambda x: len(x.parts), reverse=True):
                while d != target and target in d.parents:
                    try:
                        d.rmdir()
                    except OSError:
                        break
                    d = d.parent
            try:
                manifest.unlink()
            except OSError:
                pass
            self.events.put(("removed", None))
        except OSError as e:
            self.events.put(("error", f"Не удалось удалить файлы: {e.strerror or e}"))

    def page_removed(self):
        self.clear()
        self.set_step(2)
        self.heading("Удаление завершено")
        self.text(f"{APP} удалён с компьютера.")
        self.buttons(("Готово", self.finish_remove))

    def finish_remove(self):
        # сам деинсталлятор и пустую папку удаляет cmd уже после закрытия окна
        me = Path(sys.executable)
        if getattr(sys, "frozen", False) and me.name.lower() == UNINSTALL_EXE:
            subprocess.Popen(f'cmd /c ping 127.0.0.1 -n 3 >nul & del /f /q "{me}" & rmdir "{self.target}"',
                             creationflags=CREATE_NO_WINDOW, cwd=os.environ.get("TEMP", "C:\\"))
        self.result = "done"
        self.destroy()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "final":
                    self.final = True
                    if self.cancel_button is not None:
                        self.cancel_button.configure(state="disabled")
                elif kind == "file":
                    self.file_label.configure(text=value)
                elif kind == "progress":
                    self.bar.set(value)
                elif kind == "done":
                    self.busy = False
                    self.page_done()
                elif kind == "removed":
                    self.busy = False
                    self.page_removed()
                elif kind == "cancelled":
                    self.busy = False
                    self.page_folder("Установка отменена.")
                elif kind == "error":
                    self.busy = False
                    self.page_error(value)
        except queue.Empty:
            pass
        except Exception:
            pass
        try:
            self.after(60, self.poll)
        except Exception:
            pass

    def on_close(self):
        if self.busy:
            # во время удаления и последнего шага установки окно не закрывается, отмена там невозможна
            self.ask_cancel()
            return
        self.destroy()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    mode = "install" if payload_path() else "remove"
    if "--uninstall" in sys.argv:
        mode = "remove"
    Wizard(mode).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
