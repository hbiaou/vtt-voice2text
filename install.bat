@echo off
:: VTT-voice2text Installer
:: Run this once to set up the environment.

echo === VTT-voice2text Setup ===
echo.

cd /d "%~dp0"

echo Creating virtual environment...
python -m venv venv

echo Activating environment...
call venv\Scripts\activate

echo Installing dependencies (this may take a few minutes)...
pip install -r requirements.txt

echo.
echo === Setup Complete! ===
echo Run 'run.bat' to start the application.
pause

