"""
eeg_realtime.py - Exp 3 即時因果腦波分類、認知過載 (Stroop) 與眨眼偵測模組
=============================================================================
特色：
1. 完全因果線上推論 (移除 Exp 3 離線 LOSO 的 Sinkhorn / Block Voting 非因果後處理)，
   改以滑動視窗 (4 秒窗 / 0.5 秒步長) + 線上 EMA 自適應標準化 + 考前暖身校正。
2. 直接載入純 NumPy 權重包 eeg_models.npz (Zero pickle version warnings，跨電腦共編零風險)。
3. 同時輸出：
   - focus  (0~100): 專注度機率 (驅動小抄清晰度)
   - stroop (0~100): 認知負荷 / 緊張過載機率 (驅動考卷心理壓迫幹擾)
   - blink / double_blink: Fp1 前額單通道即時眨眼尖峰偵測 (支援免手翻頁小抄)
4. 內建 ThinkGear 二進位串口解碼器 (57600 baud BrainLink Lite / Pro)。
"""

import os
import time
from collections import deque
import numpy as np
from scipy import signal

FS = 512
WIN = 4 * FS  # 2048 點 = 4 秒視窗

DEFAULT_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eeg_models.npz")

_BN, _AN = signal.iirnotch(60.0, 30.0, fs=FS)
_BANDS = {
    "sub_de": (0.5, 2),
    "de": (2, 4),
    "th": (4, 8),
    "lo_al": (8, 10),
    "hi_al": (10, 13),
    "smr": (12, 15),
    "lb": (15, 20),
    "hb": (20, 30),
    "ga": (30, 45),
}
_FILT_LO = signal.butter(4, [0.5, 7.0], btype="band", fs=FS, output="sos")
_FILT_AL = signal.butter(4, [8.0, 13.0], btype="band", fs=FS, output="sos")
_FILT_BE = signal.butter(4, [13.0, 30.0], btype="band", fs=FS, output="sos")

# 即時眨眼低通/帶通 (狀態化因果濾波)
_BLINK_SOS = signal.butter(2, [0.8, 6.5], btype="band", fs=FS, output="sos")


def _mad(v):
    return 1.4826 * float(np.median(np.abs(v - np.median(v)))) + 1e-9


def extract_38_features(seg):
    """從單一 4 秒腦波視窗 (2048 點 @ 512Hz) 萃取 38 維生理與眼電特徵。"""
    x = signal.filtfilt(_BN, _AN, seg - np.mean(seg))
    f, p = signal.welch(x, FS, nperseg=min(1024, len(x)))
    bp = np.array([p[(f >= lo) & (f < hi)].mean() for lo, hi in _BANDS.values()]) + 1e-12
    lb = np.log(bp)
    rel = lb - np.log(bp.sum())

    mask = (f >= 0.5) & (f <= 45.0)
    p_norm = p[mask] / (p[mask].sum() + 1e-12)
    freqs = f[mask]
    spec_ent = float(-np.sum(p_norm * np.log(p_norm + 1e-12)))
    centroid = float(np.sum(freqs * p_norm))
    sef90 = float(freqs[min(len(freqs) - 1, int(np.searchsorted(np.cumsum(p_norm), 0.90)))])

    dx = np.diff(x)
    ddx = np.diff(dx)
    var_x = float(np.var(x) + 1e-12)
    var_dx = float(np.var(dx) + 1e-12)
    var_ddx = float(np.var(ddx) + 1e-12)
    mobility = float(np.sqrt(var_dx / var_x))
    complexity = float(np.sqrt(var_ddx / var_dx) / (mobility + 1e-9))

    lo = signal.sosfiltfilt(_FILT_LO, x)
    al = signal.sosfiltfilt(_FILT_AL, x)
    be = signal.sosfiltfilt(_FILT_BE, x)
    s_lo, s_al, s_be = _mad(lo), _mad(al), _mad(be)

    lo_max_mad = float(np.log(np.max(np.abs(lo)) / s_lo))
    lo_std_mad = float(np.log((np.std(lo) + 1e-9) / s_lo))
    lo_pk3 = len(signal.find_peaks(np.abs(lo), height=3.0 * s_lo, distance=FS // 5)[0]) / 4.0
    lo_kurt = float(np.log(np.mean(((lo - lo.mean()) / (lo.std() + 1e-9)) ** 4) + 1e-9))

    env_al = np.abs(signal.hilbert(al))
    al_cv = float(env_al.std() / (env_al.mean() + 1e-9))
    al_q75_q25 = float(
        np.log((np.percentile(env_al, 75) + 1e-9) / (np.percentile(env_al, 25) + 1e-9))
    )

    zcr = float(((x[:-1] * x[1:]) < 0).mean())
    r_al_be = float(np.log(s_al / s_be))
    r_lo_al_hi_al = float(lb[3] - lb[4])
    r_al_hb = float((lb[3] + lb[4]) / 2.0 - lb[7])
    r_th_be = float(lb[2] - lb[7])

    return np.concatenate(
        [
            lb,
            rel,
            [
                spec_ent,
                centroid,
                sef90,
                np.log(var_x),
                mobility,
                complexity,
                lo_max_mad,
                lo_std_mad,
                lo_pk3,
                lo_kurt,
                np.log(s_lo),
                np.log(s_al),
                np.log(s_be),
                al_cv,
                al_q75_q25,
                zcr,
                r_al_be,
                r_lo_al_hi_al,
                r_al_hb,
                r_th_be,
            ],
        ]
    )


class ThinkGearStreamDecoder:
    """
    解析 NeuroSky / BrainLink 標準 ThinkGear 二進位串流 (57600 baud):
      Sync: 0xAA 0xAA <len> <payload...> <checksum>
      Code 0x80 (len 2): 16-bit signed big-endian Raw EEG @ 512Hz
      Code 0x02: PoorSignal (0=佳, 200=離頭)
      Code 0x04: eSense Attention (0~100)
      Code 0x05: eSense Meditation (0~100)
    若偵測不到 0xAA 0xAA，也可搭配 ASCII 浮點數列模式讀取。
    """

    def __init__(self):
        self.state = "SYNC1"
        self.plen = 0
        self.payload = bytearray()
        self.poor_signal = 0
        self.attention = None
        self.meditation = None
        self.packet_ok_count = 0

    def feed(self, raw_bytes):
        raw_samples = []
        for b in raw_bytes:
            if self.state == "SYNC1":
                if b == 0xAA:
                    self.state = "SYNC2"
            elif self.state == "SYNC2":
                if b == 0xAA:
                    self.state = "LEN"
                else:
                    self.state = "SYNC1"
            elif self.state == "LEN":
                if b == 0xAA:
                    continue
                if b > 169:
                    self.state = "SYNC1"
                else:
                    self.plen = b
                    self.payload.clear()
                    self.state = "CHK" if b == 0 else "PAYLOAD"
            elif self.state == "PAYLOAD":
                self.payload.append(b)
                if len(self.payload) >= self.plen:
                    self.state = "CHK"
            elif self.state == "CHK":
                expected = (~sum(self.payload)) & 0xFF
                if b == expected:
                    self.packet_ok_count += 1
                    self._parse_payload(self.payload, raw_samples)
                self.state = "SYNC1"
        return raw_samples

    def _parse_payload(self, pl, raw_samples):
        i = 0
        n = len(pl)
        while i < n:
            while i < n and pl[i] == 0x55:
                i += 1
            if i >= n:
                break
            code = pl[i]
            i += 1
            if code >= 0x80:
                if i >= n:
                    break
                vlen = pl[i]
                i += 1
                if i + vlen > n:
                    break
                if code == 0x80 and vlen == 2:
                    raw = (pl[i] << 8) | pl[i + 1]
                    if raw >= 32768:
                        raw -= 65536
                    raw_samples.append(float(raw))
                i += vlen
            else:
                if i >= n:
                    break
                val = pl[i]
                i += 1
                if code == 0x02:
                    self.poor_signal = val
                elif code == 0x04:
                    self.attention = val
                elif code == 0x05:
                    self.meditation = val


class CausalEEGDecoder:
    """
    Exp 3 因果即時 EEG 解碼器 (支援 _GLOBAL_ 自適應或 S01~S21 個人模型)：
    - 輸出 focus (0~100%), stroop (0~100%), eeg_quality, blink / double_blink
    """

    def __init__(self, subject_id="_GLOBAL_", model_path=DEFAULT_MODEL_PATH, step_s=0.5, smooth_len=5):
        self.subject_id = subject_id or "_GLOBAL_"
        self.step = int(step_s * FS)
        self.buf = deque(maxlen=WIN)
        self.since = 0

        self.has_model = False
        self.w2 = None
        self.b2 = 0.0
        self.mu = np.zeros(38, dtype=np.float64)
        self.sd = np.ones(38, dtype=np.float64)
        self.W3 = None
        self.b3 = np.zeros(3, dtype=np.float64)
        self.mu3 = np.zeros(38, dtype=np.float64)
        self.sd3 = np.ones(38, dtype=np.float64)

        if os.path.exists(model_path):
            try:
                npz = np.load(model_path, allow_pickle=False)
                sid = self.subject_id if f"{self.subject_id}__w2" in npz.files else "_GLOBAL_"
                self.subject_id = sid
                self.w2 = npz[f"{sid}__w2"].astype(np.float64)
                self.b2 = float(npz[f"{sid}__b2"][0])
                self.mu = npz[f"{sid}__mu"].astype(np.float64)
                self.sd = npz[f"{sid}__sd"].astype(np.float64)
                if f"{sid}__W3" in npz.files:
                    self.W3 = npz[f"{sid}__W3"].astype(np.float64)
                    self.b3 = npz[f"{sid}__b3"].astype(np.float64)
                    self.mu3 = npz[f"{sid}__mu3"].astype(np.float64)
                    self.sd3 = npz[f"{sid}__sd3"].astype(np.float64)
                self.has_model = True
            except Exception as e:
                print(f"[CausalEEGDecoder] 載入 {model_path} 失敗，改用節律啟發模式: {e}")

        # 線上自適應標準化統計 (針對 _GLOBAL_ 即插即用)
        self.is_global = (self.subject_id == "_GLOBAL_")
        self.ema_mu = None
        self.ema_var = None
        self.ema_alpha = 0.06
        self.drift_offset = np.zeros(38, dtype=np.float64)

        self.focus_hist = deque(maxlen=smooth_len)
        self.stroop_hist = deque(maxlen=smooth_len)
        self.focus_pct = 70.0
        self.stroop_pct = 20.0
        self.quality = "ok"

        # Fp1 即時眨眼 (EOG) 狀態機
        self._zi_blink = signal.sosfilt_zi(_BLINK_SOS) * 0.0
        self._blink_init = False
        self._blink_hist = deque(maxlen=FS * 3)
        self._last_blink_t = -10.0
        self._prev_blink_t = -10.0

    def warmup_from_samples(self, samples, weight=0.40):
        """考前暖身校正 (4 秒以上樣本即可更新個人漂移或 EMA 起始點)"""
        arr = np.asarray(samples, dtype=np.float64)
        if len(arr) < WIN:
            return False
        feats = np.array(
            [extract_38_features(arr[i : i + WIN]) for i in range(0, len(arr) - WIN + 1, FS)]
        )
        if self.is_global:
            self.ema_mu = feats.mean(axis=0)
            self.ema_var = np.maximum(0.25, feats.var(axis=0))
        else:
            self.drift_offset = weight * (feats.mean(axis=0) - self.mu)
        return True

    def _detect_blink(self, chunk, now_t):
        if len(chunk) == 0:
            return False, False
        arr = np.asarray(chunk, dtype=np.float64)
        if not self._blink_init:
            self._zi_blink = signal.sosfilt_zi(_BLINK_SOS) * arr[0]
            self._blink_init = True
        lo, self._zi_blink = signal.sosfilt(_BLINK_SOS, arr, zi=self._zi_blink)
        self._blink_hist.extend(lo.tolist())

        blink = False
        double_blink = False
        if len(self._blink_hist) >= FS:  # 至少累積 1 秒參考雜訊基底
            hist_arr = np.asarray(self._blink_hist, dtype=np.float64)
            s = _mad(hist_arr)
            # 只有單一強眼電尖峰高於 5.5 倍 MAD 且遠離微小雜訊才觸發
            peak_v = float(np.max(np.abs(lo)))
            if peak_v > max(35.0, 5.5 * s) and (now_t - self._last_blink_t) > 0.25:
                blink = True
                if 0.25 <= (now_t - self._last_blink_t) <= 0.90:
                    double_blink = True
                self._prev_blink_t = self._last_blink_t
                self._last_blink_t = now_t
        return blink, double_blink

    def push(self, raw_samples, poor_signal=0, now_t=None):
        """推入一批 512Hz 腦波點，回傳 dict: focus, stroop, eeg_quality, blink, double_blink"""
        if now_t is None:
            now_t = time.time()
        chunk = np.asarray(raw_samples, dtype=np.float64)
        self.buf.extend(chunk.tolist())
        self.since += len(chunk)

        blink, double_blink = self._detect_blink(chunk, now_t)

        # 訊號品質檢查
        if poor_signal >= 50:
            self.quality = "poor"
        elif len(self.buf) >= FS:
            tail = np.asarray(list(self.buf)[-FS:], dtype=np.float64)
            if float(np.std(tail)) < 1e-3 or float(np.max(np.abs(tail))) > 1e5:
                self.quality = "poor"
            else:
                self.quality = "ok"

        if len(self.buf) == WIN and self.since >= self.step:
            self.since = 0
            seg = np.asarray(self.buf, dtype=np.float64)
            f = extract_38_features(seg)

            if self.is_global:
                if self.ema_mu is None:
                    self.ema_mu = f.copy()
                    self.ema_var = np.ones_like(f) * 1.0
                else:
                    # 眨眼嚴重時降低基準追蹤速率避免污染
                    alpha = self.ema_alpha * (0.25 if blink else 1.0)
                    self.ema_mu = (1.0 - alpha) * self.ema_mu + alpha * f
                    diff = f - self.ema_mu
                    self.ema_var = (1.0 - alpha) * self.ema_var + alpha * (diff ** 2)
                sd = np.sqrt(self.ema_var) + 1e-6
                z2 = (f - self.ema_mu) / sd
                z3 = z2
            else:
                z2 = (f - self.mu - self.drift_offset) / (self.sd + 1e-9)
                z3 = (f - self.mu3 - self.drift_offset) / (self.sd3 + 1e-9)

            z2 = np.clip(z2, -5.0, 5.0)
            z3 = np.clip(z3, -5.0, 5.0)

            if self.has_model:
                logit2 = float(np.dot(self.w2, z2) + self.b2)
                raw_p_focus = 1.0 / (1.0 + np.exp(-np.clip(logit2, -15.0, 15.0)))

                if self.W3 is not None:
                    logits3 = self.W3 @ z3 + self.b3
                    logits3 -= np.max(logits3)
                    exps = np.exp(logits3)
                    probs3 = exps / np.sum(exps)
                    raw_p_stroop = float(probs3[2])
                    # 融合 2 分類與 3 分類 Focus 信心
                    raw_p_focus = 0.65 * raw_p_focus + 0.35 * float(probs3[1] / (probs3[0] + probs3[1] + 1e-6))
                else:
                    raw_p_stroop = float(1.0 / (1.0 + np.exp(-np.clip(z2[24], -10.0, 10.0))))
            else:
                # 備援節律啟發式 (無權重檔時)
                raw_p_focus = float(1.0 / (1.0 + np.exp(-np.clip(z2[6], -8.0, 8.0))))
                raw_p_stroop = float(1.0 / (1.0 + np.exp(-np.clip(z2[2], -8.0, 8.0))))

            self.focus_hist.append(raw_p_focus * 100.0)
            self.stroop_hist.append(raw_p_stroop * 100.0)
            self.focus_pct = float(np.clip(np.mean(self.focus_hist), 0.0, 100.0))
            self.stroop_pct = float(np.clip(np.mean(self.stroop_hist), 0.0, 100.0))

        return {
            "focus": round(self.focus_pct, 1),
            "stroop": round(self.stroop_pct, 1),
            "eeg_quality": self.quality,
            "blink": bool(blink),
            "double_blink": bool(double_blink),
        }
