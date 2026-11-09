@echo off
setlocal
cd /d "%~dp0"
echo =============================================
echo   Balaji Workforce - local demo setup
echo =============================================
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher not found. Install Python 3.10+ and try again.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -m venv .venv
  if errorlevel 1 goto fail
)
echo Installing requirements...
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto fail
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto fail
echo Initializing database...
.venv\Scripts\python.exe scripts\init_db.py
if errorlevel 1 goto fail
echo Adding fictional demo data...
.venv\Scripts\python.exe scripts\seed_demo.py
if errorlevel 1 goto fail
echo.
echo Opening Balaji Workforce at http://127.0.0.1:5000
.venv\Scripts\python.exe app.py
if errorlevel 1 goto fail
exit /b 0
:fail
echo.
echo Setup stopped because a command failed. Review the error above.
pause
exit /b 1
