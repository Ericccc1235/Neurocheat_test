# NeuroCheat: Don’t Get Caught, a Brain Control Exam Survival Game
**生醫工程期末專題 - Group 6**  
**組員：黃建澄 (B13502162)、王家佑 (B13901094)、張嘉宸 (B13901135)**

---

## 🎯 專案理念與遊戲背景
「**作弊不是問 Gemini，而是控制自己的身體。**」  
玩家身處電資學院期末考考場，時間有限，必須在**奶龍監考官**嚴密的法眼巡視下，一邊看手中密藏小抄一邊作答考卷。只有達到 **90 分以上 (A+)** 才能順利通關，否則只能停修！

---

## 🔀 雙模式系統 (Dual Game Modes)

遊戲首頁與遊戲中（按 `M` 鍵或點擊右上角模式按鈕）支援兩種模式自由選擇與切換：

### 🟢 模式一：手動調控模式 (`MANUAL`)
- **自己調控 ECG、EEG、EMG**：
  - **EMG（小抄按鈕）**：按 `空白鍵` / `C 鍵` / `滑鼠右鍵` / 螢幕 `EMG 按鈕`，將小抄由桌底舉到眼前或收回。
  - **ECG（心率 BPM）**：按 `方向鍵 ↑ / ↓` 或點擊螢幕 `BPM▲ / BPM▼` 按鈕，直接增減基準心率（不會自動跳回 70 BPM！），按住 `R 鍵` 或 `深呼吸放鬆` 按鈕可平復心率。
  - **EEG（腦波專注度）**：按 `W / S 鍵` 或點擊螢幕 `專注(W) / 分心(S)` 按鈕，直接調整小抄透明度與清晰度。

### 🟣 模式二：外部訊號輸入模式 (`EXTERNAL`)
- **必須從外部輸入 ECG、EEG 訊號，按鈕控制 EMG**：
  - 鎖定鍵盤與畫面上的 ECG、EEG 手動微調按鍵（嘗試點擊會跳出外部模式鎖定提示）。
  - **EMG（小抄開闔）**：維持以按鈕（`空白鍵` / `滑鼠右鍵` / 螢幕 `EMG 按鈕`）控制，亦相容外部輸入 `EMG:1`。
  - **ECG 與 EEG 外部輸入支援 3 種即時管道（零設定同時監聽）**：
    1. **Arduino / ESP32 Serial 序列埠 (COM Port)**：點擊首頁或儀表板右下角的 `COM埠` 按鈕即可自動掃描並切換 COM 埠（鮑率 `115200`），傳送格式如：`ECG:85,EEG:78\n` 或 `EMG:1,ECG:85.0,EEG:78.5\n`。
    2. **本地 UDP Socket (`127.0.0.1:5005`)**：任何外部 Python 訊號處理腳本（如 OpenBCI、LSL、PySerial 濾波程式）可直接對 `127.0.0.1:5005` 發送 `"ECG:88.5,EEG:82.0"` 或 JSON `'{"ecg": 88.5, "eeg": 82.0}'`。
    3. **外部訊號發送測試工具 (`external_signal_sender.py`)**：
       - 開啟另一個終端機執行 `python external_signal_sender.py`（互動輸入心率與專注度）或 `python external_signal_sender.py --auto`（自動連續正弦波串流測試）。

---

## 🧠 三大生理訊號與遊戲機制

| 生理訊號 | 對應機制 | 遊戲操作與效果 |
| :--- | :--- | :--- |
| **EMG (肌電 / 握拳用力)** | **手中密藏小抄開闔** | **【以按鈕代替】**：<br>• 單擊 `SPACE`（空白鍵）、`C` 鍵、滑鼠右鍵或畫面 `EMG 按鈕` 舉起/收起小抄。<br>• 奶龍轉頭巡視時若未及時收起，直接被抓包零分當掉！ |
| **EEG (腦電 / 專注度)** | **小抄清晰度與透明度** | • 專注度高時（$\ge 80\%$）：小抄字體 100% 飽和清晰。<br>• 專注度低時（$\le 25\%$）：字體完全透明隱形。<br>• 模式一可由 `W`/`S` 調整；模式二必須由外部腦波訊號輸入。 |
| **ECG (心電 / 緊張程度)** | **心率與奶龍警戒巡邏** | • 即時動態繪製 P-Q-R-S-T 心電圖與心率 BPM。<br>• 心率過高時會觸發蜂鳴器預警並大幅增加奶龍下台巡邏機率！<br>• 模式一可由 `↑`/`↓` 與 `R` 鍵調控；模式二必須由外部心電訊號輸入。 |

---

## 📂 專案檔案結構
```text
生醫工程期末專題/
├── main.py                      # 遊戲主迴圈、雙模式切換與事件監聽
├── bio_signals.py               # 生理訊號管理 (支援 MANUAL 手動模式與 EXTERNAL 外部訊號模式)
├── hardware_bridge.py           # 外部訊號接收橋接器 (支援 Serial COM 埠、UDP:5005 與 JSON)
├── external_signal_sender.py    # 外部 ECG/EEG 訊號傳送器 (供外部模式測試與串接範本)
├── teacher.py                   # 奶龍監考官 AI 狀態機、蜂鳴器預警、假動作與抓包判定
├── exam.py                      # 10 道電資與生醫工程考題、題目導航、計分邏輯
├── ui_renderer.py               # 視窗畫面渲染 (奶龍、手中密藏小抄、雙模式生醫儀表板)
├── sound_generator.py           # 程序化音效合成器 (蜂鳴器、心跳聲、抓包音效、翻紙聲)
├── data_logger.py               # 4Hz 生理訊號紀錄器 (自動匯出 neurocheat_session_data.csv)
├── analyze_bio_data.py          # 賽後生理數據視覺化分析腳本
├── arduino_neurocheat.ino       # Arduino 韌體範例程式碼
├── run_game.bat                 # Windows 一鍵啟動批次檔
└── README.md                    # 專案說明手冊
```

---

## 🚀 如何啟動遊戲

### 1. 啟動主遊戲
雙擊執行 **`run_game.bat`**，或在終端機執行：
```powershell
& "C:\Users\ACER\AppData\Local\Programs\Python\Python313\python.exe" main.py
```

### 2. 在「模式二：外部訊號模式」下從外部傳送 ECG / EEG 訊號
若尚未插上實體 Arduino，可開啟第二個終端機視窗執行內建的外部訊號傳送工具：
```powershell
# 互動式手動輸入外部 [ECG心率 EEG專注度]
& "C:\Users\ACER\AppData\Local\Programs\Python\Python313\python.exe" external_signal_sender.py

# 或自動連續傳送動態變化的外部 ECG/EEG 生理波形
& "C:\Users\ACER\AppData\Local\Programs\Python\Python313\python.exe" external_signal_sender.py --auto
```

---

## ⌨️ 遊戲按鍵對照表

| 按鍵 / 畫面按鈕 | 功能說明 |
| :--- | :--- |
| **1 鍵 / 2 鍵 (首頁)** | 首頁快速選擇 **【模式一：手動調控模式】** 或 **【模式二：外部訊號模式】** |
| **M 鍵** 或 **儀表板右上角按鈕** | 遊戲中隨時切換 **手動調控模式** $\leftrightarrow$ **外部訊號模式** |
| **ESC 鍵** | 隨時返回首頁模式選擇選單 |
| **SPACE (空白鍵)** / **C 鍵** / **滑鼠右鍵** | **切換拿起／收起手中密藏小抄** (EMG 按鈕控制) |
| **方向鍵 ↑ / ↓** 或 **BPM ▲ / ▼** | **【僅限模式一】** 調升 / 調降 ECG 心率 ($\pm 5$ BPM) |
| **W / S 鍵** 或 **專注 / 分心按鈕** | **【僅限模式一】** 提高 / 降低 EEG 專注度 ($\pm 10\%$) |
| **R 鍵** 或 **深呼吸按鈕** | **【僅限模式一】** 按住深呼吸冷靜降低心率 |
| **1 / 2 / 3 / 4** 或 **左/右方向鍵** | 快速作答 A/B/C/D 選項、切換上一題 / 下一題 |
