@echo off
python -m venv venv
venv\Scripts\python -m pip install requests PyYAML
echo.
echo Client setup complete. Run with run_client.bat
pause
