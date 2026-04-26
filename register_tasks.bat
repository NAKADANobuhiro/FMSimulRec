@echo off
REM Run as Administrator (right-click -> Run as administrator)
REM Registers 3 one-time recording tasks in Task Scheduler

echo Registering tasks...

SCHTASKS /CREATE /TN "RadioRec_ToyamaCityFM_0430" ^
  /TR "C:\RadioRec\rec_toyamacityfm.bat" ^
  /SC ONCE /SD 2026/04/30 /ST 12:30 /F
echo [OK] ToyamaCityFM  4/30 12:30-13:00

SCHTASKS /CREATE /TN "RadioRec_Takaoka_0501" ^
  /TR "C:\RadioRec\rec_radiotakaoka.bat" ^
  /SC ONCE /SD 2026/05/01 /ST 13:00 /F
echo [OK] RadioTakaoka  5/1  13:00-14:00

SCHTASKS /CREATE /TN "RadioRec_FMTonami_0502" ^
  /TR "C:\RadioRec\rec_fmtonami.bat" ^
  /SC ONCE /SD 2026/05/02 /ST 12:00 /F
echo [OK] FMTonami       5/2  12:00-12:30

echo.
echo Done. Verify:
echo   SCHTASKS /QUERY /TN "RadioRec_ToyamaCityFM_0430"
pause
