"""
NeuroCheat 外部生理訊號測試發送端 (External Signal Sender)
=========================================================
不接實體電路時，可用於測試【模式二：外部訊號模式 (EXTERNAL)】完整欄位：
  python -m bio_bridge.external_signal_sender --auto
  python -m bio_bridge.external_signal_sender
"""

import json
import math
import socket
import sys
import time

UDP_IP = "127.0.0.1"
UDP_PORT = 5005


def send_signal(sock, ecg, eeg, emg=None, stroop=None, bpm_delta=None, double_blink=False):
    payload = {
        "ecg_bpm": round(float(ecg), 1),
        "bpm_base": 72.0,
        "bpm_delta": round(float(bpm_delta if bpm_delta is not None else (ecg - 72.0)), 1),
        "ecg_quality": "ok",
        "eeg": round(float(eeg), 1),
        "focus": round(float(eeg), 1),
        "stroop": round(float(stroop if stroop is not None else max(5.0, 100.0 - eeg)), 1),
        "eeg_quality": "ok",
        "double_blink": bool(double_blink),
    }
    if emg is not None:
        payload["emg"] = round(float(emg), 2)
        payload["emg_fist"] = bool(float(emg) > 0.30)

    msg_str = json.dumps(payload)
    try:
        sock.sendto(msg_str.encode("utf-8"), (UDP_IP, UDP_PORT))
    except Exception:
        pass
    return msg_str


def run_auto_stream(sock):
    print(f"📡 開始向 NeuroCheat ({UDP_IP}:{UDP_PORT}) 連續發送模擬生醫串流 (Ctrl+C 停止)...")
    t0 = time.time()
    try:
        while True:
            elapsed = time.time() - t0
            ecg = 80.0 + 22.0 * math.sin(elapsed * 0.45)
            eeg = 66.0 + 28.0 * math.cos(elapsed * 0.35)
            stroop = 32.0 + 30.0 * max(0.0, math.sin(elapsed * 0.5))
            # 連續 3 段握力循環：靜止 -> 微開縫隙 (0.40) -> 全開 (0.85)
            cyc = elapsed % 12.0
            emg = 0.08 if cyc < 4.0 else (0.40 if cyc < 8.0 else 0.85)
            send_signal(sock, ecg, eeg, emg=emg, stroop=stroop)
            print(f"\r[Auto] ECG={ecg:.1f} (Δ{ecg-72:+.1f}) | EMG={emg:.2f} | EEG={eeg:.0f}% | Stroop={stroop:.0f}%   ", end="", flush=True)
            time.sleep(0.08)
    except KeyboardInterrupt:
        print("\n已停止發送。")


def run_interactive(sock):
    print("=" * 65)
    print("🧠 NeuroCheat 外部生醫訊號互動測試器 (UDP 127.0.0.1:5005)")
    print("=" * 65)
    print("輸入指令：")
    print("  85 90         -> ECG=85 BPM, EEG Focus=90%")
    print("  85 90 0.4     -> ECG=85, Focus=90%, EMG=0.4 (輕握縫隙)")
    print("  blink         -> 送出一次雙眨眼翻頁事件")
    print("  auto          -> 連續波形測試")
    print("  q             -> 離開")
    print("-" * 65)

    last_ecg, last_eeg, last_emg = 75.0, 80.0, 0.0
    while True:
        try:
            raw = input("輸入> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw:
            continue
        if raw.lower() in ("q", "quit", "exit"):
            break
        if raw.lower() == "auto":
            run_auto_stream(sock)
            continue
        if raw.lower() == "blink":
            send_signal(sock, last_ecg, last_eeg, emg=last_emg, double_blink=True)
            print("👁️ 已送出雙眨眼事件 (翻頁小抄)!")
            continue

        parts = raw.replace(",", " ").split()
        try:
            if len(parts) >= 2:
                last_ecg = float(parts[0])
                last_eeg = float(parts[1])
                last_emg = float(parts[2]) if len(parts) >= 3 else None
                send_signal(sock, last_ecg, last_eeg, emg=last_emg)
                print(f"✅ 已送出 -> ECG={last_ecg}, EEG={last_eeg}, EMG={last_emg}")
            else:
                print("⚠️ 格式錯誤，請輸入至少兩個數字，如: 85 90 0.4")
        except ValueError:
            print("⚠️ 請輸入合法數字！")


if __name__ == "__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if "--auto" in sys.argv:
        run_auto_stream(sock)
    else:
        run_interactive(sock)
