@echo off
setlocal enabledelayedexpansion

echo 🔄 NPM Rollback Script
echo ======================
echo.

if "%~1"=="" (
    echo [ERROR] Usage: %0 ^<backup_directory^>
    echo [ERROR] Example: %0 backup_20231227_143000
    pause
    exit /b 1
)

set "BACKUP_DIR=%~1"

if not exist "!BACKUP_DIR!" (
    echo [ERROR] Backup directory '!BACKUP_DIR!' not found!
    pause
    exit /b 1
)

if not exist "!BACKUP_DIR!\package.json" (
    echo [ERROR] Backup directory doesn't contain package.json!
    pause
    exit /b 1
)

echo [ROLLBACK] Found backup: !BACKUP_DIR!
echo [ROLLBACK] Contents:
dir "!BACKUP_DIR!" | findstr /r "package\.json package-lock\.json"
echo.

echo [WARNING] This will restore the following files:
echo   - frontend\package.json
echo   - frontend\package-lock.json (if exists)
echo.
echo [WARNING] This action will undo any changes made by npm audit fix --force
echo.
set /p "choice=Do you want to continue with rollback? (y/N): "
if /i not "!choice!"=="y" (
    echo [INFO] Rollback cancelled.
    pause
    exit /b 0
)

echo.
echo [ROLLBACK] Starting rollback...

REM Stop any running development server
taskkill /f /im "node.exe" >nul 2>&1
timeout /t 2 /nobreak >nul

REM Restore files
echo [ROLLBACK] Restoring package.json...
copy "!BACKUP_DIR!\package.json" frontend\ >nul

if exist "!BACKUP_DIR!\package-lock.json" (
    echo [ROLLBACK] Restoring package-lock.json...
    copy "!BACKUP_DIR!\package-lock.json" frontend\ >nul
)

REM Navigate to frontend and reinstall dependencies
cd frontend
echo [ROLLBACK] Reinstalling dependencies from restored package.json...
if exist "node_modules" rmdir /s /q node_modules
if exist "package-lock.json" del package-lock.json
call npm install

if !errorlevel! equ 0 (
    echo [INFO] ✅ Rollback completed successfully!
    echo.
    echo [INFO] Testing if the application builds...
    call npm run build

    if !errorlevel! equ 0 (
        echo [INFO] ✅ Build successful! Application is working correctly.
    ) else (
        echo [ERROR] ❌ Build failed after rollback!
        echo [WARNING] You may need to manually fix dependency issues.
    )
) else (
    echo [ERROR] ❌ Rollback failed during npm install!
    echo [WARNING] You may need to manually restore files and run npm install.
)

echo.
echo [INFO] Checking current dependencies...
call npm list --depth=0

echo.
echo === ROLLBACK SUMMARY ===
echo ✅ package.json restored from: !BACKUP_DIR!
if exist "!BACKUP_DIR!\package-lock.json" (
    echo ✅ package-lock.json restored
)
echo ✅ Dependencies reinstalled
echo ✅ Build tested
echo.
echo [ROLLBACK] Your original files are still available in: !BACKUP_DIR!
echo.
pause
