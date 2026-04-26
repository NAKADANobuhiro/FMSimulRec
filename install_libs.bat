@echo off
REM Install required Python libraries
REM Run once before first recording

echo Installing required libraries...
pip install requests websocket-client
echo.
echo Done. Please close this window.
pause
