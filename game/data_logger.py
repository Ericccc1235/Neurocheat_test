"""
data_logger.py - 生醫訊號與考試遊戲遙測記錄器
==============================================
每 0.25 秒擷取一筆 ECG / EMG / EEG 與監考狀態至記憶體，
並在結算時匯出至 sessions/neurocheat_session_data.csv 供課後圖表分析。
"""

import csv
import os


class BioDataLogger:
    """記錄完整局內生理訊號與事件時間軸。"""

    FIELDNAMES = [
        "time",
        "ecg_bpm",
        "bpm_base",
        "bpm_delta",
        "ecg_quality",
        "emg_level",
        "emg_fatigue",
        "emg_clenched",
        "eeg_focus",
        "eeg_stroop",
        "eeg_quality",
        "suspicion",
        "teacher_alert",
        "teacher_state",
        "cheat_page",
        "peek_side",
        "close_calls",
        "exam_score",
    ]

    def __init__(self, record_interval=0.25):
        self.record_interval = record_interval
        self.elapsed = 0.0
        self.accum = 0.0
        self.records = []

    def reset(self):
        self.elapsed = 0.0
        self.accum = 0.0
        self.records.clear()

    def update(self, dt, bio_signals, teacher, exam, peek_side=None):
        self.elapsed += dt
        self.accum += dt
        if self.accum < self.record_interval:
            return
        self.accum -= self.record_interval

        self.records.append(
            {
                "time": round(self.elapsed, 2),
                "ecg_bpm": round(bio_signals.ecg_bpm, 2),
                "bpm_base": round(bio_signals.bpm_base, 2),
                "bpm_delta": round(bio_signals.bpm_delta, 2),
                "ecg_quality": bio_signals.ecg_quality,
                "emg_level": round(bio_signals.emg_signal_level, 3),
                "emg_fatigue": round(bio_signals.emg_fatigue, 1),
                "emg_clenched": int(bool(bio_signals.emg_clenched)),
                "eeg_focus": round(bio_signals.eeg_focus, 1),
                "eeg_stroop": round(bio_signals.eeg_stroop, 1),
                "eeg_quality": bio_signals.eeg_quality,
                "suspicion": round(teacher.suspicion, 1),
                "teacher_alert": round(teacher.get_alert_level(), 2),
                "teacher_state": teacher.state.name,
                "cheat_page": bio_signals.cheat_page + 1,
                "peek_side": peek_side or "none",
                "close_calls": teacher.close_calls,
                "exam_score": exam.calculate_score(),
            }
        )

    def export_csv(self, filepath=None):
        if filepath is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sess_dir = os.path.join(project_root, "sessions")
            os.makedirs(sess_dir, exist_ok=True)
            filepath = os.path.join(sess_dir, "neurocheat_session_data.csv")
        else:
            parent = os.path.dirname(os.path.abspath(filepath))
            if parent:
                os.makedirs(parent, exist_ok=True)

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES)
            writer.writeheader()
            writer.writerows(self.records)
        return filepath
