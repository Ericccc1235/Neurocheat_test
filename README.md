# NeuroCheat: 生醫電子考場潛行 (Exp 2 + Exp 3 Co-op 版)

第一人稱 3D 生醫工程期末考潛行遊戲：結合 **實驗二 (ECG / EMG 類比前端 + Python 數位濾波)** 與 **實驗三 (BrainLink 單通道 EEG 專注/Stroop 負荷/Fp1 雙眨眼翻頁)**。

---

## 資料夾架構（已整理為標準模組化專案）

```text
Neurocheat_test/
├── main.py                              # 遊戲主程式 (TITLE -> CALIBRATION -> PLAYING -> REPORT)
├── run_game.bat                         # 一鍵啟動遊戲 (自動優先使用 .venv)
├── run_bridge.bat                       # 硬體訊號橋接器選單 (實機 / 重播 / 模擬器)
├── requirements.txt                     # 團隊共編統一套件清單
├── .gitignore                           # 排除 .venv/ 與個人遊玩產出的 sessions/
├── assets/
│   ├── teacher_back.png                 # 3D 去背奶娃老師：背對板書
│   ├── teacher_peek.png                 # 3D 去背奶娃老師：側身回頭偷瞄
│   ├── teacher_patrol.png               # 3D 去背奶娃老師：眼鏡教鞭走道巡堂
│   ├── teacher_laugh.png                # 3D 去背奶娃大笑：抓包嘲笑結局
│   └── docs/115_1_g6_proposal.pdf       # 專題企劃書參考
├── game/                                # 遊戲核心模組
│   ├── bio_signals.py                   # EMG/ECG/EEG 狀態機、疲勞抽筋、基線ΔBPM、Stroop 與翻頁
│   ├── hardware_bridge.py               # UDP :5005 接收 / :5006 指令回傳 + Serial 直連相容
│   ├── classroom_3d.py                  # Z-Sort 3D 立體教室、1080x700 超取樣考卷、3D 老師走道逼近
│   ├── teacher.py                       # 三階難度 AI (走道逼近 / 雙重假動作 / 近距微縫抓包)
│   ├── exam.py                          # 18 題隨機題庫 + 難度時限 (115s/95s/80s) + 同學作答進度解鎖
│   ├── ui_renderer.py                   # 15 秒個人校正精靈、即時生醫示波器 HUD 與結算成績單
│   ├── sound_generator.py               # NumPy 即時合成音效 (免外部音效檔)
│   └── data_logger.py                   # 局內 4Hz 生理遙測記錄匯出 (sessions/*.csv)
├── bio_bridge/                          # Exp 2 + Exp 3 即時線上因果訊號處理核心
│   ├── bridge_hub.py                    # 同步融合 Exp 2 + Exp 3 並以 25Hz UDP JSON 推播
│   ├── exp2_dsp.py                      # 60Hz 數位陷波 + 0.5-40Hz 因果帶通 + R-peak 品管 + EMG 遲滯校正
│   ├── eeg_realtime.py                  # 純因果 38 特徵擷取 + Shrinkage LDA (Focus/Relax/Stroop) + EOG 雙眨眼
│   ├── eeg_models.npz                   # 預訓練純 NumPy 權重 (跨 Python/sklearn 版本零警告)
│   └── external_signal_sender.py        # 無硬體時的手動/自動 UDP 測試模擬器
├── firmware/
│   ├── neurocheat_exp2_dual/            # 整合新版：A0(ECG@160Hz) + A1(EMG包絡@1kHz) 3-byte 自我同步 + Pin8蜂鳴器
│   └── neurocheat_exp2_raw_compat/      # 相容原版 Exp 2 200Hz 單通道 ECG 韌體
├── analytics/
│   └── analyze_bio_data.py              # 課後 ECG/EMG/EEG 與風險分析四聯圖繪製
└── sessions/                            # 執行時自動產生（已列入 .gitignore，不上傳 GitHub）
```

---

## 同學共編快速上手（首次 Clone 下來只需做一次）

```bash
git clone https://github.com/Ericccc1235/Neurocheat_test.git
cd Neurocheat_test

# 建立隔離虛擬環境 (推薦使用 Python 3.11 ~ 3.13)
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 啟動遊戲！
python main.py
# 或直接雙擊 run_game.bat
```

> 共編守則：所有測試產生的 CSV 與圖片都會自動寫入 `sessions/`（已被 `.gitignore` 忽略），切勿將個人 `.venv/` 或測試 log 提交進 Git。

---

## 實驗二硬體整合與精簡建議

| 項目 | 建議保留 / 新增 | 建議刪除或改以數位處理 (`exp2_dsp.py`) |
| :--- | :--- | :--- |
| **前端差動與電氣安全** | **保留** AD620 + 電氣隔離（行動電源供電 + **HM-10 BLE** / HC-05）+ **建議新增 RLD 右腿驅動**（或穩壓偏置 + 2.5V Vref Buffer） | 原本 **類比 60Hz Fliege Notch**（對電容誤差與溫漂敏感，且阻帶不夠穩）→ 改由 Python `iirnotch(60Hz, Q=30)` 精準濾除 |
| **EMG 前級** | **保留** 20–500Hz 帶通 + 整流包絡（或讓 `neurocheat_exp2_dual.ino` 在 Arduino 內以 1kHz 採樣 A1 取包絡後傳送，避開 200Hz 取樣混疊與 `9600 baud` 瓶頸！）| 原本 **10µF 大電容 0.1Hz 高通**（動作干擾恢復慢 $\tau=10\text{s}$）→ 改為 `1µF` (`~1.6Hz`) 或直接交由數位 `0.5-40Hz` `sosfilt` 帶通處理 |
| **反折疊 / LPF** | **保留** 固定 ~50~70Hz 一階 RC LPF 當硬體抗混疊保護 | 可省略 Arduino 外接分壓或過度多級類比調增益（並將總增益調低避免 `0~5V` 截波飽和） |
| **硬體雙向回饋** | **可新增** Pin 8 主動式蜂鳴器 / 震動馬達（與遊戲老師警告同步響）+ Pin 4 微動測試按鈕 | — |

---

## 操作方式說明

- **開考模式與難度**：於標題頁可選 `輕鬆練習 (115s)`、`標準期末考 (95s，預設)`、`地獄大刀教授 (80s)`，並支援「直接開考」或「15 秒考前基線校正精靈」。
- **切換感測器來源**：遊戲中按 **`F1`** 切換 `MANUAL`（鍵鼠模擬）與 `EXTERNAL`（硬體串流）；按 **`F2`** 切換直連 COM Port。
- **操作按鍵**：
  - **滑鼠移動 / `V` 鍵**：轉頭查看走道老師與黑板、低頭或按住 **`V`** 傾身拉近高清考卷作答（支援 3D 單應性點擊）、左右偷看鄰座（隨時間進度作答解鎖：左 **阿明** 常猜錯、右 **小華** 為學霸）。
  - **`空白鍵` / `滑鼠右鍵` / EMG 用力握拳**：全開抽屜看小抄（持續過久手臂疲勞滿 100% 會抽筋彈回並發出巨響！）。
  - **`F` 鍵 / EMG 輕握**：微開抽屜縫隙偷窺（遠距離有機會閃避，但當老師走近走道時會被直接識破！）。
  - **`Tab` / BrainLink Fp1 雙眨眼**：免手翻閱第 1 頁 (`Q1~Q5`) 與第 2 頁 (`Q6~Q10`) 公式小抄。
  - **`R` 鍵 / 真實心跳低於基線**：深呼吸冷靜光環，加速降低老師懷疑值並縮短巡邏盯視。
  - **手動調參測試**：`1~4` 選答案、`←/→` 換題、`Q/E` 調 EEG 專注度、`Z/X` 調 Stroop 壓力、`↑/↓` 調 ECG 心率。

---

## 實機硬體聯動啟動順序

1. 先執行 **`run_bridge.bat`**（或手動執行下方指令）：
   ```bash
   # 例：雙通道模擬測試（無須硬體即可體驗真實 DSP + LDA 管線）
   .venv\Scripts\python.exe -m bio_bridge.bridge_hub --eeg sim --arduino-mode sim

   # 例：Exp 3 受試者重播 + Exp 2 原版單通道 ECG 藍牙實機 (COM4 @ 9600)
   .venv\Scripts\python.exe -m bio_bridge.bridge_hub --eeg replay --sub S01 --arduino-mode exp2_raw --bio-com COM4 --bio-baud 9600

   # 例：掃描並連線 HM-10 BLE（無須 COM Port！--ble-test 可免貼電極測封包）
   .venv\Scripts\python.exe -m bio_bridge.bridge_hub --scan-ble
   .venv\Scripts\python.exe -m bio_bridge.bridge_hub --eeg sim --arduino-mode ble --ble-test

   # 例：全實機雙系統 (BrainLink COM3 + HM-10 BLE Arduino)
   .venv\Scripts\python.exe -m bio_bridge.bridge_hub --eeg live --eeg-com COM3 --arduino-mode ble
   ```
2. 再啟動 **`run_game.bat`**（或 `python main.py`），按 **`F1`** 切至 `EXTERNAL`，點擊「15 秒基線校正後開考」即可遊玩。
3. 遊戲結束後會自動產出 `sessions/neurocheat_session_data.csv` 與四聯分析圖 `sessions/bio_analysis_report.png`。
