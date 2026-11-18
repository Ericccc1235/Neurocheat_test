"""
exp2_dsp.py - Exp 2 ECG / EMG 即時傳統數位訊號處理與封包解碼模組
===================================================================
落實專題規格與 Exp 2 電路簡化：
1. 以因果 IIR 數位濾波 (60Hz Notch + 0.5-40Hz ECG 帶通) 取代容易溫漂/難調整的類比 Fliege Notch 與大電容 0.1Hz HPF。
2. 即時動態 R-peak 偵測 + RR 間期品管 + 相對開局基線心率增量 (bpm_delta)。
3. 支援雙層校正之 EMG 包絡線正規化 (0.0~1.0) 與遲滯開關 (Hysteresis)。
4. 同時相容：
   - neurocheat_exp2_dual.ino 的 3-byte 自我同步 10-bit ECG + 8-bit EMG 封包
   - Exp 2 原版 arduino_ecg_bluetooth.ino 的 1-byte 200Hz 原始 ECG 串流
"""

from collections import deque
import time
import numpy as np
from scipy import signal


class DualBinaryFrameDecoder:
    """
    解碼 neurocheat_exp2_dual.ino 的 3-byte 自我同步二進位封包：
      Byte 0: 1 | status(2 bits) | ecg10[9:5]   (>= 0x80)
      Byte 1: 0 | ecg10[4:0]     | emg8[7:6]    (< 0x80)
      Byte 2: 0 | 0              | emg8[5:0]    (< 0x40)
    """

    def __init__(self):
        self.buf = bytearray()

    def feed(self, raw_bytes):
        frames = []
        for b in raw_bytes:
            if b & 0x80:
                # 只要遇到 MSB=1 就視為新封包起點，自動從任意掉字恢復同步
                self.buf.clear()
                self.buf.append(b)
            elif len(self.buf) > 0:
                self.buf.append(b)
                if len(self.buf) == 3:
                    b0, b1, b2 = self.buf[0], self.buf[1], self.buf[2]
                    self.buf.clear()
                    status = (b0 >> 5) & 0x03
                    ecg10 = ((b0 & 0x1F) << 5) | ((b1 >> 2) & 0x1F)
                    emg8 = ((b1 & 0x03) << 6) | (b2 & 0x3F)
                    test_mode = bool((status >> 1) & 1)
                    btn_pressed = bool(status & 1)
                    frames.append((ecg10, emg8, test_mode, btn_pressed))
        return frames


class RealtimeECGProcessor:
    """
    即時 ECG 數位濾波、R-peak 心率計算與訊號品質檢查。
    採用有狀態因果濾波 (sosfilt + lfilter zi)，無未來視窗延遲。
    """

    def __init__(self, fs=160.0, adc_max=1023.0, use_notch=True):
        self.fs = float(fs)
        self.adc_max = float(adc_max)
        self.use_notch = bool(use_notch and self.fs > 125.0)

        # 1. 數位 60Hz Notch Filter (取代 Exp 2 類比 Fliege Notch)
        if self.use_notch:
            self.b_notch, self.a_notch = signal.iirnotch(60.0, 30.0, fs=self.fs)
            self.zi_notch = signal.lfilter_zi(self.b_notch, self.a_notch) * 0.0
        else:
            self.b_notch = self.a_notch = self.zi_notch = None

        # 2. 數位 0.5 - 40 Hz 帶通 (取代 Exp 2 大電容 0.1Hz HPF 並保留 QRS 主能量)
        high_cut = min(40.0, self.fs * 0.45)
        self.sos_bp = signal.butter(2, [0.5, high_cut], btype="bandpass", fs=self.fs, output="sos")
        self.zi_bp = signal.sosfilt_zi(self.sos_bp) * 0.0

        self.initialized = False

        # 濾波後緩衝區 (存近 3.5 秒供即時自適應閾值與示波器輸出)
        win_len = int(3.5 * self.fs)
        self.filt_buf = deque([0.0] * win_len, maxlen=win_len)
        self.raw_buf = deque([adc_max * 0.5] * int(self.fs), maxlen=int(self.fs))
        self.out_wave_q = deque(maxlen=int(self.fs))

        # R-peak 追蹤
        self.sample_idx = 0
        self.last_peak_idx = -int(self.fs)
        self.refractory_samples = int(0.32 * self.fs)  # 最高約 187 BPM 不應期
        self.rr_hist = deque(maxlen=8)

        self.bpm = 72.0
        self.bpm_base = 72.0
        self.base_calibrated = False
        self._calib_bpms = []
        self._outlier_streak = 0
        self.bpm_delta = 0.0
        self.quality = "ok"
        self.bad_reason = ""
        self.rail_frac = 0.0
        self.last_ptp = 0.0
        self.raw_v_min = 2.5
        self.raw_v_max = 2.5
        self.last_beat_time = time.time()

    def set_baseline_bpm(self, bpm_base):
        self.bpm_base = float(np.clip(bpm_base, 45.0, 120.0))
        self.base_calibrated = True
        self.bpm_delta = self.bpm - self.bpm_base

    def start_baseline_calibration(self):
        self.base_calibrated = False
        self._calib_bpms = []

    def finish_baseline_calibration(self):
        if self._calib_bpms:
            self.bpm_base = float(np.median(self._calib_bpms))
        else:
            self.bpm_base = float(self.bpm)
        self.base_calibrated = True
        self.bpm_delta = self.bpm - self.bpm_base
        return self.bpm_base

    def process_samples(self, raw_adc_list, now_time=None):
        """輸入一批 ADC 取樣點，回傳 (bpm, bpm_delta, quality, wave_chunk)"""
        if not raw_adc_list:
            return self.bpm, self.bpm_delta, self.quality, []

        if now_time is None:
            now_time = time.time()

        arr = np.asarray(raw_adc_list, dtype=np.float64)
        self.raw_buf.extend(arr.tolist())

        # 以中點為中心正規化至 [-1, +1] 量級，避免直流切換瞬間突波
        centered = (arr - (self.adc_max * 0.5)) / (self.adc_max * 0.5)
        if not self.initialized:
            if self.use_notch:
                self.zi_notch = signal.lfilter_zi(self.b_notch, self.a_notch) * centered[0]
            self.zi_bp = signal.sosfilt_zi(self.sos_bp) * 0.0
            self.initialized = True

        x = centered
        if self.use_notch:
            x, self.zi_notch = signal.lfilter(self.b_notch, self.a_notch, x, zi=self.zi_notch)
        x_bp, self.zi_bp = signal.sosfilt(self.sos_bp, x, zi=self.zi_bp)

        self.filt_buf.extend(x_bp.tolist())

        # 動態偵測 R-peak
        win = np.asarray(self.filt_buf, dtype=np.float64)
        med = float(np.median(win))
        mad = float(np.median(np.abs(win - med))) * 1.4826 + 1e-6
        # 自動判斷 R 波正向或負向 (如導程反接)
        pos_max = float(np.percentile(win, 99.5))
        neg_max = float(np.percentile(-win, 99.5))
        polarity = 1.0 if pos_max >= neg_max else -1.0

        peak_amp = max(pos_max, neg_max)
        # 自適應閾值：須高於雜訊 4 倍 MAD 且大於最小訊號振幅 (避免沒貼電極誤判雜訊為心跳)
        thresh = max(0.035, med * polarity + max(4.2 * mad, 0.42 * peak_amp))

        n = len(x_bp)
        # 逐點檢查局部極大值 (確保即時低延遲)
        prev_v = win[-n - 1] * polarity if len(win) > n else 0.0
        for i in range(n):
            val = x_bp[i] * polarity
            next_v = (x_bp[i + 1] * polarity) if (i + 1 < n) else val
            cur_idx = self.sample_idx + i
            if val > thresh and val >= prev_v and val >= next_v:
                if (cur_idx - self.last_peak_idx) >= self.refractory_samples:
                    if self.last_peak_idx >= 0:
                        rr = (cur_idx - self.last_peak_idx) / self.fs
                        if 0.33 <= rr <= 1.80:  # 33 ~ 181 BPM
                            inst_bpm = 60.0 / rr
                            # 抗單點極端異常值門控（連續 2 次同節律則解鎖切換，避免被初始錯值永久鎖死）
                            if not self.rr_hist or abs(inst_bpm - self.bpm) < 35.0:
                                self._outlier_streak = 0
                                self.rr_hist.append(rr)
                                med_rr = float(np.median(self.rr_hist))
                                smooth_bpm = 60.0 / med_rr
                                self.bpm = 0.72 * self.bpm + 0.28 * smooth_bpm
                                self._calib_bpms.append(self.bpm)
                                self.last_beat_time = now_time
                                if not self.base_calibrated and len(self._calib_bpms) >= 6:
                                    self.bpm_base = float(np.median(self._calib_bpms[:12]))
                                    self.base_calibrated = True
                            else:
                                self._outlier_streak += 1
                                if self._outlier_streak >= 2:
                                    self._outlier_streak = 0
                                    self.rr_hist.clear()
                                    self.rr_hist.append(rr)
                                    self.bpm = inst_bpm
                                    self.last_beat_time = now_time
                    else:
                        self.last_beat_time = now_time
                    self.last_peak_idx = cur_idx
            prev_v = val

        self.sample_idx += n

        # 訊號品質檢查 (飽和 / 脫落 / 嚴重肌電干擾)
        raw_arr = np.asarray(self.raw_buf, dtype=np.float64)
        rail_frac = float(np.mean((raw_arr <= 4.0) | (raw_arr >= self.adc_max - 4.0)))
        ptp = float(np.ptp(win[-int(self.fs):]))
        self.rail_frac = rail_frac
        self.last_ptp = ptp
        self.raw_v_min = float(np.min(raw_arr)) / self.adc_max * 5.0
        self.raw_v_max = float(np.max(raw_arr)) / self.adc_max * 5.0
        no_beat_s = now_time - self.last_beat_time

        if rail_frac > 0.15:
            self.quality = "bad"
            self.bad_reason = f"削頂飽和 rail={rail_frac*100:.0f}%, A0={self.raw_v_min:.2f}~{self.raw_v_max:.2f}V"
        elif ptp < 0.025:
            self.quality = "bad"
            self.bad_reason = f"平線過小 ptp={ptp:.3f}, A0={self.raw_v_min:.2f}~{self.raw_v_max:.2f}V"
        elif no_beat_s > 3.8:
            self.quality = "bad"
            self.bad_reason = f"逾{no_beat_s:.1f}s無合格R波, A0={self.raw_v_min:.2f}~{self.raw_v_max:.2f}V, ptp={ptp:.3f}"
        elif mad > 0.32 * peak_amp and peak_amp > 0.1:
            self.quality = "noisy"
            self.bad_reason = f"雜訊偏高 A0={self.raw_v_min:.2f}~{self.raw_v_max:.2f}V"
        else:
            self.quality = "ok"
            self.bad_reason = ""

        self.bpm_delta = float(self.bpm - self.bpm_base)

        # 正規化輸出給示波器繪圖 (-1.0 ~ +1.0)
        scale = max(0.15, float(np.percentile(np.abs(win), 99.0)) * 1.15)
        wave_norm = np.clip((x_bp * polarity) / scale, -1.2, 1.2).tolist()
        return round(self.bpm, 1), round(self.bpm_delta, 1), self.quality, [round(v, 3) for v in wave_norm]


class RealtimeEMGProcessor:
    """
    即時 EMG 握力校正與遲滯二值化/連續張力處理器。
    支援 0~255 Arduino 包絡線輸入或 0.0~1.0 預處理輸入。
    """

    def __init__(self, input_max=255.0):
        self.input_max = float(input_max)
        self.rest_level = 12.0
        self.mvc_level = 160.0
        self.calibrated = False

        self.rest_samples = []
        self.mvc_samples = []

        self.emg_norm = 0.0
        self.emg_fist = False
        self.on_thresh = 0.32
        self.off_thresh = 0.18

    def record_rest(self, val):
        self.rest_samples.append(float(val))

    def record_mvc(self, val):
        self.mvc_samples.append(float(val))

    def finish_calibration(self):
        if self.rest_samples:
            self.rest_level = float(np.percentile(self.rest_samples, 80))
        if self.mvc_samples:
            p90 = float(np.percentile(self.mvc_samples, 90))
            self.mvc_level = max(self.rest_level + self.input_max * 0.12, p90)
        self.calibrated = True
        self.rest_samples.clear()
        self.mvc_samples.clear()
        return self.rest_level, self.mvc_level

    def process(self, raw_val, btn_override=False):
        val = float(raw_val)
        span = max(1e-3, self.mvc_level - self.rest_level)
        norm = float(np.clip((val - self.rest_level) / span, 0.0, 1.0))

        # 輕微輸出平滑避免滑動條閃爍
        alpha = 0.45 if norm > self.emg_norm else 0.30
        self.emg_norm = (1.0 - alpha) * self.emg_norm + alpha * norm

        if btn_override:
            self.emg_norm = max(self.emg_norm, 0.90)

        # 遲滯閥值判定是否進入握拳看小抄狀態
        if not self.emg_fist and self.emg_norm >= self.on_thresh:
            self.emg_fist = True
        elif self.emg_fist and self.emg_norm <= self.off_thresh and not btn_override:
            self.emg_fist = False

        return round(self.emg_norm, 3), self.emg_fist
