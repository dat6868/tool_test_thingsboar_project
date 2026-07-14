@echo off
:: Script khởi chạy Device Simulator Web trên Windows
cd /d "%~dp0\..\device_simulator_web"
echo Dang khoi chay Device Simulator Web tai cong 6369...
if exist "..\venv\Scripts\uvicorn.exe" (
    ..\venv\Scripts\uvicorn main:app --host 0.0.0.0 --port 6369 --no-access-log --reload
) else (
    uvicorn main:app --host 0.0.0.0 --port 6369 --no-access-log --reload
)
pause
