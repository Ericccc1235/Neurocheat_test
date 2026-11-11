"""
NeuroCheat 生醫硬體與外部訊號串接模組 (Hardware Bridge)
專為「模式二：外部訊號輸入模式」設計，同時支援三種零配置外部訊號輸入管道：
1. Serial 序列埠 (COM Port)：自動偵測或手動切換 Arduino / ESP32 / 生醫感測板 (115200 bps)
2. UDP 本地網路埠 (127.0.0.1:5005)：供外部 Python 腦波/心電處理程式、OpenBCI、LSL 或測試器即時傳送
3. 共享檔案 (external_signals.json)：供任何外部程式寫入 {"ecg": 85, "eeg": 78}

支援字串格式範例：
- 鍵值對格式："ECG:85.0,EEG:78.5" 或 "EMG:1,ECG:85,EEG:78"
- JSON 格式：'{"ecg": 85.0, "eeg": 78.5, "emg": 0}'
"""

import json
import os
import socket
import threading
import time

class HardwareBridge:
    def __init__(self, bio_signals, port=None, baudrate=115200, udp_port=5005):
        self.bio_signals = bio_signals
        self.port = port
        self.baudrate = baudrate
        self.udp_port = udp_port

        self.running = False
        self.serial_conn = None
        self.udp_sock = None
        self.available_ports = []
        self.status_text = "等待外部訊號 (UDP:5005 / Serial)"
        self._last_json_mtime = (
            os.path.getmtime("external_signals.json")
            if os.path.exists("external_signals.json")
            else 0.0
        )
        self.json_file_path = "external_signals.json"

        self.scan_ports()

    def scan_ports(self):
        """掃描系統目前可用的 Serial COM 埠"""
        try:
            import serial.tools.list_ports
            ports = [p.device for p in serial.tools.list_ports.comports()]
            self.available_ports = ports
        except Exception:
            self.available_ports = []
        return self.available_ports

    def cycle_serial_port(self):
        """在可用的 COM 埠之間循環切換 (供遊戲畫面按鈕點擊切換)"""
        self.scan_ports()
        if not self.available_ports:
            self.port = None
            self.status_text = "未偵測到實體 COM 埠 (UDP:5005 監聽中)"
            return "未偵測到 COM 埠 (可使用 UDP:5005 外部輸入)"

        if self.port not in self.available_ports:
            next_port = self.available_ports[0]
        else:
            idx = self.available_ports.index(self.port)
            if idx + 1 < len(self.available_ports):
                next_port = self.available_ports[idx + 1]
            else:
                next_port = None

        self.connect_serial(next_port)
        return self.status_text

    def connect_serial(self, port_name):
        """連接或切換指定的 Serial COM 埠"""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass
        self.serial_conn = None
        self.port = port_name

        if not port_name:
            self.status_text = f"Serial 未連接 | UDP:{self.udp_port} 監聽中"
            return False

        try:
            import serial
            self.serial_conn = serial.Serial(port_name, self.baudrate, timeout=0.05)
            self.status_text = f"已連接 {port_name} ({self.baudrate}) & UDP:{self.udp_port}"
            print(f"[HardwareBridge] 成功連接 Serial 埠: {port_name}")
            return True
        except Exception as e:
            self.status_text = f"無法開啟 {port_name} | UDP:{self.udp_port} 監聽中"
            print(f"[HardwareBridge] 無法開啟串口 {port_name}: {e}")
            return False

    def start(self):
        """啟動背景監聽執行緒 (同時監聽 Serial COM 埠、UDP 127.0.0.1:5005 與 JSON 檔案)"""
        self.running = True

        # 1. 啟動本地 UDP 非阻塞 Socket (127.0.0.1:5005)
        try:
            self.udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sock.bind(("127.0.0.1", self.udp_port))
            self.udp_sock.setBlocking(False) if hasattr(self.udp_sock, "setBlocking") else self.udp_sock.setblocking(False)
        except Exception as e:
            print(f"[HardwareBridge] UDP 埠 {self.udp_port} 綁定提示: {e}")
            self.udp_sock = None

        # 2. 若有指定 port 或系統只有一個 COM 埠可嘗試連接
        if self.port:
            self.connect_serial(self.port)
        else:
            self.status_text = f"UDP:{self.udp_port} & JSON 外部監聽就緒"

        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()

    def parse_and_apply(self, raw_str, source_label="External"):
        """解析單行外部訊號字串並寫入 BioSignalManager"""
        line = raw_str.strip()
        if not line:
            return False

        ecg_val = None
        eeg_val = None
        emg_val = None

        # 格式 A: JSON 字串 {"ecg": 85, "eeg": 75, "emg": 1}
        if line.startswith("{") and line.endswith("}"):
            try:
                data = json.loads(line)
                for k, v in data.items():
                    ku = k.strip().upper()
                    if ku in ("ECG", "BPM", "HEART_RATE"):
                        ecg_val = float(v)
                    elif ku in ("EEG", "FOCUS", "ATTENTION"):
                        eeg_val = float(v)
                    elif ku == "EMG":
                        emg_val = float(v)
            except Exception:
                return False
        else:
            # 格式 B: 逗號分隔鍵值對 "EMG:1,ECG:85.2,EEG:76.0"
            parts = line.split(",")
            for p in parts:
                if ":" in p:
                    try:
                        key, val = p.split(":", 1)
                        key = key.strip().upper()
                        val = float(val.strip())
                        if key in ("ECG", "BPM"):
                            ecg_val = val
                        elif key in ("EEG", "FOCUS"):
                            eeg_val = val
                        elif key == "EMG":
                            emg_val = val
                    except ValueError:
                        continue

        if ecg_val is not None or eeg_val is not None or emg_val is not None:
            self.bio_signals.set_external_signals(
                ecg=ecg_val,
                eeg=eeg_val,
                emg=emg_val,
                source=source_label
            )
            return True
        return False

    def _listen_loop(self):
        while self.running:
            received_any = False

            # 1. 讀取 Serial COM 埠
            if self.serial_conn and self.serial_conn.is_open:
                try:
                    while self.serial_conn.in_waiting > 0:
                        line = self.serial_conn.readline().decode("utf-8", errors="ignore").strip()
                        if line and self.parse_and_apply(line, source_label=f"Serial({self.port})"):
                            received_any = True
                except Exception:
                    pass

            # 2. 讀取 UDP 127.0.0.1:5005
            if self.udp_sock:
                try:
                    while True:
                        data, addr = self.udp_sock.recvfrom(1024)
                        line = data.decode("utf-8", errors="ignore").strip()
                        if line and self.parse_and_apply(line, source_label="UDP:5005"):
                            received_any = True
                except BlockingIOError:
                    pass
                except Exception:
                    pass

            # 3. 檢查共享 JSON 檔案 (external_signals.json)
            try:
                if os.path.exists(self.json_file_path):
                    mtime = os.path.getmtime(self.json_file_path)
                    if mtime > self._last_json_mtime:
                        self._last_json_mtime = mtime
                        with open(self.json_file_path, "r", encoding="utf-8") as f:
                            content = f.read().strip()
                        if content:
                            self.parse_and_apply(content, source_label="JSON檔案")
                            received_any = True
            except Exception:
                pass

            if not received_any:
                time.sleep(0.015)

    def stop(self):
        self.running = False
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
            except Exception:
                pass
        if self.udp_sock:
            try:
                self.udp_sock.close()
            except Exception:
                pass
