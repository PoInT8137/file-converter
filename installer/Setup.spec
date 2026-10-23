# Сборка установщика. Сначала нужны dist\FileConverter и build\payload\payload.zip.
# FC_UNINSTALL=1 собирает uninstall.exe без архива программы внутри.
import os

from PyInstaller.utils.hooks import collect_data_files

uninstall = os.environ.get("FC_UNINSTALL") == "1"
root = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [(os.path.join(root, "assets"), "assets")]
datas += collect_data_files("customtkinter")
if not uninstall:
    datas += [(os.path.join(root, "build", "payload", "payload.zip"), "."),
              (os.path.join(root, "build", "payload", "uninstall.exe"), ".")]

a = Analysis(
    [os.path.join(SPECPATH, "setup_app.py")],
    pathex=[os.path.join(root, "src")],
    datas=datas,
    excludes=["pymupdf", "fitz", "pdf2docx", "numpy", "cv2", "pptx", "docx", "openpyxl", "pillow_heif",
              "tkinterdnd2", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="uninstall" if uninstall else f"FileConverter_Setup_1.0.0",
    icon=os.path.join(root, "assets", "app.ico"),
    version=os.path.join(SPECPATH, "setup_version.txt"),
    console=False,
    upx=False,
)
