@echo off
REM ============================================================================
REM Case Intel - Development Server Startup Script (Windows)
REM ============================================================================
REM This script starts all required services for local development
REM
REM Prerequisites:
REM   1. PostgreSQL running with case_intel database
REM   2. Python virtual environment activated
REM   3. Ollama installed (if USE_OLLAMA=true)
REM
REM NOTE: Redis and Celery are NOT started here. Verified 2026-07-16 that
REM Celery has zero real task dispatch anywhere in this codebase (no
REM .delay(/.apply_async(/@shared_task calls), and the default cache backend
REM is now LocMemCache (see case_intel_project/settings.py) -- neither is
REM needed to run this app. See REDIS_SETUP.md for the same finding.
REM ============================================================================

echo.
echo ========================================
echo   Case Intel - Starting Services
echo ========================================
echo.

REM Check if PostgreSQL is accessible
echo [1/3] Checking PostgreSQL...
echo [OK] Skipping PostgreSQL check - assuming it's running

REM Activate virtual environment
echo [2/3] Activating virtual environment...
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
    echo [OK] Virtual environment activated
) else (
    echo [ERROR] Virtual environment not found at .venv\Scripts\activate.bat
    echo Please create it first: python -m venv .venv
    pause
    exit /b 1
)

REM Check if dependencies are installed
echo [3/3] Checking Python dependencies...
python -c "import django" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Dependencies not installed!
    echo Please install dependencies: pip install -r requirements.txt
    pause
    exit /b 1
) else (
    echo [OK] Dependencies installed
)

echo.
echo ========================================
echo   Starting services...
echo ========================================
echo.
echo You will see 2 new terminal windows:
echo   1. Django Backend (port 8000^)
echo   2. Next.js Frontend (port 3000^)
echo.
echo Close this window to stop all services
echo ========================================
echo.

REM Start Django in new window
start "Django Backend" cmd /k "call .venv\Scripts\activate.bat && python manage.py runserver 8000"
timeout /t 2 /nobreak >nul

REM Start Next.js Frontend in new window
start "Next.js Frontend" cmd /k "cd frontend-next && npm run dev"
timeout /t 2 /nobreak >nul

echo.
echo ========================================
echo   All services started!
echo ========================================
echo.
echo Open your browser to: http://localhost:3000
echo.
echo To stop all services:
echo   1. Close all terminal windows, OR
echo   2. Press Ctrl+C in each window
echo.
echo Press any key to exit this launcher...
pause >nul
