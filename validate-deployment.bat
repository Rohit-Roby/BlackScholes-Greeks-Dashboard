@echo off
REM Deployment Validation Script for Windows
REM Validates Docker build, containers, API health, and performance

setlocal enabledelayedexpansion

set API_URL=%1
if "%API_URL%"=="" set API_URL=http://localhost:8000

set FRONTEND_URL=%2
if "%FRONTEND_URL%"=="" set FRONTEND_URL=http://localhost

set TIMEOUT=10
set RETRIES=3
set PASSED=0
set FAILED=0
set WARNINGS=0

REM ============================================================
REM 1. Docker Check
REM ============================================================
echo.
echo === 1. Docker Installation Check ===
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker not installed
    set /a FAILED+=1
) else (
    echo [OK] Docker installed
    set /a PASSED+=1
    
    docker info >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] Docker daemon not accessible
        set /a FAILED+=1
    ) else (
        echo [OK] Docker daemon running
        set /a PASSED+=1
    )
)

REM ============================================================
REM 2. Container Status
REM ============================================================
echo.
echo === 2. Container Status ===
docker ps | findstr /i "greeks.*backend" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Backend container running
    set /a PASSED+=1
    for /f "tokens=*" %%a in ('docker ps -q -f name="greeks.*backend"') do set BACKEND_ID=%%a
) else (
    echo [ERROR] Backend container not running
    set /a FAILED+=1
)

docker ps | findstr /i "greeks.*frontend" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Frontend container running
    set /a PASSED+=1
) else (
    echo [ERROR] Frontend container not running
    set /a FAILED+=1
)

REM ============================================================
REM 3. API Health Check
REM ============================================================
echo.
echo === 3. API Health Check ===
for /l %%i in (1,1,%RETRIES%) do (
    curl -s "%API_URL%/api/health" >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK] Backend API reachable
        set /a PASSED+=1
        goto api_ok
    )
    if %%i lss %RETRIES% (
        echo Retry %%i/%RETRIES%...
        timeout /t 2 >nul
    )
)
echo [ERROR] Backend API not reachable
set /a FAILED+=1

:api_ok

REM ============================================================
REM 4. Endpoint Tests
REM ============================================================
echo.
echo === 4. API Endpoints ===

REM Calculate Greeks
curl -s -X POST "%API_URL%/api/calculate-greeks" ^
  -H "Content-Type: application/json" ^
  -d "{\"spot_price\":100,\"strike_price\":100,\"days_to_expiration\":30,\"interest_rate\":5,\"implied_volatility\":25}" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Calculate Greeks endpoint working
    set /a PASSED+=1
) else (
    echo [ERROR] Calculate Greeks endpoint failed
    set /a FAILED+=1
)

REM Greeks Surface
curl -s -X POST "%API_URL%/api/greeks-surface" ^
  -H "Content-Type: application/json" ^
  -d "{\"spot_price\":100,\"strike_price\":100,\"days_to_expiration\":30,\"interest_rate\":5,\"implied_volatility\":25,\"num_points\":10,\"spot_range\":[0.8,1.2]}" >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Greeks Surface endpoint working
    set /a PASSED+=1
) else (
    echo [ERROR] Greeks Surface endpoint failed
    set /a FAILED+=1
)

REM ============================================================
REM 5. Configuration Check
REM ============================================================
echo.
echo === 5. Configuration Check ===
if exist ".env" (
    echo [OK] .env file exists
    set /a PASSED+=1
    
    findstr /i "ENVIRONMENT=production" .env >nul
    if %errorlevel% equ 0 (
        echo [OK] Production environment configured
        set /a PASSED+=1
    ) else (
        echo [WARNING] Not configured for production
        set /a WARNINGS+=1
    )
    
    findstr /i "DEBUG=false" .env >nul
    if %errorlevel% equ 0 (
        echo [OK] Debug mode disabled
        set /a PASSED+=1
    ) else (
        echo [WARNING] Debug mode may be enabled
        set /a WARNINGS+=1
    )
) else (
    echo [WARNING] .env file not found
    set /a WARNINGS+=1
)

REM ============================================================
REM 6. Docker Compose Check
REM ============================================================
echo.
echo === 6. Docker Compose Validation ===
if exist "docker-compose.prod.yml" (
    echo [OK] Production compose file exists
    set /a PASSED+=1
    
    docker-compose -f docker-compose.prod.yml config >nul 2>&1
    if %errorlevel% equ 0 (
        echo [OK] Docker Compose configuration valid
        set /a PASSED+=1
    ) else (
        echo [ERROR] Docker Compose configuration invalid
        set /a FAILED+=1
    )
) else (
    echo [WARNING] Production compose file not found
    set /a WARNINGS+=1
)

REM ============================================================
REM Summary
REM ============================================================
echo.
echo ============================================================
echo Validation Summary
echo ============================================================
set /a TOTAL=%PASSED% + %FAILED% + %WARNINGS%
echo Total Checks: %TOTAL%
echo [OK] Passed: %PASSED%
echo [ERROR] Failed: %FAILED%
echo [WARNING] Warnings: %WARNINGS%
echo.

if %FAILED% equ 0 (
    echo Deployment validation successful!
    exit /b 0
) else (
    echo Deployment validation failed - %FAILED% issues detected
    exit /b 1
)
