@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY_EXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"

echo ========================================================
echo   NeuroCheat 硬體訊號橋接中心 (Exp 2 + Exp 3 整合)
echo ========================================================
echo   [1] 純合成雙通道模擬測試 (無須實機，推播至遊戲 F1 實機模式)
echo   [2] Exp 3 S01 受試者資料重播 + Exp 2 ECG/EMG 模擬
echo   [3] 掃描附近 HM-10 BLE 裝置 (確認電腦找得到模組)
echo   [4] 連線 HM-10 BLE 實機 (可搭配 --ble-test 免貼電極測試波 + BrainLink)
echo   [5] 自訂連線 COM Port (HC-05/USB Arduino + BrainLink)
echo   [6] 啟動互動式訊號控制台 (manual keypress -> UDP)
echo ========================================================
set /p choice="請選擇模式 (1-6，預設 1): "

if "%choice%"=="" set "choice=1"
if "%choice%"=="1" (
    "%PY_EXE%" -m bio_bridge.bridge_hub --eeg sim --arduino-mode sim
) else if "%choice%"=="2" (
    "%PY_EXE%" -m bio_bridge.bridge_hub --eeg replay --sub S01 --arduino-mode sim
) else if "%choice%"=="3" (
    "%PY_EXE%" -m bio_bridge.bridge_hub --scan-ble
) else if "%choice%"=="4" (
    set /p ble_addr="HM-10 MAC 位址 (留空則自動搜尋 HMSoft/FFE0): "
    set /p ble_test_q="是否開啟 Arduino 內建測試波 (--ble-test)? [y/N] (預設 n): "
    set /p eeg_mode="EEG 模式 [live / replay / sim / none] (預設 sim): "
    if "%eeg_mode%"=="" set "eeg_mode=sim"
    set "EEG_ARG=--eeg %eeg_mode%"
    if /I "%eeg_mode%"=="live" (
        set /p eeg_com="BrainLink COM Port (例如 COM3): "
        set "EEG_ARG=--eeg live --eeg-com %eeg_com%"
    )
    set "BLE_ARGS=--arduino-mode ble"
    if not "%ble_addr%"=="" set "BLE_ARGS=%BLE_ARGS% --ble-addr %ble_addr%"
    if /I "%ble_test_q%"=="y" set "BLE_ARGS=%BLE_ARGS% --ble-test"
    "%PY_EXE%" -m bio_bridge.bridge_hub %EEG_ARG% %BLE_ARGS%
) else if "%choice%"=="5" (
    set /p eeg_mode="EEG 模式 [live / replay / sim / none] (預設 live): "
    if "%eeg_mode%"=="" set "eeg_mode=live"
    set /p eeg_com="BrainLink COM Port (例如 COM3): "
    set /p ard_mode="Arduino 模式 [dual / exp2_raw / sim / none] (預設 dual): "
    if "%ard_mode%"=="" set "ard_mode=dual"
    set /p bio_com="Arduino/HC-05 COM Port (例如 COM4，無則留空): "
    set /p bio_baud="Arduino Baudrate (HC-05藍牙 9600 / USB 115200，預設 9600): "
    if "%bio_baud%"=="" set "bio_baud=9600"
    if "%bio_com%"=="" (
        "%PY_EXE%" -m bio_bridge.bridge_hub --eeg "%eeg_mode%" --eeg-com "%eeg_com%" --arduino-mode sim
    ) else (
        "%PY_EXE%" -m bio_bridge.bridge_hub --eeg "%eeg_mode%" --eeg-com "%eeg_com%" --arduino-mode "%ard_mode%" --bio-com "%bio_com%" --bio-baud "%bio_baud%"
    )
) else if "%choice%"=="6" (
    "%PY_EXE%" -m bio_bridge.external_signal_sender
) else (
    echo 無效選擇。
)

pause
