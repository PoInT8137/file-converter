"""Скачивает портативные FFmpeg и Pandoc в папку engines.

Запуск: .venv\\Scripts\\python.exe tools\\get_engines.py
"""
import io
import json
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINES = ROOT / "engines"
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
PANDOC_API = "https://api.github.com/repos/jgm/pandoc/releases/latest"


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "FileConverter/1.0"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read()


def extract(data, names):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            name = Path(info.filename).name
            if name in names:
                (ENGINES / name).write_bytes(z.read(info))
                print("распакован", name)


def main():
    ENGINES.mkdir(exist_ok=True)
    if not (ENGINES / "ffmpeg.exe").exists():
        print("скачиваю FFmpeg...")
        extract(download(FFMPEG_URL), {"ffmpeg.exe", "ffprobe.exe"})
    if not (ENGINES / "pandoc.exe").exists():
        release = json.loads(download(PANDOC_API))
        url = next(a["browser_download_url"] for a in release["assets"]
                   if a["name"].endswith("windows-x86_64.zip"))
        print("скачиваю", url)
        extract(download(url), {"pandoc.exe"})


if __name__ == "__main__":
    main()
