@echo off
REM Check if pip is installed and show output only if it needs to be installed
python -m pip --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Installing pip...
    python -m ensurepip --default-pip
) else (
    python -m pip install --upgrade pip >nul 2>&1
)

REM Check if virtual environment exists, create if it doesn't
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate
    echo Installing requirements...
    
    REM Install required packages directly if requirements.txt doesn't exist
    if exist "requirements.txt" (
        pip install -r requirements.txt
    ) else (
        echo requirements.txt not found, installing packages directly...
        pip install opencv-python numpy pillow tkinterdnd2-universal
    )
    
    echo Setup complete!
    echo.
) else (
    call venv\Scripts\activate
)

REM Run the main application directly
python main.py

REM Pause only if the python script exited with an error
if %ERRORLEVEL% neq 0 pause