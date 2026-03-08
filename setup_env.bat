@echo off
REM Activate existing virtual environment and install requirements (Windows)

echo.
echo ======================================
echo   Bordle Environment Setup
echo ======================================
echo.

REM Check if venv exists
if not exist ".venv" (
    echo ❌ Virtual environment not found at .venv
    echo Please create it first with: python -m venv .venv
    echo.
    pause
    exit /b 1
)

REM Activate venv
echo ✅ Activating virtual environment...
call .venv\Scripts\activate.bat

REM Upgrade pip
echo 📦 Upgrading pip...
python -m pip install --upgrade pip setuptools wheel

REM Install requirements
echo 📦 Installing requirements from requirements.txt...
pip install -r requirements.txt

echo.
echo ======================================
echo ✅ Setup complete!
echo ======================================
echo.
echo Your virtual environment is ready:
echo   - Located in: .\.venv
echo   - Currently: ACTIVATED
echo.
echo Next steps:
echo   1. Validate packages: python scripts\validate_requirements.py
echo   2. Run the app: python app.py
echo   3. Run tests: python scripts\test_postgres_integration.py
echo.
echo To deactivate: deactivate
echo.

pause
