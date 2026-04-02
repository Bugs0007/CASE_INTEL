@echo off
REM ============================================================================
REM Case Intel - Development Server Startup Script (Windows)
REM ============================================================================
REM This script starts all required services for local development
REM 
REM Prerequisites:
REM   1. Redis installed (redis-server)
REM   2. PostgreSQL running with case_intel database
REM   3. Python virtual environment activated
REM   4. Ollama installed (if USE_OLLAMA=true)
REM ============================================================================

echo.
echo ========================================
echo   Case Intel - Starting Services
echo ========================================
echo.

REM Check if Redis is installed
echo [1/5] Checking Redis installation...
where redis-server >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo   Redis Not Found!
    echo ========================================
    echo.
    echo Redis is required for background tasks.
    echo.
    echo To install Redis (ONE TIME ONLY^):
    echo   1. Right-click PowerShell
    echo   2. Select "Run as Administrator"  
    echo   3. Run: .\setup_redis.ps1
    echo.
    echo OR download manually from:
    echo   https://github.com/tporadowski/redis/releases
    echo.
    pause
    exit /b 1
)
echo [OK] Redis is installed

REM Check if Redis is running
echo [2/5] Checking if Redis is running...
redis-cli ping >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Redis is not running. Starting Redis...
    start "Redis Server" cmd /k "redis-server --port 6379"
    timeout /t 3 /nobreak >nul
    
    REM Verify Redis started
    redis-cli ping >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Redis failed to start!
        echo Please start Redis manually: redis-server
        pause
        exit /b 1
    )
    echo [OK] Redis started
) else (
    echo [OK] Redis is running
)

REM Check if PostgreSQL is accessible
echo [3/5] Checking PostgreSQL...
echo [OK] Skipping PostgreSQL check - assuming it's running

REM Activate virtual environment
echo [4/5] Activating virtual environment...
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
echo [5/5] Checking Python dependencies...
python -c "import celery" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Celery not installed!
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
echo You will see 3 new terminal windows:
echo   1. Django Backend (port 8000^)
echo   2. Celery Worker (background tasks^)
echo   3. Next.js Frontend (port 3000^)
echo.
echo Close this window to stop all services
echo ========================================
echo.

REM Start Django in new window
start "Django Backend" cmd /k "call .venv\Scripts\activate.bat && python manage.py runserver 8000"
timeout /t 2 /nobreak >nul

REM Start Celery in new window
start "Celery Worker" cmd /k "call .venv\Scripts\activate.bat && celery -A case_intel_project worker --loglevel=info --pool=solo"
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
