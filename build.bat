@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение...
    py -3.12 -m venv .venv || python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)
if not exist "engines\ffmpeg.exe" .venv\Scripts\python.exe tools\get_engines.py
if not exist "engines\pandoc.exe" .venv\Scripts\python.exe tools\get_engines.py

echo Сборка папки dist\FileConverter...
set FC_ONEFILE=
.venv\Scripts\pyinstaller.exe --noconfirm --clean FileConverter.spec || goto error
if not exist "dist\FileConverter\engines" mkdir "dist\FileConverter\engines"
copy /y engines\*.exe "dist\FileConverter\engines\" >nul

echo Сборка одиночного файла dist\FileConverter_onefile...
set FC_ONEFILE=1
.venv\Scripts\pyinstaller.exe --noconfirm --distpath dist\onefile_tmp FileConverter.spec || goto error
set FC_ONEFILE=
if not exist "dist\FileConverter_onefile" mkdir "dist\FileConverter_onefile"
move /y dist\onefile_tmp\FileConverter.exe dist\FileConverter_onefile\FileConverter.exe >nul
rmdir /s /q dist\onefile_tmp
if not exist "dist\FileConverter_onefile\engines" mkdir "dist\FileConverter_onefile\engines"
copy /y engines\*.exe "dist\FileConverter_onefile\engines\" >nul

echo Проверка сборки...
start /wait "" "dist\FileConverter\FileConverter.exe" --selftest
if errorlevel 1 goto error
echo Готово: dist\FileConverter\FileConverter.exe
exit /b 0

:error
echo Сборка или проверка завершилась с ошибкой
exit /b 1
