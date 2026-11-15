@echo off
rem Baut EMUHUB.exe (Ordner dist\EMUHUB) - Python muss auf DIESEM Rechner installiert sein, bei den Nutzern nicht.
cd /d "%~dp0"
py -m pip install -r emu_launcher\requirements.txt pyinstaller || goto :fehler
py -m PyInstaller --noconfirm --clean --windowed --name EMUHUB --icon emu_launcher\assets\icon.ico emu_launcher\main.py || goto :fehler
xcopy /E /I /Y emu_launcher\assets dist\EMUHUB\assets >nul
echo.
echo Fertig: dist\EMUHUB\EMUHUB.exe  (den ganzen Ordner dist\EMUHUB als ZIP weitergeben)
pause
exit /b 0
:fehler
echo Fehler beim Bauen.
pause
exit /b 1
