"""
bridge_hub.py - NeuroCheat 多通道生醫訊號融合橋接中心
=========================================================
同時統整：
1. Exp 2 硬體串口 (Arduino ECG + EMG):
   - dual:     接收 neurocheat_exp2_dual.ino 的 3-byte 160Hz 封包 (10-bit ECG + 1kHz EMG包絡線) + 回傳蜂鳴器控制指令
   - exp2_raw: 相容實驗二原版 arduino_ecg_bluetooth.ino 的 200Hz 單 byte ECG 串流
   - sim:      免硬體模擬 PQRST 心電波形 + 漸進握拳肌電測試
2. Exp 3 BrainLink EEG 即時串流:
   - replay:   從 bci_dataset_115-1_anon 回放 Relax / Focus / Stroop 真實 512Hz 腦波
   - live:     從真實 BrainLink COM Port 解碼 ThinkGear 二進位封包 (57600 baud)
   - sim:      免資料集合成三狀態腦波模擬串流
3. 雙向 UDP 通訊：
   - 推送 25Hz 完整生理 JSON 至遊戲本體 (127.0.0.1:5005)
   - 接收遊戲指令 (127.0.0.1:5006)：自動校正 Rest/MVC/ECG基準，以及驅動 Arduino Pin 8 蜂鳴器！

執行範例：
  python -m bio_bridge.bridge_hub --eeg replay --arduino-mode sim
  python -m bio_bridge.bridge_hub --eeg live --eeg-com COM5 --arduino-mode dual --bio-com COM6
  python -m bio_bridge.bridge_hub --eeg replay --arduino-mode exp2_raw --bio-com COM6 --bio-baud 9600
"""

import argparse
import json
import math
import os
import random
import socket
import sys
import threading
import time
from collections import deque

import numpy as np

# 確保不論從根目錄或 bio_bridge/ 直接啟動都能正確匯入
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bio_bridge.eeg_realtime import FS as EEG_FS, CausalEEGDecoder, ThinkGearStreamDecoder
from bio_bridge.exp2_dsp import (
    DualBinaryFrameDecoder,
    RealtimeECGProcessor,
    RealtimeEMGProcessor,
)

UDP_IP = "127.0.0.1"
UDP_DATA_PORT = 5005
UDP_CMD_PORT = 5006


def find_dataset_dir():
    candidates = [
        os.path.join(_ROOT, "bci_dataset_115-1_anon", "bci_dataset_115-1_anon"),
        os.path.join(_ROOT, "bci_dataset_115-1_anon"),
        os.path.join(os.path.dirname(_ROOT), "bci_dataset_115-1_anon", "bci_dataset_115-1_anon"),
        os.path.join(os.path.dirname(_ROOT), "bci_dataset_115-1_anon"),
    ]
    for c in candidates:
        if os.path.isdir(c) and any(d.startswith("S") for d in os.listdir(c)):
            return c
    return None


def synth_pqrst_ecg_sample(phase):
    """產生接近 0~1023 的單點模擬心電樣本 (僅於 sim 模式沒插 Arduino 時使用)"""
    v = 0.0
    if 0.12 <= phase <= 0.22:
        v += 90.0 * math.sin((phase - 0.12) / 0.10 * math.pi)
    elif 0.32 <= phase <= 0.35:
        v -= 70.0 * math.sin((phase - 0.32) / 0.03 * math.pi)
    elif 0.35 <= phase <= 0.40:
        v += 380.0 * math.sin((phase - 0.35) / 0.05 * math.pi)
    elif 0.40 <= phase <= 0.44:
        v -= 140.0 * math.sin((phase - 0.40) / 0.04 * math.pi)
    elif 0.55 <= phase <= 0.72:
        v += 115.0 * math.sin((phase - 0.55) / 0.17 * math.pi)
    noise = random.uniform(-12.0, 12.0)
    return float(max(20.0, min(1000.0, 512.0 + v + noise)))


class BridgeHub:
    def __init__(self, args):
        self.args = args
        self.running = True
        self.lock = threading.Lock()

        # UDP Sockets
        self.tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.cmd_sock.bind((UDP_IP, args.cmd_port))
            self.cmd_sock.setblocking(False)
        except Exception as e:
            print(f"[BridgeHub] 指令埠 {args.cmd_port} 綁定失敗: {e}")

        # 1. EEG 解碼器
        self.eeg_decoder = CausalEEGDecoder(subject_id=args.sub)
        self.eeg_state = {
            "focus": 72.0,
            "stroop": 18.0,
            "eeg_quality": "ok",
            "blink": False,
            "double_blink": False,
        }
        self._calib_eeg_buf = deque(maxlen=EEG_FS * 25)

        # 2. Exp 2 ECG + EMG 處理器
        ecg_fs = 200.0 if args.arduino_mode == "exp2_raw" else 160.0
        adc_max = 255.0 if args.arduino_mode == "exp2_raw" else 1023.0
        self.ecg_proc = RealtimeECGProcessor(fs=ecg_fs, adc_max=adc_max, use_notch=True)
        self.emg_proc = RealtimeEMGProcessor(input_max=255.0)
        self.bio_state = {
            "ecg_bpm": 72.0,
            "bpm_base": 72.0,
            "bpm_delta": 0.0,
            "ecg_quality": "ok",
            "ecg_samples": [],
            "emg": 0.0,
            "emg_fist": False,
        }

        self.bio_serial = None
        self.calib_phase = None  # None | "REST" | "MVC" | "FOCUS"
        self._pending_blink = False
        self._pending_double_blink = False

    def handle_game_command(self, cmd_str):
        cmd = cmd_str.strip().upper()
        if not cmd:
            return
        if cmd == "BUZZER_WARN":
            self._send_arduino_byte(b"B")
        elif cmd == "BUZZER_BUSTED":
            self._send_arduino_byte(b"C")
        elif cmd == "CALIB_REST":
            self.calib_phase = "REST"
            self.ecg_proc.start_baseline_calibration()
            self._calib_eeg_buf.clear()
            print("[Calib] 進入階段 1: 靜止放鬆與基準心率量測...")
        elif cmd == "CALIB_MVC":
            self.calib_phase = "MVC"
            print("[Calib] 進入階段 2: 左手全力握拳 MVC 校正...")
        elif cmd == "CALIB_FOCUS":
            self.calib_phase = "FOCUS"
            print("[Calib] 進入階段 3: EEG 專注基線校正...")
        elif cmd == "CALIB_DONE":
            self.calib_phase = None
            rest_v, mvc_v = self.emg_proc.finish_calibration()
            bpm_base = self.ecg_proc.finish_baseline_calibration()
            if len(self._calib_eeg_buf) >= EEG_FS * 4:
                self.eeg_decoder.warmup_from_samples(list(self._calib_eeg_buf))
            print(f"[Calib 完成] EMG Rest={rest_v:.1f}, MVC={mvc_v:.1f} | ECG Base={bpm_base:.1f} BPM")
        elif cmd == "TOGGLE_ARDUINO_TEST":
            self._send_arduino_byte(b"T")

    def _send_arduino_byte(self, b_cmd):
        if self.bio_serial and self.bio_serial.is_open:
            try:
                self.bio_serial.write(b_cmd)
            except Exception:
                pass

    def _poll_commands(self):
        try:
            while True:
                data, _ = self.cmd_sock.recvfrom(512)
                msg = data.decode("utf-8", errors="ignore").strip()
                if msg:
                    self.handle_game_command(msg)
        except BlockingIOError:
            pass
        except Exception:
            pass

    def eeg_worker(self):
        mode = self.args.eeg
        if mode == "none":
            return
        if mode == "replay":
            self._run_eeg_replay()
        elif mode == "live":
            self._run_eeg_live()
        elif mode == "sim":
            self._run_eeg_sim()

    def _run_eeg_replay(self):
        ds_dir = find_dataset_dir()
        if not ds_dir:
            print("[EEG] 找不到 bci_dataset_115-1_anon，自動改為合成腦波模擬串流 (sim)！")
            self._run_eeg_sim()
            return

        subs = sorted(d for d in os.listdir(ds_dir) if os.path.isdir(os.path.join(ds_dir, d)))
        pick_sub = self.args.sub if self.args.sub in subs else subs[0]
        sub_path = os.path.join(ds_dir, pick_sub)
        files_relax = sorted(os.path.join(sub_path, f) for f in os.listdir(sub_path) if "_1_" in f and f.endswith(".txt"))
        files_focus = sorted(os.path.join(sub_path, f) for f in os.listdir(sub_path) if "_2_" in f and f.endswith(".txt"))
        files_stroop = sorted(os.path.join(sub_path, f) for f in os.listdir(sub_path) if "_3_" in f and f.endswith(".txt"))

        sequence = []
        n_blocks = max(len(files_focus), len(files_relax), 1)
        for i in range(n_blocks):
            if files_focus:
                sequence.append(("Focus", files_focus[i % len(files_focus)]))
            if files_stroop and i % 2 == 1:
                sequence.append(("Stroop", files_stroop[i % len(files_stroop)]))
            elif files_relax:
                sequence.append(("Relax", files_relax[i % len(files_relax)]))

        print(f"[EEG Replay] 使用受試者 {pick_sub} 真實三態腦波串流 ({self.eeg_decoder.subject_id} 模型)")
        chunk_size = 32  # ~62.5ms
        dt_sleep = chunk_size / EEG_FS
        idx = 0

        while self.running:
            state_label, fpath = sequence[idx % len(sequence)]
            idx += 1
            raw = np.loadtxt(fpath)
            for s in range(0, len(raw), chunk_size):
                if not self.running:
                    break
                chunk = raw[s : s + chunk_size]
                self._calib_eeg_buf.extend(chunk.tolist())
                res = self.eeg_decoder.push(chunk)
                with self.lock:
                    self.eeg_state.update(res)
                    if res["blink"]:
                        self._pending_blink = True
                    if res["double_blink"]:
                        self._pending_double_blink = True
                time.sleep(dt_sleep)

    def _run_eeg_live(self):
        try:
            import serial
        except ImportError:
            print("[EEG Live] 缺少 pyserial，無法連線 BrainLink。")
            return

        print(f"[EEG Live] 連線 BrainLink {self.args.eeg_com} @ {self.args.eeg_baud} baud...")
        try:
            ser = serial.Serial(self.args.eeg_com, self.args.eeg_baud, timeout=0.1)
        except Exception as e:
            print(f"[EEG Live] 開啟 {self.args.eeg_com} 失敗: {e}")
            return

        tg = ThinkGearStreamDecoder()
        raw_buf = []
        ascii_buf = bytearray()

        while self.running:
            try:
                waiting = ser.in_waiting
                data = ser.read(waiting if waiting > 0 else 1)
                if not data:
                    continue

                samples = tg.feed(data)
                if samples:
                    raw_buf.extend(samples)
                elif tg.packet_ok_count == 0:
                    # 若從未見 ThinkGear binary 封包，支援文字格式 fallback
                    ascii_buf.extend(data)
                    while b"\n" in ascii_buf:
                        line_b, _, ascii_buf = ascii_buf.partition(b"\n")
                        try:
                            val = float(line_b.decode("utf-8", errors="ignore").strip().split(",")[0])
                            raw_buf.append(val)
                        except ValueError:
                            pass

                if len(raw_buf) >= 32:
                    self._calib_eeg_buf.extend(raw_buf)
                    res = self.eeg_decoder.push(raw_buf, poor_signal=tg.poor_signal)
                    raw_buf.clear()
                    with self.lock:
                        self.eeg_state.update(res)
                        if res["blink"]:
                            self._pending_blink = True
                        if res["double_blink"]:
                            self._pending_double_blink = True
            except Exception:
                time.sleep(0.02)

    def _run_eeg_sim(self):
        print("[EEG Sim] 啟動合成三態腦波模擬器 (Focus / Relax / Stroop 交替)")
        t0 = time.time()
        chunk_size = 32
        dt_sleep = chunk_size / EEG_FS
        sample_i = 0

        while self.running:
            elapsed = time.time() - t0
            phase = int(elapsed // 14) % 3  # 每 14 秒輪流切換狀態
            ts = (np.arange(chunk_size) + sample_i) / EEG_FS
            sample_i += chunk_size

            if phase == 0:  # Focus: Beta (18Hz) 高 + Alpha (10Hz) 低
                sig = 18.0 * np.sin(2 * np.pi * 18.0 * ts) + 6.0 * np.sin(2 * np.pi * 10.0 * ts)
            elif phase == 1:  # Relax: Alpha (10.2Hz) 顯著
                sig = 32.0 * np.sin(2 * np.pi * 10.2 * ts) + 7.0 * np.sin(2 * np.pi * 18.0 * ts)
            else:  # Stroop: Theta (5.5Hz) + 瞬變升高
                sig = 26.0 * np.sin(2 * np.pi * 5.5 * ts) + 14.0 * np.sin(2 * np.pi * 22.0 * ts)

            sig = sig + np.random.normal(0.0, 5.0, size=chunk_size)
            self._calib_eeg_buf.extend(sig.tolist())
            res = self.eeg_decoder.push(sig)
            with self.lock:
                self.eeg_state.update(res)
                if res["blink"]:
                    self._pending_blink = True
                if res["double_blink"]:
                    self._pending_double_blink = True
            time.sleep(dt_sleep)

    def bio_worker(self):
        mode = self.args.arduino_mode
        if mode == "none":
            return
        if mode in ("dual", "exp2_raw") and self.args.bio_com:
            self._run_arduino_live(mode)
        else:
            if mode in ("dual", "exp2_raw") and not self.args.bio_com:
                print("[Exp2] 未指定 --bio-com，改用合成 ECG+EMG 模擬串流 (sim)")
            self._run_bio_sim()

    def _run_arduino_live(self, mode):
        try:
            import serial
        except ImportError:
            print("[Exp2 Live] 缺少 pyserial，無法連線 Arduino。")
            return

        print(f"[Exp2 Live] 開啟 {self.args.bio_com} @ {self.args.bio_baud} baud (模式={mode})...")
        try:
            self.bio_serial = serial.Serial(self.args.bio_com, self.args.bio_baud, timeout=0.05)
        except Exception as e:
            print(f"[Exp2 Live] 開啟 {self.args.bio_com} 失敗: {e}")
            return

        # 如果是原版 Exp 2 韌體，傳一個字元喚醒 start_recv
        if mode == "exp2_raw":
            time.sleep(0.5)
            self._send_arduino_byte(b"1")
        else:
            time.sleep(0.3)
            self._send_arduino_byte(b"S")

        decoder = DualBinaryFrameDecoder()
        batch_ecg = []
        batch_emg = []
        last_btn = False
        last_flush = time.time()

        while self.running:
            try:
                waiting = self.bio_serial.in_waiting
                data = self.bio_serial.read(waiting if waiting > 0 else 1)
                if data:
                    if mode == "dual":
                        frames = decoder.feed(data)
                        for ecg10, emg8, _test_mode, btn in frames:
                            batch_ecg.append(ecg10)
                            batch_emg.append(emg8)
                            last_btn = btn
                    else:
                        # exp2_raw: 每個 byte 就是一個 0..255 ECG 取樣
                        for b in data:
                            batch_ecg.append(float(b))

                now_t = time.time()
                if batch_ecg and (now_t - last_flush >= 0.04 or len(batch_ecg) >= 12):
                    last_flush = now_t
                    bpm, bpm_d, qual, wave_chunk = self.ecg_proc.process_samples(batch_ecg, now_t)
                    batch_ecg.clear()

                    emg_norm = self.bio_state["emg"]
                    emg_fist = self.bio_state["emg_fist"]
                    if batch_emg:
                        raw_emg = float(np.mean(batch_emg))
                        batch_emg.clear()
                        if self.calib_phase == "REST":
                            self.emg_proc.record_rest(raw_emg)
                        elif self.calib_phase == "MVC":
                            self.emg_proc.record_mvc(raw_emg)
                        emg_norm, emg_fist = self.emg_proc.process(raw_emg, btn_override=last_btn)

                    with self.lock:
                        self.bio_state["ecg_bpm"] = bpm
                        self.bio_state["bpm_base"] = round(self.ecg_proc.bpm_base, 1)
                        self.bio_state["bpm_delta"] = bpm_d
                        self.bio_state["ecg_quality"] = qual
                        self.bio_state["ecg_samples"].extend(wave_chunk)
                        if len(self.bio_state["ecg_samples"]) > 120:
                            self.bio_state["ecg_samples"] = self.bio_state["ecg_samples"][-120:]
                        self.bio_state["emg"] = emg_norm
                        self.bio_state["emg_fist"] = emg_fist
            except Exception:
                time.sleep(0.02)

    def _run_bio_sim(self):
        print("[Exp2 Sim] 啟動合成 ECG (真實數位 R-peak 濾波演算法驗證) + 漸進 EMG 模擬")
        fs = self.ecg_proc.fs
        dt_tick = 0.04  # 25Hz
        samples_per_tick = max(1, int(round(fs * dt_tick)))
        beat_phase = 0.0
        t0 = time.time()

        while self.running:
            t_now = time.time()
            elapsed = t_now - t0
            # 週期性模擬：平靜(70bpm/放鬆) -> 輕握偷看(78bpm/EMG 0.4) -> 緊張全開(96bpm/EMG 0.85)
            cycle = elapsed % 24.0
            if cycle < 8.0:
                target_bpm = 70.0 + 3.0 * math.sin(elapsed * 0.5)
                raw_emg_sim = 14.0 + random.uniform(-3.0, 3.0)
            elif cycle < 15.0:
                target_bpm = 79.0 + 4.0 * math.sin(elapsed * 0.7)
                raw_emg_sim = 72.0 + random.uniform(-6.0, 6.0)
            else:
                target_bpm = 96.0 + 5.0 * math.sin(elapsed * 1.1)
                raw_emg_sim = 152.0 + random.uniform(-10.0, 10.0)

            chunk = []
            d_phase = (target_bpm / 60.0) / fs
            for _ in range(samples_per_tick):
                beat_phase = (beat_phase + d_phase) % 1.0
                chunk.append(synth_pqrst_ecg_sample(beat_phase))

            bpm, bpm_d, qual, wave_chunk = self.ecg_proc.process_samples(chunk, t_now)
            if self.calib_phase == "REST":
                self.emg_proc.record_rest(14.0)
            elif self.calib_phase == "MVC":
                self.emg_proc.record_mvc(155.0)
            emg_norm, emg_fist = self.emg_proc.process(raw_emg_sim)

            with self.lock:
                self.bio_state["ecg_bpm"] = bpm
                self.bio_state["bpm_base"] = round(self.ecg_proc.bpm_base, 1)
                self.bio_state["bpm_delta"] = bpm_d
                self.bio_state["ecg_quality"] = qual
                self.bio_state["ecg_samples"].extend(wave_chunk)
                if len(self.bio_state["ecg_samples"]) > 120:
                    self.bio_state["ecg_samples"] = self.bio_state["ecg_samples"][-120:]
                self.bio_state["emg"] = emg_norm
                self.bio_state["emg_fist"] = emg_fist

            time.sleep(dt_tick)

    def run(self):
        t_eeg = threading.Thread(target=self.eeg_worker, daemon=True)
        t_bio = threading.Thread(target=self.bio_worker, daemon=True)
        t_eeg.start()
        t_bio.start()

        print(f"[BridgeHub] UDP JSON 推播中 -> {UDP_IP}:{UDP_DATA_PORT} (指令接收埠 {UDP_CMD_PORT})，按 Ctrl+C 停止")
        t_start = time.time()
        last_print = 0.0

        try:
            while self.running:
                self._poll_commands()
                t_now = time.time() - t_start

                with self.lock:
                    ecg_samples_out = self.bio_state["ecg_samples"][-16:]
                    self.bio_state["ecg_samples"] = []
                    blink_now = self._pending_blink
                    dbl_now = self._pending_double_blink
                    self._pending_blink = False
                    self._pending_double_blink = False

                    packet = {
                        "t": round(t_now, 2),
                        "ecg_bpm": self.bio_state["ecg_bpm"],
                        "bpm_base": self.bio_state["bpm_base"],
                        "bpm_delta": self.bio_state["bpm_delta"],
                        "ecg_quality": self.bio_state["ecg_quality"],
                        "ecg_samples": ecg_samples_out,
                        "emg": self.bio_state["emg"],
                        "emg_fist": self.bio_state["emg_fist"],
                        "eeg": self.eeg_state["focus"],
                        "focus": self.eeg_state["focus"],
                        "stroop": self.eeg_state["stroop"],
                        "eeg_quality": self.eeg_state["eeg_quality"],
                        "blink": blink_now,
                        "double_blink": dbl_now,
                    }

                self.tx_sock.sendto(json.dumps(packet).encode("utf-8"), (UDP_IP, UDP_DATA_PORT))

                if t_now - last_print >= 2.0:
                    last_print = t_now
                    print(
                        f"[{t_now:5.1f}s] ECG={packet['ecg_bpm']:.1f}bpm (Δ{packet['bpm_delta']:+.1f},{packet['ecg_quality']}) | "
                        f"EMG={packet['emg']:.2f}({packet['emg_fist']}) | "
                        f"Focus={packet['focus']:.0f}% Stroop={packet['stroop']:.0f}%"
                    )

                time.sleep(0.04)  # 25 Hz 推送頻率
        except KeyboardInterrupt:
            print("\n[BridgeHub] 正在關閉橋接器...")
        finally:
            self.running = False
            self._send_arduino_byte(b"P")
            if self.bio_serial and self.bio_serial.is_open:
                self.bio_serial.close()


def main():
    parser = argparse.ArgumentParser(description="NeuroCheat 生醫訊號橋接中心 (Exp2 ECG/EMG + Exp3 EEG)")
    parser.add_argument("--eeg", choices=["replay", "live", "sim", "none"], default="replay", help="EEG 來源模式")
    parser.add_argument("--sub", default="_GLOBAL_", help="EEG 模型 (_GLOBAL_ 或 S01~S21)")
    parser.add_argument("--eeg-com", default="COM3", help="BrainLink 藍牙 COM Port")
    parser.add_argument("--eeg-baud", type=int, default=57600, help="BrainLink Baudrate (標準 ThinkGear 為 57600)")
    parser.add_argument("--arduino-mode", choices=["dual", "exp2_raw", "sim", "none"], default="sim", help="Arduino 模式")
    parser.add_argument("--bio-com", default=None, help="Arduino / HC-05 COM Port (例如 COM4)")
    parser.add_argument("--bio-baud", type=int, default=9600, help="Arduino/HC-05 Baudrate (HC-05 預設 9600, USB 115200)")
    parser.add_argument("--cmd-port", type=int, default=UDP_CMD_PORT, help="接收遊戲回饋指令的 UDP Port")
    args = parser.parse_args()

    hub = BridgeHub(args)
    hub.run()


if __name__ == "__main__":
    main()
