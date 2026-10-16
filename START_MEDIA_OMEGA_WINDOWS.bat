@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -c "import tkinter; import media_omega.desktop" >nul 2>nul
    if not errorlevel 1 goto launch_py
)
where python >nul 2>nul
if errorlevel 1 goto missing_python
python -c "import tkinter; import media_omega.desktop" >nul 2>nul
if errorlevel 1 goto missing_package
python -m media_omega.desktop
if errorlevel 1 goto launch_failed
exit /b 0

:launch_py
py -3 -m media_omega.desktop
if errorlevel 1 goto launch_failed
exit /b 0

:missing_python
echo Python 3 is not available. Install Python 3.11+ with Tkinter.
pause
exit /b 1

:missing_package
echo MEDIA Omega or Tkinter is not installed for the selected Python.
echo From this project folder run: python -m pip install -e .
pause
exit /b 1

:launch_failed
echo MEDIA Omega desktop could not start. Check dependencies and console errors above.
pause
exit /b 1
