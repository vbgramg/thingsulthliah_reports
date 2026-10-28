@echo off
title Mizoram VB-G RAM G Manual Sync
echo ============================================================
echo   Mizoram VB-G RAM G Report Sync (Thingsulthliah & Saitual)
echo ============================================================
cd /d "E:\thingsulthliah_reports"
"C:\Users\WCS\AppData\Local\Programs\Python\Python313\python.exe" "E:\thingsulthliah_reports\run_daily_sync.py"
echo.
echo Process complete. Press any key to close this window.
pause >nul
