@echo off
REM RadioTakaoka  5/1 13:00-14:00 (60min=3600sec)
set STATION=radiotakaoka
set DURATION=3600
set SAVE_DIR=C:\RadioRec
set SCRIPT=C:\RadioRec\jcba_rec.py

if not exist "%SAVE_DIR%" mkdir "%SAVE_DIR%"

for /f "tokens=1-3 delims=/" %%a in ("%date%") do set YMD=%%a%%b%%c
for /f "tokens=1-2 delims=:." %%a in ("%time: =0%") do set HM=%%a%%b
set OUTFILE=%SAVE_DIR%\%STATION%_%YMD%_%HM%.ogg

echo [%date% %time%] START %STATION% >> "%SAVE_DIR%\rec_log.txt"
python "%SCRIPT%" %STATION% %DURATION% "%OUTFILE%"
echo [%date% %time%] END   %STATION% >> "%SAVE_DIR%\rec_log.txt"
