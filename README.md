# File Converter

Конвертер файлов для Windows 10 и 11. Перетаскиваете файл в окно, выбираете формат, результат появляется рядом с исходным файлом. Сама программа ничего не конвертирует, она вызывает готовые движки: LibreOffice, PyMuPDF, pdf2docx, Pillow, FFmpeg, Pandoc и Tesseract.

Что умеет:
- документы, таблицы и презентации через LibreOffice (DOCX, DOC, ODT, RTF, TXT, XLSX, XLS, ODS, CSV, PPTX, PPT, ODP в PDF и между собой);
- PDF в DOCX, TXT, HTML, PNG, JPG, PPTX и XLSX;
- картинки PNG, JPG, WEBP, BMP, GIF, TIFF, ICO, HEIC между собой и в PDF;
- аудио и видео через FFmpeg, в том числе видео в MP3 и в GIF;
- MD, HTML, DOCX, ODT, EPUB, RTF, TXT через Pandoc;
- инструменты PDF (объединить, разделить, повернуть, сжать, пароль, водяной знак и другие), картинок и видео;
- распознавание текста через Tesseract, если он установлен.

## Запуск из исходников

Нужен Python 3.12.

```
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python tools\get_engines.py
run.bat
```

`tools\get_engines.py` скачивает FFmpeg и Pandoc в папку `engines`. LibreOffice и Tesseract ставятся отдельно обычными установщиками, программа находит их сама.

## Сборка

```
build.bat
```

Результат: установщик `dist\FileConverter_Setup_1.0.0.exe`, программа без установки `dist\FileConverter\FileConverter.exe` и вариант одним файлом `dist\FileConverter_onefile\FileConverter.exe` (папку `engines` нужно держать рядом).

Установщик ставит программу для текущего пользователя в `%LOCALAPPDATA%\Programs\File Converter`, права администратора не нужны. Он создаёт ярлык в меню Пуск, по желанию ярлык на рабочем столе и пункт в меню «Отправить». Удаление через Параметры Windows, раздел «Приложения». Удаляются только файлы, которые ставил установщик. Проверка собранной программы: `FileConverter.exe --selftest`, код возврата 0 значит всё в порядке. Отчёт пишется в `%APPDATA%\FileConverter\selftest.log`.

## Тесты

```
.venv\Scripts\python -m pytest tests
```

## Данные

Настройки, статистика, история и профиль LibreOffice лежат в `%APPDATA%\FileConverter`.

## Иконки и шрифты

Шрифты IBM Plex (лицензия OFL) из репозитория google/fonts. Иконки форматов из набора vscode-icons, иконки интерфейса из Lucide (ISC). Значки приложений Microsoft и Adobe принадлежат их владельцам, при публикации проекта их нужно заменить на нейтральные.
