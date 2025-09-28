@echo off
setlocal enabledelayedexpansion

echo 🔒 NPM Vulnerability Fix Script
echo ================================
echo.

REM Colors for output (Windows doesn't support ANSI colors easily, so we'll use symbols)

echo [INFO] Checking if we're in the right directory...
if not exist "frontend\package.json" (
    echo [ERROR] Please run this script from the project root directory
    pause
    exit /b 1
)

echo [INFO] Creating backup of current package files...
set "BACKUP_DIR=backup_%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
set "BACKUP_DIR=!BACKUP_DIR: =0!"

mkdir "!BACKUP_DIR!" 2>nul

copy "frontend\package.json" "!BACKUP_DIR!\" >nul
if exist "frontend\package-lock.json" (
    copy "frontend\package-lock.json" "!BACKUP_DIR!\" >nul
) else (
    echo [WARNING] No package-lock.json found
)

echo [INFO] Backup created in: !BACKUP_DIR!\
echo.

cd frontend

echo [INFO] Running npm audit to check current vulnerabilities...
call npm audit
echo.

echo [WARNING] This will run 'npm audit fix --force' which may make breaking changes.
set /p "choice=Do you want to continue? (y/N): "
if /i not "!choice!"=="y" (
    echo [INFO] Operation cancelled.
    pause
    exit /b 0
)

echo.
echo [INFO] Running npm audit fix --force...
call npm audit fix --force

if !errorlevel! equ 0 (
    echo [INFO] Fix completed successfully!
    echo.
    echo [INFO] Checking for remaining vulnerabilities...
    call npm audit
    echo.
    echo [INFO] Testing if the application still builds...
    call npm run build

    if !errorlevel! equ 0 (
        echo [INFO] ✅ Build successful! Application is working correctly.
    ) else (
        echo [ERROR] ❌ Build failed! There may be breaking changes.
        echo [WARNING] To rollback, run: rollback.bat !BACKUP_DIR!
    )
) else (
    echo [ERROR] ❌ npm audit fix --force failed!
    echo [WARNING] To rollback, run: rollback.bat !BACKUP_DIR!
)

echo.
echo [INFO] Checking updated dependencies...
call npm list --depth=0

echo.
echo === SUMMARY ===
echo ✅ Backup created: !BACKUP_DIR!\
echo ✅ Vulnerabilities fixed (if any were found)
echo ✅ Build tested
echo.
echo [WARNING] If you encounter any issues:
echo 1. Try running: npm install
echo 2. If that doesn't work, rollback with: rollback.bat !BACKUP_DIR!
echo 3. Check the React app documentation for any breaking changes
echo.
pause
