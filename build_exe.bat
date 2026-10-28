@echo off
rem Локальная сборка (нужен Python 3.12 для Windows). Результат: dist\MediaPanel.exe
py -3.12 -m pip install -r requirements.txt pyinstaller || goto :err
py -3.12 -m PyInstaller --noconfirm --clean --onefile --windowed --name MediaPanel --icon assets\icon.ico ^
 --collect-submodules winrt --collect-binaries winrt --collect-data winrt ^
 --hidden-import winrt.windows.media.control --hidden-import winrt.windows.storage.streams ^
 --hidden-import winrt.windows.foundation --hidden-import winrt.windows.foundation.collections ^
 --exclude-module tkinter main.py || goto :err
echo Готово: dist\MediaPanel.exe
goto :eof
:err
echo Сборка не удалась
exit /b 1
