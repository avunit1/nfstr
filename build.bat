@echo off
REM build.bat -- builds dist\NFSTR-ModMenu.exe
REM Run this from the project root on Windows, with Python installed.

setlocal

echo Installing build requirements...
python -m pip install -r requirements.txt --quiet
python -m pip install pyinstaller --quiet
if errorlevel 1 goto :error

echo Building NFSTR-ModMenu.exe ...
python -m PyInstaller nfstr_modmenu.spec --noconfirm
if errorlevel 1 goto :error

echo.
echo Done. Your exe is at: dist\NFSTR-ModMenu.exe
echo Copy it anywhere -- it manages its own "nfstr_data" folder next to itself.
goto :eof

:error
echo.
echo Build failed -- see the output above.
exit /b 1
