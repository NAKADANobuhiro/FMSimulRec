@echo off
REM FMTonami  5/2 12:00-12:30 (30min=1800sec)
set STATION=fmtonami
set DURATION=1800
set SAVE_DIR=C:\RadioRec
set SCRIPT=C:\RadioRec\jcba_rec.py

if not exist "%SAVE_DIR%" mkdir "%SAVE_DIR%"

for /f "tokens=1-3 delims=/" %%a in ("%date%") do set YMD=%%a%%b%%c
for /f "tokens=1-2 delims=:." %%a in ("%time: =0%") do set HM=%%a%%b
set OUTFILE=%SAVE_DIR%\%STATION%_%YMD%_%HM%.ogg

echo [%date% %time%] START %STATION% >> "%SAVE_DIR%\rec_log.txt"
python "%SCRIPT%" %STATION% %DURATION% "%OUTFILE%" >> "%SAVE_DIR%\rec_log.txt" 2>&1
echo [%date% %time%] END   %STATION% >> "%SAVE_DIR%\rec_log.txt"
