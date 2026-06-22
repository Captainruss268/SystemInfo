@echo off
title SystemInfo Dashboard
chcp 65001 >nul

echo ========================================
echo   SystemInfo Dashboard - Quick Start
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed! Install Python 3.8+ from https://python.org
    pause
    exit /b 1
)
echo [OK] Python found

REM Check/Install Node.js
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Node.js not found. Installing via winget...
    winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install Node.js. Install manually from https://nodejs.org
        pause
        exit /b 1
    )
    echo [OK] Node.js installed
) else (
    echo [OK] Node.js found
)

REM Ensure node is on PATH for this session
set "PATH=C:\Program Files\nodejs;%PATH%"

echo.
echo [1/4] Installing backend dependencies...
cd backend
pip install -r requirements.txt >nul 2>&1
if %errorlevel% neq 0 (
    pip install -r requirements.txt
)
cd ..
echo [OK] Backend dependencies ready

echo [2/4] Starting backend server (port 5000)...
start "SystemInfo-Backend" cmd /c "cd /d backend && python app.py"
timeout /t 3 /nobreak >nul
echo [OK] Backend server started

echo [3/4] Installing frontend dependencies...
cd frontend
call npm install --legacy-peer-deps --ignore-scripts >nul 2>&1
if %errorlevel% neq 0 (
    call npm install --legacy-peer-deps --ignore-scripts
)
cd ..
echo [OK] Frontend dependencies ready

echo [4/4] Starting frontend server (port 3000)...
start "SystemInfo-Frontend" cmd /c "set PATH=C:\Program Files\nodejs;%%PATH%% && cd /d frontend && npm start"
timeout /t 5 /nobreak >nul

echo.
echo ========================================
echo   ✅ SystemInfo is running!
echo.
echo   Backend:  http://127.0.0.1:5000
echo   Frontend: http://localhost:3000
echo ========================================
echo.
start http://localhost:3000
echo Press any key to close this window (servers will keep running)...
pause >nul
exit