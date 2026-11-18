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
import asyncio
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

# HM-10 (CC2541) 與常見 BLE UART 透傳模組預設名稱與 GATT UUID
HM10_NAME_HINTS = ("hmsoft", "hm-10", "hm10", "bt05", "mlt-bt05", "dsd", "jdy", "cc41")
BLE_NOTIFY_UUIDS = (
    "0000ffe1-0000-1000-8000-00805f9b34fb",
    "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
)
BLE_WRITE_UUIDS = (
    "0000ffe1-0000-1000-8000-00805f9b34fb",
    "0000ffe2-0000-1000-8000-00805f9b34fb",
    "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
)


def _is_probable_hm10(name, adv_uuids):
    low_name = (name or "").lower()
    if any(hint in low_name for hint in HM10_NAME_HINTS):
        return True
    for u in adv_uuids or ():
        if "ffe0" in str(u).lower() or "6e400001" in str(u).lower():
            return True
    return False


def scan_ble_devices(timeout=5.0):
    """掃描附近 BLE 裝置並標示疑似 HM-10 模組，方便組員確認電腦是否找得到模組。"""
    try:
        from bleak import BleakScanner
    except ImportError:
        print("[BLE] 尚未安裝 bleak，請先執行: .venv\\Scripts\\python.exe -m pip install bleak")
        return []

    print(f"[BLE 掃描] 正在搜尋鄰近低功耗藍牙裝置 ({timeout:.0f} 秒)...")

    async def _scan():
        return await BleakScanner.discover(timeout=timeout, return_adv=True)

    try:
        results = asyncio.run(_scan())
    except Exception as e:
        print(f"[BLE 掃描失敗] 請確認筆電藍牙已開啟: {e}")
        return []

    items = []
    for _addr, (dev, adv) in results.items():
        name = dev.name or adv.local_name or "(未命名)"
        rssi = adv.rssi if adv.rssi is not None else -999
        uuids = list(adv.service_uuids or [])
        items.append((rssi, dev.address, name, uuids, _is_probable_hm10(name, uuids)))

    items.sort(reverse=True, key=lambda x: x[0])
    print("\n=== 掃描到的 BLE 裝置清單 ===")
    if not items:
        print("  (找不到任何 BLE 裝置。請確認 HM-10 電源已開、LED 正在閃爍、且筆電藍牙已開啟)")
    else:
        for idx, (rssi, addr, name, uuids, is_hm10) in enumerate(items, start=1):
            tag = " [★ 疑似 HM-10]" if is_hm10 else ""
            u_str = ", ".join(str(u)[:8] for u in uuids[:3])
            print(f"  {idx:2d}. {name:<20s} | MAC={addr} | RSSI={rssi:4d} dBm | UUID={u_str}{tag}")

        best = next((it for it in items if it[4]), None)
        if best:
            print(f"\n建議連線測試指令 (MAC={best[1]}):")
            print(f"  .venv\\Scripts\\python.exe -m bio_bridge.bridge_hub --eeg sim --arduino-mode ble --ble-addr {best[1]} --ble-test")
    print("=" * 34)
    return items


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
        self._last_emg_raw = 0.0

        self.bio_serial = None
        self._ble_active = False
        self._ble_tx_lock = threading.Lock()
        self._ble_tx_deque = deque()
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
        if self._ble_active:
            with self._ble_tx_lock:
                self._ble_tx_deque.append(b_cmd)

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
        print(f"[EEG Live] {self.args.eeg_com} 序列埠已開啟，等待 ThinkGear 腦波資料...")

        tg = ThinkGearStreamDecoder()
        raw_buf = []
        ascii_buf = bytearray()
        t0_eeg = time.time()
        got_first_sample = False
        warned_no_eeg = False

        while self.running:
            try:
                waiting = ser.in_waiting
                data = ser.read(waiting if waiting > 0 else 1)
                if not data:
                    if (not got_first_sample) and (not warned_no_eeg) and (time.time() - t0_eeg >= 4.5):
                        warned_no_eeg = True
                        print(
                            f"[EEG Live 提示] 開啟 {self.args.eeg_com} 後 4.5 秒內未收到資料："
                            "請確認選到「連出 (Outgoing)」COM Port、頭環已長按開機，且未開著 115-1_brainlink.exe 佔用藍牙！"
                        )
                    continue

                samples = tg.feed(data)
                if samples:
                    raw_buf.extend(samples)
                    if not got_first_sample:
                        got_first_sample = True
                        print(
                            f"[EEG Live] 成功收到 BrainLink 512Hz 腦波串流！"
                            f"(poor_signal={tg.poor_signal}；0=貼合正常，>50=請壓緊額頭乾電極)"
                        )
                elif tg.packet_ok_count == 0:
                    # 若從未見 ThinkGear binary 封包，支援文字格式 fallback
                    ascii_buf.extend(data)
                    while b"\n" in ascii_buf:
                        line_b, _, ascii_buf = ascii_buf.partition(b"\n")
                        try:
                            val = float(line_b.decode("utf-8", errors="ignore").strip().split(",")[0])
                            raw_buf.append(val)
                            if not got_first_sample:
                                got_first_sample = True
                                print("[EEG Live] 成功收到 BrainLink 文字格式串流！")
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
        if mode == "ble":
            self._run_ble_live()
        elif mode in ("dual", "exp2_raw") and self.args.bio_com:
            self._run_arduino_live(mode)
        else:
            if mode in ("dual", "exp2_raw") and not self.args.bio_com:
                print("[Exp2] 未指定 --bio-com，改用合成 ECG+EMG 模擬串流 (sim)")
            self._run_bio_sim()

    def _flush_bio_batches(self, batch_ecg, batch_emg, last_btn, now_t):
        """共用的即時 ECG/EMG 數位濾波、個人校正與狀態更新，供 Serial 與 BLE 共用。"""
        bpm, bpm_d, qual, wave_chunk = self.ecg_proc.process_samples(batch_ecg, now_t)
        batch_ecg.clear()

        emg_norm = self.bio_state["emg"]
        emg_fist = self.bio_state["emg_fist"]
        if batch_emg:
            raw_emg = float(np.mean(batch_emg))
            batch_emg.clear()
            self._last_emg_raw = raw_emg
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
                        for ecg10, emg8, _test_mode, btn in decoder.feed(data):
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
                    self._flush_bio_batches(batch_ecg, batch_emg, last_btn, now_t)
            except Exception:
                time.sleep(0.02)

    def _resolve_ble_chars(self, client):
        """從連線後的 GATT 服務中找出 HM-10/BLE UART 通知 (RX) 與寫入 (TX) Characteristic。"""
        custom_uuid = (self.args.ble_uuid or "").strip().lower()
        notify_cands = []
        write_cands = []
        for svc in client.services:
            for ch in svc.characteristics:
                u = str(ch.uuid).lower()
                props = set(ch.properties or ())
                if custom_uuid and custom_uuid in u:
                    if "notify" in props or "indicate" in props:
                        notify_cands.insert(0, (0, ch))
                    if "write-without-response" in props or "write" in props:
                        write_cands.insert(0, (0, ch))
                if "notify" in props or "indicate" in props:
                    prio = BLE_NOTIFY_UUIDS.index(u) + 1 if u in BLE_NOTIFY_UUIDS else 99
                    notify_cands.append((prio, ch))
                if "write-without-response" in props or "write" in props:
                    prio = BLE_WRITE_UUIDS.index(u) + 1 if u in BLE_WRITE_UUIDS else 99
                    write_cands.append((prio, ch))
        notify_cands.sort(key=lambda x: x[0])
        write_cands.sort(key=lambda x: x[0])
        rx_char = notify_cands[0][1] if notify_cands else None
        tx_char = write_cands[0][1] if write_cands else None
        return rx_char, tx_char

    def _run_ble_live(self):
        try:
            from bleak import BleakClient, BleakScanner
        except ImportError:
            print("[BLE] 尚未安裝 bleak，請執行: .venv\\Scripts\\python.exe -m pip install bleak")
            return

        async def _ble_session():
            target_addr = (self.args.ble_addr or "").strip()
            target_name = (self.args.ble_name or "").strip().lower()
            decoder = DualBinaryFrameDecoder()
            batch_ecg = []
            batch_emg = []
            state_box = {"btn": False, "first_frame": False, "disconnected": False}
            rx_buf = bytearray()
            rx_lock = threading.Lock()

            while self.running:
                device = None
                if target_addr:
                    print(f"[BLE] 正在尋找指定裝置 MAC={target_addr} ...")
                    device = await BleakScanner.find_device_by_address(target_addr, timeout=6.0)
                else:
                    print("[BLE] 掃描鄰近低功耗藍牙裝置 (最多 6 秒)...")
                    found = await BleakScanner.discover(timeout=6.0, return_adv=True)
                    candidates = []
                    for _a, (dev, adv) in found.items():
                        dname = dev.name or adv.local_name or ""
                        rssi = adv.rssi if adv.rssi is not None else -999
                        uuids = list(adv.service_uuids or [])
                        if target_name:
                            matched = target_name in dname.lower()
                        else:
                            matched = _is_probable_hm10(dname, uuids)
                        if matched:
                            candidates.append((rssi, dev, dname or dev.address))
                    if candidates:
                        candidates.sort(reverse=True, key=lambda x: x[0])
                        _rssi, device, picked_label = candidates[0]
                        print(f"[BLE] 鎖定目標: {picked_label} (MAC={device.address}, RSSI={_rssi} dBm)")
                    elif found:
                        print("[BLE] 未比對到 HM-10 (HMSoft/FFE0)，鄰近發現的裝置有：")
                        for _a, (dev, adv) in found.items():
                            dname = dev.name or adv.local_name or "(未命名)"
                            print(f"      - {dname} (MAC={dev.address}, RSSI={adv.rssi})")
                        print("[BLE] 提示: 可直接加上 --ble-addr <MAC> 或 --ble-name <名稱>；若 HM-10 燈已恆亮代表正被手機/Windows 佔用連線！")

                if device is None:
                    if not self.running:
                        break
                    print("[BLE] 找不到目標裝置，3 秒後重試...")
                    await asyncio.sleep(3.0)
                    continue

                state_box["disconnected"] = False
                state_box["first_frame"] = False
                state_box["raw_rx_bytes"] = 0
                state_box["first_raw_logged"] = False

                def _on_disconnect(_client):
                    state_box["disconnected"] = True
                    print("[BLE] 警告: HM-10 藍牙連線已中斷，將自動重連...")

                def _on_notify(_sender, data):
                    with rx_lock:
                        rx_buf.extend(data)

                try:
                    async with BleakClient(device, disconnected_callback=_on_disconnect, timeout=12.0) as client:
                        rx_char, tx_char = self._resolve_ble_chars(client)
                        if rx_char is None:
                            print("[BLE] 找不到支援 Notify 的 GATT 特徵值，請確認這顆裝置為 HM-10 透傳模組！")
                            await asyncio.sleep(3.0)
                            continue

                        with self._ble_tx_lock:
                            self._ble_tx_deque.clear()
                        self._ble_active = True

                        await client.start_notify(rx_char, _on_notify)
                        print(
                            f"[BLE] 已連線！(若模組 LED 轉為恆亮代表成功) RX={str(rx_char.uuid)[:8]} | "
                            f"TX={str(tx_char.uuid)[:8] if tx_char else '無'}，等待 Arduino 封包..."
                        )

                        # 送出啟動串流指令 ('S')，若使用者傳入 --ble-test 則同步切入 Arduino 測試波 ('T')
                        if tx_char is not None:
                            use_resp = "write-without-response" not in set(tx_char.properties or ())
                            await client.write_gatt_char(tx_char, b"S", response=use_resp)
                            if self.args.ble_test:
                                await asyncio.sleep(0.08)
                                await client.write_gatt_char(tx_char, b"T", response=use_resp)
                                print("[BLE] 已發送 'T' 指令切換至 Arduino 內建測試波 (75 BPM + EMG 週期測試)！")

                        conn_t0 = time.time()
                        warned_no_rx = False
                        last_flush = conn_t0
                        while self.running and not state_box["disconnected"]:
                            # 傳送遊戲端回饋指令 ('B' 警告 / 'C' 抓包 / 'T' 測試波 / 'P' 暫停)
                            pending_cmds = []
                            with self._ble_tx_lock:
                                while self._ble_tx_deque:
                                    pending_cmds.append(self._ble_tx_deque.popleft())
                            for cmd_b in pending_cmds:
                                if tx_char is not None:
                                    use_resp = "write-without-response" not in set(tx_char.properties or ())
                                    try:
                                        await client.write_gatt_char(tx_char, cmd_b, response=use_resp)
                                    except Exception:
                                        pass

                            chunk = b""
                            with rx_lock:
                                if rx_buf:
                                    chunk = bytes(rx_buf)
                                    rx_buf.clear()

                            if chunk:
                                state_box["raw_rx_bytes"] += len(chunk)
                                if not state_box["first_raw_logged"]:
                                    state_box["first_raw_logged"] = True
                                    print(
                                        f"[BLE Debug] 收到原始 BLE 資料 {len(chunk)} bytes "
                                        f"(前幾碼 hex={chunk[:8].hex(' ')})，嘗試解碼 3-byte 封包..."
                                    )
                                frames = decoder.feed(chunk)
                                if frames and not state_box["first_frame"]:
                                    state_box["first_frame"] = True
                                    print("[BLE] 成功收到首筆 3-byte 封包！HM-10 雙通道串流已完全打通！")
                                for ecg10, emg8, _tm, btn in frames:
                                    batch_ecg.append(ecg10)
                                    batch_emg.append(emg8)
                                    state_box["btn"] = btn

                            now_t = time.time()
                            if (not state_box["first_frame"]) and (not warned_no_rx) and (now_t - conn_t0 >= 4.0):
                                warned_no_rx = True
                                if state_box["raw_rx_bytes"] == 0:
                                    print(
                                        "[BLE 提示] 筆電已連上 HM-10，但收到 0 bytes："
                                        "請確認是否已燒錄 neurocheat_exp2_dual.ino、HM-10 RXD<-Pin 3、TXD->Pin 2 與共地 GND！"
                                    )
                                else:
                                    print(
                                        f"[BLE 提示] 收到 {state_box['raw_rx_bytes']} bytes 原始資料但無法解成 3-byte 雙通道封包："
                                        "請確認已燒錄最新版 neurocheat_exp2_dual.ino 且 Arduino BT_BAUD 與 HM-10 Baudrate 一致 (預設 9600)！"
                                    )
                            if batch_ecg and (now_t - last_flush >= 0.04 or len(batch_ecg) >= 12):
                                last_flush = now_t
                                self._flush_bio_batches(batch_ecg, batch_emg, state_box["btn"], now_t)

                            await asyncio.sleep(0.015)

                        try:
                            if tx_char is not None and not state_box["disconnected"]:
                                use_resp = "write-without-response" not in set(tx_char.properties or ())
                                await client.write_gatt_char(tx_char, b"P", response=use_resp)
                            await client.stop_notify(rx_char)
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[BLE] 連線過程發生異常: {e}")
                finally:
                    self._ble_active = False
                    with self._ble_tx_lock:
                        self._ble_tx_deque.clear()

                if self.running:
                    await asyncio.sleep(2.0)

        try:
            asyncio.run(_ble_session())
        except Exception as e:
            print(f"[BLE] 事件迴圈錯誤: {e}")

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

                emg_only = bool(getattr(self.args, "emg_only", False))
                print_interval = 0.4 if emg_only else 2.0
                if t_now - last_print >= print_interval:
                    last_print = t_now
                    if emg_only:
                        bar_n = int(round(packet["emg"] * 20))
                        bar = "#" * bar_n + "-" * (20 - bar_n)
                        print(
                            f"[{t_now:5.1f}s] EMG={packet['emg']:.2f} [{bar}] "
                            f"握拳={str(packet['emg_fist']):<5s} | A1包絡raw={self._last_emg_raw:5.1f}/255 "
                            f"(Rest={self.emg_proc.rest_level:.0f}, MVC={self.emg_proc.mvc_level:.0f})"
                        )
                    else:
                        qual_txt = packet["ecg_quality"]
                        if qual_txt != "ok" and self.ecg_proc.bad_reason:
                            qual_txt = f"{qual_txt}: {self.ecg_proc.bad_reason}"
                        eeg_q = "" if packet["eeg_quality"] == "ok" else f",{packet['eeg_quality']}"
                        print(
                            f"[{t_now:5.1f}s] ECG={packet['ecg_bpm']:.1f}bpm (Δ{packet['bpm_delta']:+.1f},{qual_txt}) | "
                            f"EMG={packet['emg']:.2f}({packet['emg_fist']},raw={self._last_emg_raw:.0f}) | "
                            f"Focus={packet['focus']:.0f}% Stroop={packet['stroop']:.0f}%{eeg_q}"
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
    parser.add_argument("--arduino-mode", choices=["dual", "ble", "exp2_raw", "sim", "none"], default="sim", help="Arduino 模式 (ble=HM-10低功耗藍牙)")
    parser.add_argument("--bio-com", default=None, help="Arduino / HC-05 COM Port (例如 COM4)")
    parser.add_argument("--bio-baud", type=int, default=9600, help="Arduino/HC-05 Baudrate (HC-05 預設 9600, USB 115200)")
    parser.add_argument("--ble-name", default="", help="HM-10/BLE 裝置名稱關鍵字 (留空自動比對 HMSoft/HM-10/FFE0)")
    parser.add_argument("--ble-addr", default=None, help="直接指定 HM-10 BLE MAC 位址 (例如 AA:BB:CC:DD:EE:FF)")
    parser.add_argument("--ble-uuid", default=None, help="選配自訂 BLE UART 特徵 UUID (預設自動偵測 FFE1)")
    parser.add_argument("--ble-test", action="store_true", help="HM-10 連線後自動送 'T' 開啟 Arduino 假波形測試 (免貼電極驗收)")
    parser.add_argument("--scan-ble", action="store_true", help="掃描並列出附近 BLE/HM-10 裝置後結束")
    parser.add_argument("--emg-only", action="store_true", help="單測 EMG 模式：每 0.4s 僅顯示 A1 原始包絡線與握拳進度條")
    parser.add_argument("--cmd-port", type=int, default=UDP_CMD_PORT, help="接收遊戲回饋指令的 UDP Port")
    args = parser.parse_args()

    if args.scan_ble:
        scan_ble_devices(timeout=5.0)
        return

    hub = BridgeHub(args)
    hub.run()


if __name__ == "__main__":
    main()
