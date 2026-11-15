"""
analyze_bio_data.py - NeuroCheat 考場生理遙測與行為分析腳本
============================================================
讀取 sessions/neurocheat_session_data.csv，繪製四聯圖表：
  1. ECG 心率與相對基線增量 (BPM vs 基線)
  2. EMG 握力開合曲線與手臂疲勞度 (%)
  3. EEG 專注度與 Stroop 認知超載 (%)
  4. 老師懷疑度變化與考試作答得分進度
"""

import os
import sys
import matplotlib
import pandas as pd


def analyze_session(csv_path=None, save_path=None, show=True):
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sess_dir = os.path.join(project_root, "sessions")

    if csv_path is None:
        csv_path = os.path.join(sess_dir, "neurocheat_session_data.csv")
    if save_path is None:
        save_path = os.path.join(sess_dir, "bio_analysis_report.png")

    if not os.path.exists(csv_path):
        print(f"[Analyze] 找不到遙測紀錄檔: {csv_path}")
        return None

    df = pd.read_csv(csv_path)
    if df.empty:
        print(f"[Analyze] 紀錄檔為空，略過繪圖: {csv_path}")
        return None

    plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, axes = plt.subplots(4, 1, figsize=(12, 11), sharex=True)
    fig.patch.set_facecolor("#0f141e")
    t = df["time"]

    for ax in axes:
        ax.set_facecolor("#151c29")
        ax.grid(color="#283448", linestyle="--", linewidth=0.6, alpha=0.8)
        ax.tick_params(colors="#cbd5e1")
        for spine in ax.spines.values():
            spine.set_color("#334155")

    # Panel 1: ECG BPM & Baseline
    ax1 = axes[0]
    ax1.plot(t, df["ecg_bpm"], color="#fb7185", linewidth=1.8, label="ECG 心率 (BPM)")
    if "bpm_base" in df.columns:
        ax1.plot(t, df["bpm_base"], color="#38bdf8", linestyle="--", linewidth=1.3, label="開局基線")
        ax1.fill_between(
            t,
            df["bpm_base"],
            df["ecg_bpm"],
            where=(df["ecg_bpm"] > df["bpm_base"] + 9.0),
            color="#fb7185",
            alpha=0.22,
            label="高壓警戒區 (+9 BPM)",
        )
    ax1.set_ylabel("BPM", color="#fda4af")
    ax1.set_title("NeuroCheat 考場生理訊號與風險遙測分析", color="#e2e8f0", fontsize=14, pad=10)
    ax1.legend(loc="upper left", fontsize=9, facecolor="#1e293b", edgecolor="#334155", labelcolor="#e2e8f0")

    # Panel 2: EMG Level & Fatigue
    ax2 = axes[1]
    emg_pct = df["emg_level"] * 100.0 if "emg_level" in df.columns else df.get("emg_clenched", 0) * 100.0
    ax2.plot(t, emg_pct, color="#facc15", linewidth=1.6, label="EMG 握力 (%)")
    if "emg_fatigue" in df.columns:
        ax2.plot(t, df["emg_fatigue"], color="#f97316", linewidth=1.5, linestyle="-.", label="肌肉疲勞 (%)")
    ax2.axhline(22, color="#38bdf8", linestyle=":", linewidth=1.0, label="微縫門檻 (22%)")
    ax2.axhline(56, color="#ef4444", linestyle=":", linewidth=1.0, label="全開門檻 (56%)")
    ax2.set_ylabel("EMG (%)", color="#fde047")
    ax2.set_ylim(-5, 108)
    ax2.legend(loc="upper left", fontsize=9, facecolor="#1e293b", edgecolor="#334155", labelcolor="#e2e8f0")

    # Panel 3: EEG Focus & Stroop Overload
    ax3 = axes[2]
    ax3.plot(t, df["eeg_focus"], color="#60a5fa", linewidth=1.7, label="EEG 專注度 (%)")
    if "eeg_stroop" in df.columns:
        ax3.plot(t, df["eeg_stroop"], color="#c084fc", linewidth=1.6, label="Stroop 認知超載 (%)")
        ax3.axhline(50, color="#c084fc", linestyle=":", linewidth=1.0, label="字色干擾門檻 (50%)")
    ax3.set_ylabel("EEG (%)", color="#93c5fd")
    ax3.set_ylim(-5, 108)
    ax3.legend(loc="upper left", fontsize=9, facecolor="#1e293b", edgecolor="#334155", labelcolor="#e2e8f0")

    # Panel 4: Suspicion & Score
    ax4 = axes[3]
    ax4.plot(t, df["suspicion"], color="#ef4444", linewidth=1.8, label="老師懷疑值 (%)")
    if "exam_score" in df.columns:
        ax4.plot(t, df["exam_score"], color="#4ade80", linewidth=1.7, drawstyle="steps-post", label="累積考試得分")
    ax4.set_ylabel("分數 / 懷疑 (%)", color="#e2e8f0")
    ax4.set_xlabel("經過時間 (秒)", color="#cbd5e1")
    ax4.set_ylim(-5, 108)
    ax4.legend(loc="upper left", fontsize=9, facecolor="#1e293b", edgecolor="#334155", labelcolor="#e2e8f0")

    plt.tight_layout()
    out_dir = os.path.dirname(os.path.abspath(save_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    fig.savefig(save_path, dpi=140, facecolor=fig.get_facecolor())
    print(f"[Analyze] 已輸出分析圖表: {save_path} (共 {len(df)} 筆遙測)")

    if show:
        plt.show()
    else:
        plt.close(fig)
    return save_path


if __name__ == "__main__":
    arg_csv = sys.argv[1] if len(sys.argv) > 1 else None
    analyze_session(csv_path=arg_csv, show=True)
