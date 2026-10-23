"""Упаковывает dist\\FileConverter в build\\payload\\payload.zip для установщика."""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dist" / "FileConverter"
OUT = ROOT / "build" / "payload" / "payload.zip"


def main():
    if not (SRC / "FileConverter.exe").exists():
        print("нет dist\\FileConverter, сначала соберите программу")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    files = [p for p in SRC.rglob("*") if p.is_file()]
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            z.write(p, p.relative_to(SRC).as_posix())
    print(f"файлов: {len(files)}, архив {OUT.stat().st_size // (1024 * 1024)} МБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
