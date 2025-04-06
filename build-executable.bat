@echo off
echo Setting up build environment...
pushd "%~dp0"

REM Define Project Name and Main Script
set APP_NAME=ImagesToVideoSlideshow
set MAIN_SCRIPT=Main.py
set ICON_ICO=icon.ico
set ICON_PNG=icon.png
set FFMPEG_EXE=ffmpeg.exe

REM Check if required files exist before starting
if not exist "%MAIN_SCRIPT%" (
    echo ERROR: Main script "%MAIN_SCRIPT%" not found in current directory.
    goto :error_exit
)
if not exist "%ICON_PNG%" (
    echo WARNING: "%ICON_PNG%" not found. Window icon might be missing in the app.
)
if not exist "%FFMPEG_EXE%" (
    echo ERROR: "%FFMPEG_EXE%" not found. This is required for the build.
    goto :error_exit
)
if not exist "%ICON_ICO%" (
    echo WARNING: "%ICON_ICO%" not found. Executable file icon will be default.
    set ICON_FLAG=
) else (
    set ICON_FLAG=--icon="%ICON_ICO%"
)


REM Check if virtual environment exists, create if it doesn't
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo Failed to create virtual environment. Make sure Python is installed and in PATH.
        goto :error_exit
    )
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate
if %ERRORLEVEL% neq 0 (
    echo Failed to activate virtual environment.
    goto :error_exit
)

REM Install/Upgrade PyInstaller and requirements
echo Installing/Updating requirements and PyInstaller...
REM Ensure pip is up-to-date
python -m pip install --upgrade pip > nul
REM Install requirements from file OR specific known ones + PyInstaller
if exist "requirements.txt" (
    pip install -r requirements.txt pyinstaller
) else (
    echo requirements.txt not found, installing base packages + PyInstaller...
    pip install opencv-python numpy pillow tkinterdnd2-universal pyinstaller
)
if %ERRORLEVEL% neq 0 (
    echo Failed to install packages. Check network connection and pip.
    goto :error_exit
)


REM Build executable (One-File)
echo Building executable (%APP_NAME%)...
pyinstaller --noconfirm ^
    --onefile ^
    --windowed ^
    %ICON_FLAG% ^
    --add-data "%FFMPEG_EXE%;." ^
    --add-data "%ICON_PNG%;." ^
    --distpath "." ^
    --name "%APP_NAME%" ^
    --collect-all tkinterdnd2 ^
    --hidden-import "PIL.ImageTk" ^
    "%MAIN_SCRIPT%"

if %ERRORLEVEL% neq 0 (
    echo PyInstaller build failed! See messages above.
    goto :error_exit
)

REM Clean up build artifacts
echo Cleaning up...
rmdir /s /q build
del "%APP_NAME%.spec"

echo.
REM Check if the main executable exists directly in the output directory
if exist "%APP_NAME%.exe" (
    echo Build successful!
    echo Executable "%APP_NAME%.exe" is located in the current directory.
) else (
    echo Build check failed! Expected executable "%APP_NAME%.exe" not found.
    goto :error_exit
)

echo Build process complete.
goto :eof

:error_exit
echo.
echo Build process failed!
popd
pause
exit /b 1

:eof
popd
echo Press any key to close this window.
pause > nul
exit /b 0 