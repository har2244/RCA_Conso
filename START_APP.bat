@echo off
setlocal
cd /d "%~dp0"

if not exist "app.py" (
    echo ERROR: app.py was not found in "%~dp0".
    echo Make sure this batch file is in the RCA Data Consolidation project root.
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_COMMAND=.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python was not found in PATH.
        echo Install Python or create a .venv virtual environment in "%~dp0".
        pause
        exit /b 1
    )
    set "PYTHON_COMMAND=python"
)

echo Starting RCA Data Consolidation...
echo Local application URL: http://localhost:8501
echo Press Ctrl+C to stop the application.
echo.

"%PYTHON_COMMAND%" -m streamlit run app.py --server.address localhost --server.port 8501
if errorlevel 1 (
    echo.
    echo ERROR: The application failed to start or stopped with an error.
    pause
)

exit /b
