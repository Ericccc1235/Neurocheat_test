@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY_EXE=%~dp0.venv\Scripts\python.exe"
if exist "%PY_EXE%" (
    echo [NeuroCheat] 使用專案虛擬環境 .venv 啟動遊戲...
    "%PY_EXE%" main.py
    goto :end
)

where python >nul 2>&1
if %errorlevel%==0 (
    echo [NeuroCheat] 未找到 .venv，改用系統 Python 啟動...
    python main.py
    goto :end
)

echo [錯誤] 找不到 .venv 或系統 Python！
echo 請先執行以下指令建立共同開發環境：
echo   python -m venv .venv
echo   .venv\Scripts\pip install -r requirements.txt
pause

:end
if %errorlevel% neq 0 (
    echo.
    echo [提示] 程式異常結束，請確認是否已安裝 requirements.txt 套件。
    pause
)
