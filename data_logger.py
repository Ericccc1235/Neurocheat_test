"""
NeuroCheat 生醫數據記錄模組 (Bio Data Logger)
生醫工程期末專題核心功能：
記錄遊玩過程中的 ECG、EEG、EMG 數據與事件，並在結束時導出 CSV 與繪製趨勢圖
"""

import time
import os
import csv

class BioDataLogger:
    def __init__(self):
        self.records = []  # 存儲 (time_sec, bpm, focus, emg_active, teacher_alert)
        self.start_time = 0.0
        self.last_record_time = 0.0
        self.record_interval = 0.25  # 每 0.25 秒記錄一筆數據 (4 Hz)
        self.active = False

    def start(self):
        self.records = []
        self.start_time = time.time()
        self.last_record_time = 0.0
        self.active = True

    def update(self, current_game_time, bio_signals, teacher):
        if not self.active:
            return

        now = time.time()
        if now - self.last_record_time >= self.record_interval:
            self.last_record_time = now
            elapsed = round(now - self.start_time, 2)
            
            entry = {
                "elapsed_sec": elapsed,
                "game_time_left": round(current_game_time, 1),
                "ecg_bpm": round(bio_signals.ecg_bpm, 1),
                "eeg_focus": round(bio_signals.eeg_focus, 1),
                "emg_active": 1 if bio_signals.emg_active else 0,
                "teacher_alert": 1 if teacher.buzzer_active or teacher.facing_player else 0
            }
            self.records.append(entry)

    def export_csv(self, filename="neurocheat_session_data.csv"):
        """將生理訊號歷史數據導出為標準 CSV，供後續 Python / Matlab / Excel 生醫數據分析"""
        if not self.records:
            return None

        try:
            filepath = os.path.abspath(filename)
            with open(filepath, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "elapsed_sec", "game_time_left", "ecg_bpm", "eeg_focus", "emg_active", "teacher_alert"
                ])
                writer.writeheader()
                for row in self.records:
                    writer.writerow(row)
            print(f"[BioDataLogger] 生醫訊號數據已成功導出至: {filepath}")
            return filepath
        except Exception as e:
            print(f"[BioDataLogger] 導出 CSV 失敗: {e}")
            return None
