"""
bio_signals.py - 生物電訊號狀態機與整合引擎 (EMG / ECG / EEG)
================================================================
管理三通道生理訊號的雙模態運作（鍵鼠模擬 MANUAL / 硬體串流 EXTERNAL）：
  1. EMG 肌電訊號：支援連續類比握力 (0.0~1.0) 控制抽屜開合幅度、
     微開縫隙偷瞄、以及高出力持續握拳導致的肌肉疲勞/抽筋強制彈回。
  2. ECG 心電訊號：相容真實硬體示波器波形與人工合成 PQRST、
     以開局個人基線 (bpm_base) 計算相對心率增量 (bpm_delta)、
     結合訊號品管 (ok/noisy/bad) 防誤判與深呼吸冷靜光環。
  3. EEG 腦波訊號：專注度 (Focus 0~100%) 決定小抄清晰度、
     Stroop 認知超載指標 (0~100%) 控制高壓閱讀干擾、
     Fp1 雙眨眼 (double_blink) 觸發免手翻頁。
"""

from collections import deque
import math
import random
import threading
import time


class BioSignalManager:
    MODE_MANUAL = "MANUAL"
    MODE_EXTERNAL = "EXTERNAL"

    def __init__(self, initial_mode=MODE_MANUAL):
        self._lock = threading.Lock()
        self.mode = initial_mode
        self.external_source = "未連線"

        # ---------------- EMG 肌肉電位 ----------------
        self.emg_signal_level = 0.0   # 0.0 (完全放鬆) ~ 1.0 (全力握拳)
        self.target_emg = 0.0
        self.emg_clenched = False     # 是否超過基本開啟門檻 (>= 0.22)
        self.emg_fatigue = 0.0        # 0.0 ~ 100.0 %
        self.emg_cramped = False      # 肌肉抽筋鎖定狀態
        self.cramp_timer = 0.0
        self._pending_cramp_slam = False

        # ---------------- ECG 心電圖 ----------------
        self.bpm_base = 72.0
        self.ecg_bpm = 72.0
        self.target_bpm = 72.0
        self.bpm_delta = 0.0
        self.ecg_quality = "ok"       # "ok" | "noisy" | "bad" | "calib"
        self.ecg_stress_threshold = 95.0
        self.deep_breath_active = False
        self.calm_aura = 0.0          # 0.0 ~ 1.0 深呼吸鎮定光環

        self.ecg_wave_buffer = deque([0.0] * 160, maxlen=160)
        self._last_real_ecg_time = 0.0
        self.using_real_ecg_wave = False
        self._synth_phase = 0.0

        # ---------------- EEG 腦波 (Exp 3) ----------------
        self.eeg_focus = 80.0         # 0.0 ~ 100.0 %
        self.target_focus = 80.0
        self.eeg_stroop = 15.0        # 0.0 ~ 100.0 % 認知超載指標
        self.target_stroop = 15.0
        self.eeg_quality = "ok"       # "ok" | "poor" | "calib"

        self.blink_detected = False
        self._pending_double_blink = False
        self._last_double_blink_at = 0.0
        self.cheat_page = 0           # 0: 第 1 頁筆記 / 1: 第 2 頁筆記

        # 外部串流暫存快照
        self._ext_last_rx = 0.0
        self._ext_ecg_queue = deque(maxlen=256)
        self._ext_emg_fist = None

        # 本局統計
        self.max_bpm = 72.0
        self.max_bpm_delta = 0.0

    # ------------------------------------------------------------------
    # 模式切換與局間重置
    # ------------------------------------------------------------------
    def toggle_mode(self):
        if self.mode == self.MODE_MANUAL:
            self.mode = self.MODE_EXTERNAL
        else:
            self.mode = self.MODE_MANUAL
            self.ecg_quality = "ok"
            self.eeg_quality = "ok"
            self.using_real_ecg_wave = False
        return self.mode

    def set_mode(self, mode):
        if mode in (self.MODE_MANUAL, self.MODE_EXTERNAL):
            self.mode = mode

    def reset(self):
        with self._lock:
            self._ext_ecg_queue.clear()
            self._pending_double_blink = False
            self._pending_cramp_slam = False

        self.emg_signal_level = 0.0
        self.target_emg = 0.0
        self.emg_clenched = False
        self.emg_fatigue = 0.0
        self.emg_cramped = False
        self.cramp_timer = 0.0

        self.deep_breath_active = False
        self.calm_aura = 0.0
        self.cheat_page = 0

        if self.mode == self.MODE_MANUAL:
            self.ecg_bpm = self.bpm_base
            self.target_bpm = self.bpm_base
            self.bpm_delta = 0.0
            self.eeg_focus = 64.0
            self.target_focus = 64.0
            self.eeg_stroop = 22.0
            self.target_stroop = 22.0
            self.ecg_quality = "ok"
            self.eeg_quality = "ok"

        self.max_bpm = self.ecg_bpm
        self.max_bpm_delta = max(0.0, self.bpm_delta)

    def set_baseline_bpm(self, bpm):
        self.bpm_base = max(45.0, min(120.0, float(bpm)))
        self.bpm_delta = self.ecg_bpm - self.bpm_base

    # ------------------------------------------------------------------
    # 外部硬體資料寫入 (由 HardwareBridge 背景執行緒呼叫)
    # ------------------------------------------------------------------
    def set_external_signals(
        self,
        ecg_bpm=None,
        bpm_base=None,
        bpm_delta=None,
        ecg_quality=None,
        ecg_samples=None,
        emg_val=None,
        emg_fist=None,
        eeg_focus=None,
        eeg_stroop=None,
        eeg_quality=None,
        blink=None,
        double_blink=None,
        source_label="External",
    ):
        now = time.time()
        with self._lock:
            self.external_source = source_label
            self._ext_last_rx = now

            if bpm_base is not None:
                self.bpm_base = max(45.0, min(120.0, float(bpm_base)))

            if ecg_bpm is not None:
                self.target_bpm = max(40.0, min(180.0, float(ecg_bpm)))

            if bpm_delta is not None and ecg_bpm is None:
                self.target_bpm = max(40.0, min(180.0, self.bpm_base + float(bpm_delta)))

            if ecg_quality is not None:
                self.ecg_quality = ecg_quality

            if ecg_samples:
                for s in ecg_samples:
                    try:
                        self._ext_ecg_queue.append(float(s))
                    except (TypeError, ValueError):
                        pass
                self._last_real_ecg_time = now

            if emg_val is not None:
                self.target_emg = max(0.0, min(1.0, float(emg_val)))
            elif emg_fist is not None:
                self.target_emg = 0.88 if emg_fist else 0.0

            if emg_fist is not None:
                self._ext_emg_fist = bool(emg_fist)

            if eeg_focus is not None:
                self.target_focus = max(0.0, min(100.0, float(eeg_focus)))

            if eeg_stroop is not None:
                self.target_stroop = max(0.0, min(100.0, float(eeg_stroop)))

            if eeg_quality is not None:
                self.eeg_quality = eeg_quality

            if blink is not None:
                self.blink_detected = bool(blink)

            if double_blink:
                # 去彈跳 0.65 秒，避免同一個事件連翻數頁
                if (now - self._last_double_blink_at) >= 0.65:
                    self._pending_double_blink = True
                    self._last_double_blink_at = now

    # ------------------------------------------------------------------
    # 手動鍵鼠控制 API
    # ------------------------------------------------------------------
    def trigger_emg_clench(self, active, level=0.90):
        """SPACE / 右鍵切換全開小抄（MANUAL 模式有效）。"""
        if self.mode == self.MODE_MANUAL:
            self.target_emg = max(0.0, min(1.0, float(level))) if active else 0.0

    def set_manual_peek(self, active, peek_level=0.42):
        """按住 F 鍵微開抽屜縫隙（MANUAL 模式有效）。"""
        if self.mode == self.MODE_MANUAL:
            self.target_emg = float(peek_level) if active else 0.0

    def set_deep_breath(self, active):
        if self.mode == self.MODE_MANUAL:
            self.deep_breath_active = bool(active)

    def flip_cheat_page(self):
        self.cheat_page = 1 - self.cheat_page
        return self.cheat_page

    def consume_double_blink(self):
        with self._lock:
            triggered = self._pending_double_blink
            self._pending_double_blink = False
        return triggered

    def consume_cramp_slam(self):
        triggered = self._pending_cramp_slam
        self._pending_cramp_slam = False
        return triggered

    def adjust_manual(self, d_bpm=0.0, d_focus=0.0, d_stroop=0.0):
        if self.mode == self.MODE_MANUAL:
            self.target_bpm = max(55.0, min(155.0, self.target_bpm + d_bpm))
            self.target_focus = max(5.0, min(100.0, self.target_focus + d_focus))
            self.target_stroop = max(0.0, min(100.0, self.target_stroop + d_stroop))

    # ------------------------------------------------------------------
    # 每幀更新
    # ------------------------------------------------------------------
    def update(self, dt, teacher_alert_level=0.0, teacher_facing_player=False, peeking_neighbor=False):
        dt = max(0.001, min(0.1, dt))

        # 讀取外部執行緒資料
        with self._lock:
            pending_wave = list(self._ext_ecg_queue)
            self._ext_ecg_queue.clear()
            last_real_ecg = self._last_real_ecg_time
            ext_emg_fist = self._ext_emg_fist

        # 1. MANUAL 模式動態生理回饋
        if self.mode == self.MODE_MANUAL:
            in_danger = (self.emg_clenched or peeking_neighbor) and (
                teacher_alert_level > 0.30 or teacher_facing_player
            )
            if self.deep_breath_active and not self.emg_clenched:
                self.target_bpm = max(self.bpm_base - 4.0, self.target_bpm - 12.5 * dt)
                self.target_stroop = max(8.0, self.target_stroop - 20.0 * dt)
                self.target_focus = min(92.0, self.target_focus + 8.5 * dt)
            elif in_danger:
                self.target_bpm = min(152.0, self.target_bpm + 19.0 * dt)
                self.target_stroop = min(95.0, self.target_stroop + 16.0 * dt)
                self.target_focus = max(24.0, self.target_focus - 6.5 * dt)
            elif self.emg_clenched or peeking_neighbor:
                # 作弊偷窺時緊張心跳略升且注意力隨疲勞消耗
                self.target_bpm = min(115.0, self.target_bpm + 5.5 * dt)
                self.target_stroop = min(82.0, self.target_stroop + 5.5 * dt)
                self.target_focus = max(34.0, self.target_focus - 2.6 * dt)
            else:
                # 緩慢自然回落至基線心率，專注力若未練習會微幅下滑
                self.target_bpm += (self.bpm_base - self.target_bpm) * min(1.0, 0.30 * dt)
                self.target_stroop += (20.0 - self.target_stroop) * min(1.0, 0.25 * dt)
                self.target_focus = max(48.0, self.target_focus - 1.1 * dt)

            if self.emg_fatigue >= 72.0:
                self.target_stroop = min(96.0, self.target_stroop + 7.5 * dt)
        else:
            # EXTERNAL 模式：當心跳回落至基線以下且未緊握或超載時，自動亮起生理深呼吸光環
            self.deep_breath_active = (
                self.ecg_quality == "ok"
                and self.bpm_delta <= -2.0
                and self.eeg_focus >= 52.0
                and not self.emg_clenched
            )

        # 2. 平滑插值 ECG & EEG
        self.ecg_bpm += (self.target_bpm - self.ecg_bpm) * min(1.0, 5.0 * dt)
        self.bpm_delta = self.ecg_bpm - self.bpm_base
        self.eeg_focus += (self.target_focus - self.eeg_focus) * min(1.0, 6.0 * dt)
        self.eeg_stroop += (self.target_stroop - self.eeg_stroop) * min(1.0, 5.0 * dt)

        # 更新深呼吸冷靜光環 (0~1)
        aura_target = 1.0 if self.deep_breath_active else 0.0
        self.calm_aura += (aura_target - self.calm_aura) * min(1.0, 3.5 * dt)

        # 紀錄最大峰值
        if self.ecg_quality != "bad":
            self.max_bpm = max(self.max_bpm, self.ecg_bpm)
            self.max_bpm_delta = max(self.max_bpm_delta, self.bpm_delta)

        # 3. EMG 肌肉張力、疲勞與抽筋物理
        if self.emg_cramped:
            self.cramp_timer -= dt
            self.emg_signal_level += (0.0 - self.emg_signal_level) * min(1.0, 18.0 * dt)
            self.emg_fatigue = max(0.0, self.emg_fatigue - 24.0 * dt)
            if self.cramp_timer <= 0.0 and self.emg_fatigue <= 35.0:
                self.emg_cramped = False
        else:
            eff_target = self.target_emg
            self.emg_signal_level += (eff_target - self.emg_signal_level) * min(1.0, 14.0 * dt)

            # 疲勞累積：微開縫隙 (<= 0.45) 幾乎不累，全開抓紙 (> 0.50) 持續累積疲勞
            if self.emg_signal_level > 0.50:
                effort = (self.emg_signal_level - 0.42) / 0.58
                self.emg_fatigue = min(100.0, self.emg_fatigue + 14.5 * effort * dt)
                if self.emg_fatigue >= 100.0:
                    self.emg_cramped = True
                    self.cramp_timer = 2.6
                    self._pending_cramp_slam = True
                    if self.mode == self.MODE_MANUAL:
                        self.target_emg = 0.0
            elif self.emg_signal_level < 0.22:
                self.emg_fatigue = max(0.0, self.emg_fatigue - 20.0 * dt)
            else:
                # 微開懸停時極慢恢復
                self.emg_fatigue = max(0.0, self.emg_fatigue - 4.0 * dt)

        # 判定抽屜是否開啟 (>= 0.22 即有微縫；若外部明確給 emg_fist=False 且類比值小於 0.28 則關閉)
        if self.emg_cramped:
            self.emg_clenched = False
        elif self.mode == self.MODE_EXTERNAL and ext_emg_fist is not None:
            self.emg_clenched = (self.emg_signal_level >= 0.22) or ext_emg_fist
        else:
            self.emg_clenched = self.emg_signal_level >= 0.22

        # 4. 更新 ECG 示波器波形 (優先使用真實硬體樣本，超時 1.5s 改回合成 PQRST)
        now = time.time()
        if self.mode == self.MODE_EXTERNAL and pending_wave:
            for sample in pending_wave:
                self.ecg_wave_buffer.append(float(sample))
            self.using_real_ecg_wave = True
        elif self.mode == self.MODE_EXTERNAL and (now - last_real_ecg) < 1.5:
            self.using_real_ecg_wave = True
        else:
            self.using_real_ecg_wave = False
            self._append_synthetic_pqrst(dt)

    def _append_synthetic_pqrst(self, dt):
        """依目前心率產生擬真 P-QRS-T 波形供示波器顯示（僅作無實機波形時後備）。"""
        freq = max(0.6, self.ecg_bpm / 60.0)
        steps = max(1, int(round(dt * 120.0)))
        step_dt = dt / steps
        for _ in range(steps):
            self._synth_phase = (self._synth_phase + freq * step_dt) % 1.0
            p = self._synth_phase
            # P wave (~0.12), Q (~0.21), R spike (~0.25), S (~0.29), T wave (~0.48)
            val = (
                0.14 * math.exp(-((p - 0.12) / 0.032) ** 2)
                - 0.18 * math.exp(-((p - 0.21) / 0.012) ** 2)
                + 1.05 * math.exp(-((p - 0.25) / 0.013) ** 2)
                - 0.30 * math.exp(-((p - 0.29) / 0.014) ** 2)
                + 0.26 * math.exp(-((p - 0.48) / 0.055) ** 2)
                + random.uniform(-0.02, 0.02)
            )
            self.ecg_wave_buffer.append(round(val, 3))

    # ------------------------------------------------------------------
    # UI / Gameplay 讀取介面
    # ------------------------------------------------------------------
    def get_drawer_open_ratio(self):
        """回傳抽屜拉出比例 (0.0~1.0)。微開約 0.35~0.55，全開 0.85~1.0。"""
        if self.emg_cramped or not self.emg_clenched:
            return 0.0
        return max(0.0, min(1.0, self.emg_signal_level))

    def get_cheat_opacity_and_blur(self):
        """
        根據 EEG 專注度與握力開度，回傳 (alpha 30~255, blur_radius 0.0~4.5, focus_pct, stroop_pct)。
        """
        focus = max(0.0, min(100.0, self.eeg_focus))
        stroop = max(0.0, min(100.0, self.eeg_stroop))

        if focus >= 72.0:
            alpha = 255
            blur = 0.0
        elif focus >= 42.0:
            t = (focus - 42.0) / 30.0
            alpha = int(125 + 130 * t)
            blur = round((1.0 - t) * 2.4, 2)
        else:
            t = focus / 42.0
            alpha = int(35 + 90 * t)
            blur = round(2.4 + (1.0 - t) * 2.2, 2)

        return alpha, blur, focus, stroop

    def get_stroop_overload(self):
        """回傳 Stroop 認知超載干擾強度 (0.0~1.0)，低於 50% 不產生負面干擾。"""
        if self.eeg_stroop <= 50.0:
            return 0.0
        return min(1.0, (self.eeg_stroop - 50.0) / 45.0)
