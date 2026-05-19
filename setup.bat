@echo off
REM Options Greeks Calculator - Windows Setup Script

echo.
echo ================================================
echo   Options Greeks Calculator - Setup Script
echo ================================================
echo.

REM Check Python
echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    exit /b 1
)

python --version
echo.

REM Setup Backend
echo Setting up backend...
echo.

REM Create virtual environment
if not exist "backend\venv" (
    echo Creating virtual environment...
    cd backend
    python -m venv venv
    cd ..
) else (
    echo Virtual environment already exists
)

REM Activate virtual environment
call backend\venv\Scripts\activate.bat
if errorlevel 1 (
    echo Error: Could not activate virtual environment
    exit /b 1
)

echo Virtual environment activated
echo.

REM Install dependencies
echo Installing backend dependencies...
cd backend
python -m pip install --upgrade pip setuptools wheel > nul 2>&1
pip install -r requirements.txt > nul 2>&1
cd ..
echo Dependencies installed
echo.

REM Summary
echo.
echo ================================================
echo Setup Complete!
echo ================================================
echo.

echo Next steps:
echo.
echo 1. Start the Backend Server (Command Prompt 1):
echo    cd backend
echo    venv\Scripts\activate.bat
echo    python -m uvicorn app:app --host 0.0.0.0 --port 8000
echo.

echo 2. Start the Frontend Server (Command Prompt 2):
echo    cd frontend
echo    python -m http.server 8080
echo.

echo 3. Open in Browser:
echo    http://localhost:8080
echo.

echo 4. Run Tests (optional):
echo    cd backend
echo    pip install pytest
echo    pytest tests\ -v
echo.

echo For more information, see README.md and frontend\README.md
echo.

pause
