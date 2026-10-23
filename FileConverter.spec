# Сборка: build.bat или pyinstaller FileConverter.spec
# Для одиночного exe: set FC_ONEFILE=1 перед запуском
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files

onefile = os.environ.get("FC_ONEFILE") == "1"

datas = [("assets", "assets")]
binaries = []
hiddenimports = ["pillow_heif", "pptx", "docx", "openpyxl"]
for pkg in ("tkinterdnd2", "pillow_heif"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
datas += collect_data_files("customtkinter")
datas += collect_data_files("pptx")
datas += collect_data_files("docx")

a = Analysis(
    ["run_app.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["matplotlib", "pytest", "IPython", "pandas", "scipy"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe_args = dict(
    name="FileConverter",
    icon="assets/app.ico",
    version="version_info.txt",
    console=False,
    upx=False,
    debug=False,
)

if onefile:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **exe_args)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_args)
    coll = COLLECT(exe, a.binaries, a.datas, name="FileConverter", upx=False)
