# NeuroCheat 更新紀錄（給組員的共編交接說明）

這份文件整理了相較於先前版本（基準 commit `e8419a4`）的所有架構重排、Exp 2 / Exp 3 生醫訊號整合、遊戲性難度強化、3D 場景／文字清晰度優化與「奶娃」監考老師替換內容，方便組員拉取程式碼後快速對齊進度與分工測試。

---

## 1. 專案資料夾整理與共編規範

原本散落在根目錄的程式與測試產出已整理為標準模組化架構：

```text
Neurocheat_test/
├── main.py                              # 主程式與狀態機 (TITLE -> CALIBRATION -> PLAYING -> REPORT)
├── run_game.bat                         # 一鍵啟動遊戲（自動偵測 .venv）
├── run_bridge.bat                       # 硬體／模擬／重播訊號橋接器選單
├── requirements.txt                     # 團隊統一套件需求 (pygame/numpy/scipy/scikit-learn/pyserial/pillow/pandas/matplotlib)
├── .gitignore                           # 排除 .venv/、sessions/、*.csv、bio_analysis_report.png 等個人執行產物
├── README.md                            # 專案總說明、硬體對照表與啟動方式
├── CHANGELOG.md                         # 本次改動總整理（本文件）
├── assets/
│   ├── teacher_back.png                 # 奶娃老師：背對黑板拿粉筆（去背 PNG）
│   ├── teacher_peek.png                 # 奶娃老師：側身偷瞄（去背 PNG）
│   ├── teacher_patrol.png               # 奶娃老師：黑框眼鏡＋木教鞭巡堂（去背 PNG）
│   ├── teacher_laugh.png                # 奶娃老師：全身捧腹大笑抓包（去背 PNG）
│   └── docs/115_1_g6_proposal.pdf       # 專題企劃書（由根目錄移入）
├── game/                                # 遊戲邏輯、3D 教室渲染與 HUD
│   ├── bio_signals.py                   # 三感測生理狀態機、疲勞抽筋、基線 ΔBPM、Stroop 與小抄翻頁
│   ├── hardware_bridge.py               # UDP (:5005收/:5006發)、USB/藍牙串口解碼與檔案輪詢
│   ├── classroom_3d.py                  # Z-Sort 3D 立體教室、1080x700 超取樣考卷、攝影機與奶娃投影
│   ├── teacher.py                       # 三階難度 AI、走道 3D 逼近與雙重假動作陷阱
│   ├── exam.py                          # 18 題電資生醫題庫、三階時限與鄰座時間進度解鎖
│   ├── ui_renderer.py                   # 標題難度選單、15 秒個人校正精靈、即時生醫 HUD 與結算畫面
│   ├── sound_generator.py               # NumPy 即時合成音效（新增走道腳步聲）
│   └── data_logger.py                   # 0.25 秒間隔遙測記錄，結算匯出至 sessions/*.csv
├── bio_bridge/                          # Exp 2 + Exp 3 線上因果訊號處理中心
│   ├── bridge_hub.py                    # 融合 ECG / EMG / EEG 並以 25Hz UDP JSON 推播至遊戲
│   ├── exp2_dsp.py                      # Exp 2 二進位拆包、60Hz 數位陷波、0.5-40Hz ECG 帶通與 EMG 校正
│   ├── eeg_realtime.py                  # Exp 3 純因果 38 特徵 + Shrinkage LDA + Fp1 雙眨眼 + ThinkGear 解碼
│   ├── eeg_models.npz                   # 預訓練純 NumPy 權重包（免除 sklearn 版本相容警告）
│   └── external_signal_sender.py        # 無硬體時的手動鍵盤測試推播台
├── firmware/                            # Arduino 韌體（取代舊根目錄 arduino_neurocheat.ino）
│   ├── neurocheat_exp2_dual/neurocheat_exp2_dual.ino
│   └── neurocheat_exp2_raw_compat/arduino_ecg_bluetooth.ino
├── analytics/
│   └── analyze_bio_data.py              # 課後 ECG / EMG / EEG / 懷疑度四聯圖表繪製
└── sessions/                            # 執行時自動生成 CSV 與 PNG（已被 .gitignore 忽略，不會上傳 Git）
```

> 共編提醒：開發或測試產出的紀錄都會自動放到 `sessions/`，且 `.venv/` 已列入 `.gitignore`，請勿手動提交個人虛擬環境與測試紀錄檔。

---

## 2. 實驗二（Exp 2 ECG + EMG）整合與硬體簡化

* **新版雙通道韌體 ([neurocheat_exp2_dual.ino](file:///D:/biomedical_final/Neurocheat_test/firmware/neurocheat_exp2_dual/neurocheat_exp2_dual.ino))**：
  * `A0` 採樣 ECG（`160Hz`，10-bit），`A1` 在 Arduino 內以 **`1000Hz` 採樣並計算 EMG 包絡線**，避免 `200Hz` 取樣對 20–500Hz EMG 產生混疊（Aliasing），打包為 3-byte 自我同步二進位封包（每秒 480 bytes，可穩定跑在 HC-05 `9600 baud` 與 USB `115200 baud`）。
  * 支援選配 Pin `4` 實體微動按鈕（不貼電極時按住模擬用力握拳）與 Pin `8` 有源蜂鳴器／震動馬達（接收遊戲傳回的 `'B'`／`'C'` 指令同步發出警告或抓包音）。
  * 內建 `'T'` 指令切換模擬測試波，無電極也可測試整條藍牙／Serial 鏈路。
* **保留原版單通道相容 ([arduino_ecg_bluetooth.ino](file:///D:/biomedical_final/Neurocheat_test/firmware/neurocheat_exp2_raw_compat/arduino_ecg_bluetooth.ino))**：
  * 若暫時只想直接接原本實驗二的單通道 ECG 電路，`bridge_hub.py` 支援 `--arduino-mode exp2_raw` 直接解碼其 `200Hz` 單 byte 串流。
* **Python 數位濾波與硬體建議 ([exp2_dsp.py](file:///D:/biomedical_final/Neurocheat_test/bio_bridge/exp2_dsp.py))**：
  * 原本對電容誤差／溫漂敏感的 **類比 60Hz Fliege Notch**，改由 Python 因果 `iirnotch(60Hz, Q=30)` 精準濾除。
  * 原本動作恢復慢（$\tau \approx 10\text{s}$）的 **10µF 大電容 0.1Hz 高通**，建議改為 `1µF` 或直接由 Python `0.5–40Hz` 因果 `sosfilt` 帶通處理。
  * 新增即時 R-peak 心率推算、RR 間期訊號品管（接觸不良 `bad` 時自動免罰以免誤抓）、個人靜息基線差值 `bpm_delta`、以及考前 Rest / MVC 雙層校正。

---

## 3. 實驗三（Exp 3 BrainLink EEG + EOG）即時因果整合

* **純因果即時推論 ([eeg_realtime.py](file:///D:/biomedical_final/Neurocheat_test/bio_bridge/eeg_realtime.py) + `eeg_models.npz`)**：
  * 移除原本離線實驗中的非因果後處理（如 Sinkhorn／Block Voting），改用 4 秒滑動視窗（`512Hz`，2048 點）、0.5 秒步長、38 維生理與眼電特徵及線上 EMA 自適應標準化。
  * 權重統一存成純 NumPy 格式 `eeg_models.npz`，避免不同電腦間的 `pickle` / `scikit-learn` 版本警告。
  * 同步輸出 **專注度 (`focus`)**（控制小抄文字清晰度）、**Stroop 認知負荷 (`stroop`)**（造成考卷題字晃動與干擾色），以及 **Fp1 前額雙眨眼偵測 (`double_blink`)**（免手翻閱第 1/2 頁小抄）。
  * 內建 BrainLink ThinkGear 二進位串口解碼器（`57600 baud`）。
* **多通道融合橋接中心 ([bridge_hub.py](file:///D:/biomedical_final/Neurocheat_test/bio_bridge/bridge_hub.py) + [hardware_bridge.py](file:///D:/biomedical_final/Neurocheat_test/game/hardware_bridge.py))**：
  * 透過 UDP `:5005` 以 `25Hz` 推送整合生理 JSON 至遊戲，並透過 UDP `:5006` 接收遊戲發出的 `CALIB_REST` / `CALIB_MVC` / `CALIB_FOCUS` / `CALIB_DONE` 校正階段指令，以及 `BUZZER_WARN` / `BUZZER_BUSTED` 硬體回饋。
  * 新增遊戲開考 **15 秒個人基線校正精靈**：依序校正「靜息心率＋EMG 零點（5 秒）→ 最大握拳 EMG MVC（5 秒）→ 專注凝視準備（5 秒）」。

---

## 4. 遊戲難度、機制與 AI 升級

* **三階難度模式（於標題畫面點選，預設為「標準期末考」）**：
  * **`EASY` 輕鬆練習**：考試 `115 秒`、寫黑板安全時間 `3.8~6.2 秒`、巡堂最遠走至 `2.95m`、懷疑累計倍率 `0.78`。
  * **`NORMAL` 標準期末考（預設）**：考試 `95 秒`、寫黑板安全時間 `2.3~4.2 秒`、無聲偷襲 `28%`、假動作接回頭 `36%`、走道逼近機率 `52%`（最深可走到 `1.68m`）。
  * **`HARD` 地獄大刀教授**：考試 `80 秒`、寫黑板安全時間 `1.6~3.0 秒`、無聲偷襲 `36%`、假動作接回頭 `50%`、走道逼近機率 `72%`（逼近至桌前 `1.32m`）。
* **奶娃老師 3D 走道逼近與近距離直接抓包 ([teacher.py](file:///D:/biomedical_final/Neurocheat_test/game/teacher.py))**：
  * 老師轉身巡視時會走下右側講台，沿中央走道從講台 `5.05m` 走向前排走道並播放腳步聲（[sound_generator.py](file:///D:/biomedical_final/Neurocheat_test/game/sound_generator.py) 新增 `footstep` 音效）。
  * 當老師已逼近走道近距區（`is_close_aisle()`），不只全開抽屜會被抓，連按住 `F` 微開抽屜縫隙都會立刻觸發抓包！
* **二段假動作陷阱 (`FALSE_ALARM -> SILENT_PEEK`)**：老師放下粉筆做出沒轉身的假動作後，有機會緊接著不響蜂鳴器直接回頭突襲。
* **鄰座時間進度鎖與生理壓力調整 ([exam.py](file:///D:/biomedical_final/Neurocheat_test/game/exam.py)、[bio_signals.py](file:///D:/biomedical_final/Neurocheat_test/game/bio_signals.py))**：
  * 左鄰座阿明（常亂猜）與右鄰座小華（電資學霸）的題目不再開局全數解鎖，改為隨考試進度逐步寫完。
  * 手動模式下專注度改由 `64%` 起跳並隨疲勞／高壓下滑，按住 `R` 進行深呼吸可同時壓低心率與回復專注清晰度。

---

## 5. 「奶娃」角色建模替換、3D 場景與操控視覺改善

* **更換為正版「奶娃」四態去背立繪（[assets/](file:///D:/biomedical_final/Neurocheat_test/assets)）**：
  * 修正先前使用有角有刺的「奶龍」問題，全面換為無角無背鰭無尾、梨形黃身＋米白肚皮＋綠眼眶大眼＋棕褐手腳掌的**奶娃**四段姿勢：
    * `teacher_back.png`：背對黑板舉手寫字
    * `teacher_peek.png`：側身偷瞄（採用實際透明去背圖）
    * `teacher_patrol.png`：戴黑框圓眼鏡、持木教鞭走道巡堂
    * `teacher_laugh.png`：全身捧腹大笑結局立繪（已清理腳底與腿間封閉白底）
  * 介面與提示文字（`ui_renderer.py`、`teacher.py`、`classroom_3d.py`）亦同步更名為 **奶娃老師**。
* **Z-Sort 3D 教室與道具擴充 ([classroom_3d.py](file:///D:/biomedical_final/Neurocheat_test/game/classroom_3d.py))**：
  * 導入 `SceneDrawQueue`（Painter's Algorithm 深度排序 ＋ Lambert 方向光著色 `_shade_rgb`）：製作立體厚度課桌、鐵管桌腳、抽屜凹槽、座椅、8 位低多邊形同學、黑板粉筆槽與板擦、講桌與發亮 3D 筆電、右上方時鐘（避免被狀態列遮擋），以及玩家桌上的 2B 鉛筆、橡皮擦與學生證。
* **文字清晰度提升**：
  * [main.py](file:///D:/biomedical_final/Neurocheat_test/main.py) 啟動 `pygame.init()` 前先啟用 Windows DPI 感知（`SetProcessDpiAwareness(1)`），防止系統縮放使文字發糊。
  * 考卷離線紋理升級為 `1080 × 700` 超取樣＋微軟正黑體粗體（`msjhbd.ttc`）＋ PIL `BICUBIC` 透視投影與髒旗標快取；底欄修正 `< 上一題 [←]`／`下一題 [→] >` 消除方框缺字並居中排列快捷鍵提示。
* **改善鏡頭向下範圍與游標邊緣卡頓**：
  * 取消原本游標一碰到視窗上下邊界就停擺的限制（滑鼠在主視窗水平範圍內即可持續更新上下俯仰），並將向下最大俯視角 `pitch` 由 `-0.56` 放寬至 **`-0.74`**、調整下半部俯仰曲線為 `-0.22 - (ny ** 0.75) * 0.50`。
  * 按住 **`V`** 鍵或將滑鼠移至下方考卷區時攝影機適度降高前傾（`y = 1.15, z = -0.17`），且考卷擺在桌面 `z = 0.20~0.76`，保證題幹、`(A)~(D)` 選項與底部按鈕完整落在畫面內、不再把底部選項切掉。

---

## 6. 組員 Pull 後快速啟動與測試步驟

1. **建立共編虛擬環境（首次執行）**：
   ```powershell
   git pull
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **快速純鍵鼠試玩**：
   * 直接雙擊 [`run_game.bat`](file:///D:/biomedical_final/Neurocheat_test/run_game.bat) 或執行 `.venv\Scripts\python.exe main.py`。
   * 標題畫面可切換「輕鬆練習 / 標準期末考 / 地獄大刀教授」，按 `Enter` 直接開始。
   * 局內可用滑鼠看教室與點答案、按住 **`V`** 傾身放大考卷、**`空白鍵`／右鍵**全開小抄、按住 **`F`** 微縫偷窺、**`Tab`** 翻頁、按住 **`R`** 深呼吸。
3. **無硬體測試 Exp 2 + Exp 3 完整管線**：
   * 先執行 [`run_bridge.bat`](file:///D:/biomedical_final/Neurocheat_test/run_bridge.bat)（選 `1` 純合成雙通道模擬 或 `2` Exp 3 受試者重播）。
   * 再開啟遊戲按 **`F1`** 切換至 `EXTERNAL`，點擊「15 秒基線校正後開考」即可連通完整即時訊號與課後 `sessions/` 報表分析。
