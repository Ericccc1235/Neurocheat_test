"""
hardware_bridge.py - 硬體感測橋接與雙向通訊模組
====================================================
支援三種外部生理訊號輸入管道（可隨時於遊戲中切換）：
  1. UDP Socket (127.0.0.1:5005) — 接收 bio_bridge/bridge_hub.py 或 external_signal_sender.py 的整合 JSON 封包
  2. USB Serial / Bluetooth SPP (COM Port) — 支援文字鍵值格式，亦相容直接解碼 Exp 2 3-byte 二進位串流
  3. 檔案輪詢 (sessions/external_signals.json 或 external_signals.json) — 方便離線/外部腳本測試

同時支援雙向硬體回饋 (UDP 127.0.0.1:5006 / 直連 Serial)：
  - BUZZER_WARN / BUZZER_BUSTED -> 觸發 Arduino Pin 8 蜂鳴器 / 震動馬達
  - CALIB_REST / CALIB_MVC / CALIB_FOCUS / CALIB_DONE -> 同步校正流程至 bridge_hub
"""

import json
import os
import socket
import threading
import time

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

try:
    from bio_bridge.exp2_dsp import (
        DualBinaryFrameDecoder,
        RealtimeECGProcessor,
        RealtimeEMGProcessor,
    )
    HAS_EXP2_DSP = True
except ImportError:
    HAS_EXP2_DSP = False


def _parse_bool(val):
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return float(val) >= 0.5
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on", "fist")
    return False


class HardwareBridge:
    """背景非阻塞生理訊號接收器與遊戲指令回傳橋接器。"""

    def __init__(self, bio_signals, port=None, baudrate=115200, udp_port=5005, cmd_port=5006):
        self.bio = bio_signals
        self.port = port
        self.baudrate = baudrate
        self.udp_port = udp_port
        self.cmd_port = cmd_port

        self._lock = threading.Lock()
        self.running = False
        self.status_text = "模擬模式 (僅鍵鼠 / 按 F1 切換外部連線)"
        self.available_ports = []

        self._serial_conn = None
        self._udp_sock = None
        self._cmd_sock = None
        self._threads = []

        # 直連 Arduino 二進位串流時的本地 DSP 後備處理器
        self._bin_decoder = DualBinaryFrameDecoder() if HAS_EXP2_DSP else None
        self._direct_ecg = RealtimeECGProcessor(fs=160.0) if HAS_EXP2_DSP else None
        self._direct_emg = RealtimeEMGProcessor(input_max=255.0) if HAS_EXP2_DSP else None
        self._direct_calib_mode = None

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._watch_paths = [
            os.path.join(project_root, "sessions", "external_signals.json"),
            os.path.join(project_root, "external_signals.json"),
        ]
        self._last_file_mtime = {}
        self._last_rx_time = 0.0

        self.scan_ports()

    # ------------------------------------------------------------------
    # COM Port 掃描與連線管理
    # ------------------------------------------------------------------
    def scan_ports(self):
        if not HAS_SERIAL:
            self.available_ports = []
            return []
        try:
            ports = [p.device for p in serial.tools.list_ports.comports()]
        except Exception:
            ports = []
        with self._lock:
            self.available_ports = sorted(ports)
        return self.available_ports

    def cycle_serial_port(self):
        """依序切換偵測到的 COM Port（切到底後回到純 UDP 監聽）。"""
        ports = self.scan_ports()
        if not ports:
            self._close_serial()
            with self._lock:
                self.port = None
                self.status_text = f"未偵測到 COM Port | UDP :{self.udp_port} 待命中"
            return None

        if self.port not in ports:
            next_port = ports[0]
        else:
            idx = ports.index(self.port)
            if idx + 1 >= len(ports):
                self._close_serial()
                with self._lock:
                    self.port = None
                    self.status_text = f"已斷開 Serial | UDP :{self.udp_port} 待命中"
                return None
            next_port = ports[idx + 1]

        self.connect_serial(next_port)
        return self.port

    def connect_serial(self, port_name):
        self._close_serial()
        if not port_name or not HAS_SERIAL:
            with self._lock:
                self.port = None
                self.status_text = f"UDP :{self.udp_port} 監聽中 (無 Serial)"
            return False

        try:
            conn = serial.Serial(port_name, self.baudrate, timeout=0.05)
            with self._lock:
                self._serial_conn = conn
                self.port = port_name
                self.status_text = f"已連線 {port_name} ({self.baudrate}) + UDP :{self.udp_port}"
            if self._bin_decoder is not None:
                self._bin_decoder = DualBinaryFrameDecoder()
            return True
        except Exception as e:
            with self._lock:
                self._serial_conn = None
                self.port = None
                self.status_text = f"Serial 開啟失敗 ({port_name}): {str(e)[:28]}"
            return False

    def _close_serial(self):
        with self._lock:
            conn = self._serial_conn
            self._serial_conn = None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 背景執行緒生命週期
    # ------------------------------------------------------------------
    def start(self):
        if self.running:
            return
        self.running = True

        # 開啟 UDP 接收 Socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("127.0.0.1", self.udp_port))
            sock.settimeout(0.25)
            self._udp_sock = sock
            with self._lock:
                if not self.port:
                    self.status_text = f"UDP :{self.udp_port} 監聽中 (等待 bridge_hub 或模擬器)"
        except Exception as e:
            self._udp_sock = None
            with self._lock:
                self.status_text = f"UDP :{self.udp_port} 綁定失敗: {str(e)[:28]}"

        # 指令回傳用 UDP Socket (無須 bind)
        try:
            self._cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except Exception:
            self._cmd_sock = None

        if self.port:
            self.connect_serial(self.port)

        self._threads = [
            threading.Thread(target=self._udp_loop, daemon=True, name="NeuroBridgeUDP"),
            threading.Thread(target=self._serial_loop, daemon=True, name="NeuroBridgeSerial"),
            threading.Thread(target=self._file_watch_loop, daemon=True, name="NeuroBridgeFile"),
        ]
        for t in self._threads:
            t.start()

    def stop(self):
        self.running = False
        if self._udp_sock is not None:
            try:
                self._udp_sock.close()
            except Exception:
                pass
            self._udp_sock = None
        if self._cmd_sock is not None:
            try:
                self._cmd_sock.close()
            except Exception:
                pass
            self._cmd_sock = None
        self._close_serial()
        for t in self._threads:
            if t.is_alive():
                t.join(timeout=0.4)
        self._threads.clear()

    # ------------------------------------------------------------------
    # 雙向遊戲指令回傳 (蜂鳴器 / 震動 / 校正同步)
    # ------------------------------------------------------------------
    def send_game_command(self, cmd_str):
        """傳送指令給 bridge_hub (UDP 5006) 及直連 Arduino Serial。"""
        cmd = str(cmd_str).strip()
        if not cmd:
            return False

        sent = False
        if self._cmd_sock is not None:
            try:
                self._cmd_sock.sendto(cmd.encode("utf-8"), ("127.0.0.1", self.cmd_port))
                sent = True
            except Exception:
                pass

        # 若遊戲直連 Arduino Serial，亦同步轉發控制字元與本地校正狀態
        if cmd == "CALIB_REST":
            self._direct_calib_mode = "REST"
            if self._direct_ecg is not None:
                self._direct_ecg.start_baseline_calibration()
        elif cmd == "CALIB_MVC":
            self._direct_calib_mode = "MVC"
        elif cmd == "CALIB_DONE":
            self._direct_calib_mode = None
            if self._direct_ecg is not None:
                self._direct_ecg.finish_baseline_calibration()
            if self._direct_emg is not None:
                self._direct_emg.finish_calibration()

        serial_map = {
            "BUZZER_WARN": b"B",
            "BUZZER_BUSTED": b"C",
            "TOGGLE_ARDUINO_TEST": b"T",
        }
        if cmd in serial_map:
            with self._lock:
                conn = self._serial_conn
            if conn is not None:
                try:
                    conn.write(serial_map[cmd])
                    sent = True
                except Exception:
                    pass
        return sent

    # ------------------------------------------------------------------
    # 背景讀取迴圈
    # ------------------------------------------------------------------
    def _udp_loop(self):
        while self.running:
            if self._udp_sock is None:
                time.sleep(0.2)
                continue
            try:
                data, _addr = self._udp_sock.recvfrom(8192)
                text = data.decode("utf-8", errors="ignore").strip()
                if text:
                    self.parse_and_apply(text, source_label=f"UDP:{self.udp_port}")
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception:
                time.sleep(0.05)

    def _serial_loop(self):
        text_buf = bytearray()
        ecg_batch = []
        last_emg = 0.0
        last_btn = False
        last_emit = time.time()

        while self.running:
            with self._lock:
                conn = self._serial_conn
                port_label = self.port or "Serial"

            if conn is None:
                time.sleep(0.15)
                continue

            try:
                waiting = conn.in_waiting
                chunk = conn.read(max(1, waiting)) if waiting > 0 else conn.read(1)
                if not chunk:
                    time.sleep(0.005)
                    continue

                # 判斷是否為 neurocheat_exp2_dual.ino 的 3-byte 二進位封包 (含 >= 0x80 同步位)
                has_binary_sync = any((b & 0x80) != 0 for b in chunk)
                if has_binary_sync and self._bin_decoder is not None:
                    frames = self._bin_decoder.feed(chunk)
                    for ecg10, emg8, _test_mode, btn_pressed in frames:
                        ecg_batch.append(ecg10)
                        last_emg = emg8
                        last_btn = btn_pressed
                        if self._direct_calib_mode == "REST":
                            self._direct_emg.record_rest(emg8)
                        elif self._direct_calib_mode == "MVC":
                            self._direct_emg.record_mvc(emg8)

                    now = time.time()
                    if ecg_batch and (now - last_emit) >= 0.04:
                        bpm, delta, qual, wave = self._direct_ecg.process_samples(ecg_batch, now)
                        emg_norm, emg_fist = self._direct_emg.process(last_emg, btn_override=last_btn)
                        ecg_batch.clear()
                        last_emit = now
                        self.bio.set_external_signals(
                            ecg_bpm=bpm,
                            bpm_base=self._direct_ecg.bpm_base,
                            bpm_delta=delta,
                            ecg_quality=qual,
                            ecg_samples=wave,
                            emg_val=emg_norm,
                            emg_fist=emg_fist,
                            source_label=f"Serial-Bin({port_label})",
                        )
                        with self._lock:
                            self._last_rx_time = now
                            self.status_text = f"直連 {port_label} | BPM:{bpm:.0f} EMG:{emg_norm*100:.0f}%"
                else:
                    # 文字行格式："ECG:82,EMG:0.65,EEG:75" 或 JSON 行
                    text_buf.extend(chunk)
                    while b"\n" in text_buf:
                        line_bytes, _, rest = text_buf.partition(b"\n")
                        text_buf = bytearray(rest)
                        line = line_bytes.decode("utf-8", errors="ignore").strip()
                        if line:
                            self.parse_and_apply(line, source_label=f"Serial({port_label})")
            except Exception:
                time.sleep(0.1)

    def _file_watch_loop(self):
        while self.running:
            for path in self._watch_paths:
                try:
                    if os.path.exists(path):
                        mtime = os.path.getmtime(path)
                        if mtime > self._last_file_mtime.get(path, 0.0):
                            self._last_file_mtime[path] = mtime
                            with open(path, "r", encoding="utf-8") as f:
                                content = f.read().strip()
                            if content:
                                self.parse_and_apply(content, source_label="JSON檔案")
                except Exception:
                    pass
            time.sleep(0.12)

    # ------------------------------------------------------------------
    # 封包解析與單位兼容正規化
    # ------------------------------------------------------------------
    def parse_and_apply(self, raw_str, source_label="External"):
        """解析 JSON 或 Key:Value 字串，並更新 BioSignalManager。"""
        raw = str(raw_str).strip()
        if not raw:
            return False

        parsed = {}
        if raw.startswith("{"):
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    parsed = {str(k).strip().lower(): v for k, v in obj.items()}
            except json.JSONDecodeError:
                return False
        else:
            # 解析 "ECG:85, EMG:0.8, EEG:70" 等格式
            for token in raw.replace(";", ",").split(","):
                if ":" in token:
                    k, v = token.split(":", 1)
                elif "=" in token:
                    k, v = token.split("=", 1)
                else:
                    continue
                k = k.strip().lower()
                v = v.strip()
                if not k:
                    continue
                if v.lower() in ("true", "false"):
                    parsed[k] = (v.lower() == "true")
                else:
                    try:
                        parsed[k] = float(v)
                    except ValueError:
                        parsed[k] = v

        if not parsed:
            return False

        def _get_float(*keys):
            for k in keys:
                if k in parsed and parsed[k] is not None:
                    try:
                        return float(parsed[k])
                    except (TypeError, ValueError):
                        pass
            return None

        ecg_bpm = _get_float("ecg_bpm", "ecg", "bpm")
        bpm_base = _get_float("bpm_base")
        bpm_delta = _get_float("bpm_delta")
        ecg_quality = parsed.get("ecg_quality")
        if ecg_quality is not None:
            ecg_quality = str(ecg_quality).strip().lower()

        ecg_samples = parsed.get("ecg_samples")
        if not isinstance(ecg_samples, list):
            ecg_samples = None

        emg_val = None
        if "emg_level" in parsed or "emg" in parsed:
            raw_emg = parsed.get("emg_level", parsed.get("emg"))
            if isinstance(raw_emg, bool):
                emg_val = 1.0 if raw_emg else 0.0
            else:
                try:
                    emg_val = float(raw_emg)
                    if emg_val > 1.5:  # 若外部直接傳 0~100 或 0~255
                        emg_val = emg_val / 100.0 if emg_val <= 100.0 else emg_val / 255.0
                except (TypeError, ValueError):
                    emg_val = 1.0 if _parse_bool(raw_emg) else 0.0

        emg_fist = None
        if "emg_fist" in parsed and parsed["emg_fist"] is not None:
            emg_fist = _parse_bool(parsed["emg_fist"])

        # 相容舊版 0.0~1.0 focus/stroop 單位與新版 0.0~100.0 百分比單位
        unit_scale = (
            "eeg" not in parsed
            and "eeg_focus" not in parsed
            and any(
                k in parsed
                and isinstance(parsed[k], (int, float))
                and 0.0 < float(parsed[k]) <= 1.0
                for k in ("focus", "stroop")
            )
        )

        eeg_focus = _get_float("eeg", "eeg_focus", "focus", "attention")
        if eeg_focus is not None and unit_scale and 0.0 <= eeg_focus <= 1.0:
            eeg_focus *= 100.0

        eeg_stroop = _get_float("stroop", "eeg_stroop", "overload")
        if eeg_stroop is not None and unit_scale and 0.0 <= eeg_stroop <= 1.0:
            eeg_stroop *= 100.0

        eeg_quality = parsed.get("eeg_quality")
        if eeg_quality is not None:
            eeg_quality = str(eeg_quality).strip().lower()

        blink = _parse_bool(parsed["blink"]) if "blink" in parsed else None
        double_blink = _parse_bool(parsed["double_blink"]) if "double_blink" in parsed else None

        self.bio.set_external_signals(
            ecg_bpm=ecg_bpm,
            bpm_base=bpm_base,
            bpm_delta=bpm_delta,
            ecg_quality=ecg_quality,
            ecg_samples=ecg_samples,
            emg_val=emg_val,
            emg_fist=emg_fist,
            eeg_focus=eeg_focus,
            eeg_stroop=eeg_stroop,
            eeg_quality=eeg_quality,
            blink=blink,
            double_blink=double_blink,
            source_label=source_label,
        )

        now = time.time()
        with self._lock:
            self._last_rx_time = now
            self.status_text = f"外部訊號接收中 ({source_label})"
        return True
