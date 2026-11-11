"""
NeuroCheat 生理訊號管理模組 (BioSignals)
涵蓋雙模式支援：
- 模式一 ("MANUAL" 手動調控模式)：玩家可自己透過按鍵/螢幕按鈕調控 ECG (心率)、EEG (專注度) 與 EMG (握拳開小抄)
- 模式二 ("EXTERNAL" 外部訊號模式)：ECG 與 EEG 必須由外部硬體/外部程式輸入 (Serial COM 埠 / UDP Socket / JSON)，鎖定手動調控；EMG 維持按鈕控制 (亦相容外部觸發)
"""

import math
import collections
import random
import time
import pygame

class BioSignalManager:
    MODE_MANUAL = "MANUAL"      # 手動調控模式 (可自己調控 ECG, EEG, EMG)
    MODE_EXTERNAL = "EXTERNAL"  # 外部訊號模式 (必須從外部輸入 ECG, EEG 訊號)

    def __init__(self, sound_manager=None, mode=MODE_MANUAL):
        self.sound_manager = sound_manager
        self.mode = mode
        self.buffer_size = 300
        self.ecg_wave = collections.deque([0.0] * self.buffer_size, maxlen=self.buffer_size)
        
        # 外部訊號連線狀態追蹤
        self.external_source_name = "尚未收到訊號"
        self.last_external_time = 0.0
        self.external_packet_count = 0

        self.reset(keep_mode=True)

    def reset(self, keep_mode=True):
        """重置生理訊號狀態 (重新開始遊戲時保留目前選擇的模式與硬體參照)"""
        if not keep_mode:
            self.mode = self.MODE_MANUAL

        # --- 1. EMG 握拳/按鈕狀態 (以按鈕代替手部用力) ---
        self.emg_active = False       # True 表示用力按住按鈕（打開小抄）
        self.emg_signal_level = 0.0   # 0.0 ~ 1.0 (模擬肌電振幅)

        # --- 2. EEG 專注度 (0 ~ 100%) ---
        self.eeg_focus = 75.0         # 初始專注度 75%
        self.eeg_target_focus = 75.0
        self.eeg_phase = 0.0

        # --- 3. ECG 心率與緊張程度 ---
        # 【Bug 修正】新增 base_bpm 儲存手動設定的基準心率，避免在 update() 中被 70.0 強制覆蓋！
        self.base_bpm = 72.0          # 基準心率 72 BPM
        self.ecg_bpm = 72.0           # 當前顯示心率
        self.ecg_target_bpm = 72.0
        self.is_deep_breathing = False

        # 清空並初始化心電圖波形緩衝區
        self.ecg_wave.clear()
        self.ecg_wave.extend([0.0] * self.buffer_size)
        self.beat_phase = 0.0

    def set_mode(self, mode):
        """切換模式 ('MANUAL' 或 'EXTERNAL')"""
        if mode in (self.MODE_MANUAL, self.MODE_EXTERNAL):
            self.mode = mode
            self.is_deep_breathing = False

    def is_external_mode(self):
        return self.mode == self.MODE_EXTERNAL

    def is_external_signal_active(self):
        """檢查最近 3 秒內是否有收到外部 ECG/EEG 訊號"""
        return (time.time() - self.last_external_time) < 3.0

    def trigger_emg(self, is_pressed):
        """控制小抄開闔（以按鈕代替握拳，兩種模式皆可使用按鈕觸發）"""
        if is_pressed and not self.emg_active:
            if self.sound_manager:
                self.sound_manager.play_paper()
        self.emg_active = bool(is_pressed)

    def toggle_emg(self):
        """切換小抄開闔狀態 (Toggle 切換開/關)"""
        self.trigger_emg(not self.emg_active)

    def adjust_bpm(self, delta):
        """
        手動調整心率 BPM (僅限 MANUAL 手動調控模式)
        回傳 True 代表調整成功，False 代表目前為外部訊號模式已鎖定
        """
        if self.mode == self.MODE_EXTERNAL:
            return False
        # 【Bug 修正】同時更新 base_bpm 與 ecg_bpm，確保不會在下一幀自動衰減回 70 BPM
        self.base_bpm = max(45.0, min(170.0, self.base_bpm + delta))
        self.ecg_bpm = max(45.0, min(170.0, self.ecg_bpm + delta))
        self.ecg_target_bpm = self.ecg_bpm
        return True

    def adjust_focus(self, delta):
        """
        手動調整 EEG 專注度 (僅限 MANUAL 手動調控模式)
        回傳 True 代表調整成功，False 代表目前為外部訊號模式已鎖定
        """
        if self.mode == self.MODE_EXTERNAL:
            return False
        # 【Bug 修正】立即同步更新 eeg_target_focus 與 eeg_focus，消除畫面與反饋數值延遲
        self.eeg_target_focus = max(5.0, min(100.0, self.eeg_target_focus + delta))
        self.eeg_focus = self.eeg_target_focus
        return True

    def set_deep_breathing(self, active):
        """深呼吸冷靜 (僅限 MANUAL 手動調控模式)"""
        if self.mode == self.MODE_EXTERNAL:
            self.is_deep_breathing = False
            return False
        self.is_deep_breathing = bool(active)
        return True

    def set_external_signals(self, ecg=None, eeg=None, emg=None, source="External"):
        """
        由外部硬體橋接器 (Serial / UDP / JSON) 注入即時生理訊號
        - ecg: 心率 BPM (40 ~ 180)
        - eeg: 腦波專注度 % (0 ~ 100)
        - emg: 選填，握拳狀態 (0 或 1)
        """
        updated = False
        if ecg is not None:
            val_ecg = max(40.0, min(180.0, float(ecg)))
            self.ecg_bpm = val_ecg
            self.base_bpm = val_ecg
            self.ecg_target_bpm = val_ecg
            updated = True

        if eeg is not None:
            val_eeg = max(0.0, min(100.0, float(eeg)))
            self.eeg_focus = val_eeg
            self.eeg_target_focus = val_eeg
            updated = True

        if emg is not None:
            is_active = bool(float(emg) > 0.5)
            if is_active != self.emg_active:
                self.trigger_emg(is_active)
            updated = True

        if updated:
            self.last_external_time = time.time()
            self.external_source_name = source
            self.external_packet_count += 1

    def update(self, dt, teacher_alert=False):
        """每幀更新生理訊號狀態與示波器波形"""
        # 1. 更新 EMG 模擬電位 (平滑舉起/放下手臂)
        target_emg = 1.0 if self.emg_active else 0.0
        self.emg_signal_level += (target_emg - self.emg_signal_level) * min(1.0, dt * 15)

        # 2. 根據模式更新 EEG 與 ECG 數值
        if self.mode == self.MODE_MANUAL:
            # --- 模式一：手動調控模式 ---
            # EEG 專注度：以玩家設定的 eeg_target_focus 為中心，帶極微小自然腦波浮動
            noise = (random.random() - 0.5) * 0.8
            self.eeg_focus += (self.eeg_target_focus - self.eeg_focus) * min(1.0, dt * 8) + noise * dt
            self.eeg_focus = max(5.0, min(100.0, self.eeg_focus))

            # ECG 心率：以玩家設定的 base_bpm 為基準，疊加開小抄/警報緊張加成
            stress_boost = 0.0
            if self.emg_active:
                stress_boost += 22.0  # 作弊時心跳上升
            if teacher_alert:
                stress_boost += 28.0  # 老師警戒時心跳上升

            if self.is_deep_breathing:
                # 深呼吸冷靜時，基準心率與當前心率皆平緩下降至 65 BPM
                self.base_bpm += (65.0 - self.base_bpm) * min(1.0, dt * 3.0)
                target = 65.0
                rate = 4.5
            else:
                target = self.base_bpm + stress_boost
                rate = 2.5 if target > self.ecg_bpm else 1.8

            self.ecg_bpm += (target - self.ecg_bpm) * min(1.0, dt * rate)
            self.ecg_bpm = max(45.0, min(170.0, self.ecg_bpm))
        else:
            # --- 模式二：外部訊號輸入模式 ---
            # ECG 與 EEG 完全由 set_external_signals() 外部訊號決定，不進行內部自動增減覆寫
            self.ecg_bpm = max(40.0, min(180.0, self.ecg_bpm))
            self.eeg_focus = max(0.0, min(100.0, self.eeg_focus))

        # 3. 生成 ECG P-Q-R-S-T 即時示波器波形 (依據當前 ecg_bpm 動態變化頻率)
        cycle_duration = 60.0 / max(40.0, self.ecg_bpm)
        self.beat_phase += dt / cycle_duration

        while self.beat_phase >= 1.0:
            self.beat_phase -= 1.0
            if self.sound_manager and (self.ecg_bpm > 95 or random.random() < 0.3):
                self.sound_manager.play_heartbeat()

        p = self.beat_phase
        val = 0.0

        # P 波 (心房去極化)
        if 0.12 <= p <= 0.22:
            val += 0.18 * math.sin((p - 0.12) / 0.10 * math.pi)
        # Q 波 (心室去極化起始)
        elif 0.32 <= p <= 0.35:
            val -= 0.15 * math.sin((p - 0.32) / 0.03 * math.pi)
        # R 波 (心室去極化主峰)
        elif 0.35 <= p <= 0.40:
            val += 1.00 * math.sin((p - 0.35) / 0.05 * math.pi)
        # S 波 (心室去極化末期)
        elif 0.40 <= p <= 0.44:
            val -= 0.35 * math.sin((p - 0.40) / 0.04 * math.pi)
        # T 波 (心室再極化)
        elif 0.55 <= p <= 0.72:
            val += 0.28 * math.sin((p - 0.55) / 0.17 * math.pi)

        baseline = 0.03 * math.sin(pygame.time.get_ticks() * 0.003)
        self.ecg_wave.append(val + baseline)

    def get_cheat_opacity_and_blur(self):
        """
        根據 EEG 專注度計算小抄的透明度 (0-255) 與清晰度描述
        - 專注度 <= 25%：完全隱形/透明 (alpha <= 8)，無法辨識
        - 專注度 50%：微弱半透明 (alpha ~ 80)
        - 專注度 >= 85%：全飽和完全不透明 (alpha = 255)
        """
        if self.eeg_focus <= 25.0:
            alpha = int((self.eeg_focus / 25.0) * 8)
        else:
            norm = (self.eeg_focus - 25.0) / 60.0
            norm = min(1.0, max(0.0, norm))
            alpha = int(8 + (norm ** 1.3) * 247)

        alpha = max(0, min(255, alpha))

        if self.eeg_focus >= 80:
            clarity = "極度清晰 (100% 不透明)"
        elif self.eeg_focus >= 55:
            clarity = "清晰可讀 (良好)"
        elif self.eeg_focus >= 35:
            clarity = "渙散半透明 (勉強)"
        else:
            clarity = "近乎隱形 (完全看不清)"

        return alpha, clarity
