@echo off
chcp 65001 >nul
echo ========================================================
echo   NeuroCheat: Don't Get Caught - 腦控期末考生存遊戲
echo   生醫工程期末專題 (Group 6)
echo ========================================================
echo.
echo 正在啟動遊戲環境...

if exist "C:\Users\ACER\AppData\Local\Programs\Python\Python313\python.exe" (
    "C:\Users\ACER\AppData\Local\Programs\Python\Python313\python.exe" main.py
) else (
    python main.py
)

pause
