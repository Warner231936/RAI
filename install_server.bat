@echo off
python -m venv venv
venv\Scripts\python -m pip install flask PyYAML
echo.
echo Server setup complete. Run with run_server.bat
pause
