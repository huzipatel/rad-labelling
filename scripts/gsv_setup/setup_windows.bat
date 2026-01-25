@echo off
echo ============================================
echo GSV API Key Setup for Windows
echo ============================================
echo.

REM Check if gcloud is installed
where gcloud >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] gcloud CLI not found.
    echo.
    echo Please install Google Cloud SDK:
    echo   Option 1: winget install Google.CloudSDK
    echo   Option 2: Download from https://cloud.google.com/sdk/docs/install
    echo.
    pause
    exit /b 1
)

echo [OK] gcloud CLI found
echo.

REM Login to Google Cloud
echo Step 1: Logging into Google Cloud...
echo (A browser window will open - log in with your Google account)
echo.
gcloud auth login

echo.
echo Step 2: Getting billing accounts...
echo.
gcloud billing accounts list

echo.
echo ============================================
echo IMPORTANT: Copy your Billing Account ID
echo (format: XXXXXX-XXXXXX-XXXXXX)
echo ============================================
echo.
echo Now edit config.py and set BILLING_ACCOUNT_ID
echo Then run: python create_projects.py
echo.
pause

