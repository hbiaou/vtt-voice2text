@echo off
:: VTT-voice2text Launcher
:: Double-click this file to start the application.

cd /d "%~dp0"
call venv\Scripts\activate
python main.py
pause

