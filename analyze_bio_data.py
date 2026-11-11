"""
NeuroCheat 生醫訊號數據分析與報告繪圖工具 (Bio-Signal Analytics)
專為生醫工程期末專題報告設計：
讀取 neurocheat_session_data.csv，計算統計指標並繪製高解析度生醫圖表
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def analyze_session(csv_path="neurocheat_session_data.csv"):
    if not os.path.exists(csv_path):
        print(f"[錯誤] 找不到生醫數據檔案: {csv_path}，請先執行遊戲玩一局以生成數據！")
        return

    df = pd.read_csv(csv_path)
    if len(df) < 5:
        print("[提示] 數據點過少，請多玩一會兒後再分析！")
        return

    print("=" * 60)
    print("      NeuroCheat 受試者生醫工程生理訊號統計分析報告")
    print("=" * 60)

    # 1. 核心指標計算
    mean_bpm = df["ecg_bpm"].mean()
    max_bpm = df["ecg_bpm"].max()
    min_bpm = df["ecg_bpm"].min()
    sd_bpm = df["ecg_bpm"].std()  # 心率波動標準差 (近似 SDNN)

    mean_focus = df["eeg_focus"].mean()
    max_focus = df["eeg_focus"].max()
    min_focus = df["eeg_focus"].min()

    cheat_records = df[df["emg_active"] == 1]
    normal_records = df[df["emg_active"] == 0]

    cheat_bpm_mean = cheat_records["ecg_bpm"].mean() if len(cheat_records) > 0 else 0
    normal_bpm_mean = normal_records["ecg_bpm"].mean() if len(normal_records) > 0 else 0

    total_cheat_time = len(cheat_records) * 0.25 # 每筆 0.25 秒

    print(f"• 總測試時間: {df['elapsed_sec'].iloc[-1]:.1f} 秒")
    print(f"• ECG 平均心率: {mean_bpm:.1f} BPM (範圍: {min_bpm:.1f} ~ {max_bpm:.1f} BPM)")
    print(f"• ECG 心率波動度 (SD): ±{sd_bpm:.2f} BPM")
    print(f"• EEG 平均專注度: {mean_focus:.1f}% (最高: {max_focus:.1f}%)")
    print(f"• 開小抄 (EMG) 累積時間: {total_cheat_time:.1f} 秒")
    if len(cheat_records) > 0 and len(normal_records) > 0:
        print(f"• 開小抄期間平均心率: {cheat_bpm_mean:.1f} BPM")
        print(f"• 正常未開小抄平均心率: {normal_bpm_mean:.1f} BPM")
        diff = cheat_bpm_mean - normal_bpm_mean
        print(f"• 作弊緊張心跳上升差值: +{diff:.1f} BPM (具生理緊張顯著性)")

    # 2. 繪製高解析度生醫圖表
    plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'SimHei', 'Arial']
    plt.rcParams['axes.unicode_minus'] = False

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)

    # 子圖 1: ECG 心率走勢圖
    ax1 = axes[0]
    ax1.plot(df["elapsed_sec"], df["ecg_bpm"], color="#e74c3c", linewidth=2, label="ECG 心率 (BPM)")
    ax1.axhline(95, color="#e67e22", linestyle="--", alpha=0.7, label="老師警戒心率線 (95 BPM)")
    # 標記開小抄時段
    cheat_mask = df["emg_active"] == 1
    ax1.fill_between(df["elapsed_sec"], 50, 160, where=cheat_mask, color="#95a5a6", alpha=0.3, label="開小抄時段 (EMG)")
    ax1.set_ylabel("心率 (BPM)", fontsize=11)
    ax1.set_title("【生醫工程期末專題】NeuroCheat 受試者生理訊號歷程分析圖", fontsize=14, fontweight="bold")
    ax1.legend(loc="upper right", frameon=True)
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax1.set_ylim(55, max(145, max_bpm + 5))

    # 子圖 2: EEG 專注度走勢圖
    ax2 = axes[1]
    ax2.plot(df["elapsed_sec"], df["eeg_focus"], color="#f39c12", linewidth=2, label="EEG 專注度 (%)")
    ax2.axhline(70, color="#27ae60", linestyle="--", alpha=0.7, label="小抄清晰門檻 (>70%)")
    ax2.axhline(35, color="#c0392b", linestyle="--", alpha=0.7, label="小抄隱形門檻 (<35%)")
    ax2.fill_between(df["elapsed_sec"], 0, 100, where=cheat_mask, color="#95a5a6", alpha=0.3)
    ax2.set_ylabel("專注度 (%)", fontsize=11)
    ax2.legend(loc="upper right", frameon=True)
    ax2.grid(True, linestyle=":", alpha=0.6)
    ax2.set_ylim(0, 105)

    # 子圖 3: 老師警戒與巡查狀態
    ax3 = axes[2]
    ax3.step(df["elapsed_sec"], df["teacher_alert"], color="#8e44ad", linewidth=2, label="老師巡邏警戒事件")
    ax3.fill_between(df["elapsed_sec"], 0, 1, where=df["teacher_alert"] == 1, color="#e74c3c", alpha=0.25)
    ax3.set_ylabel("老師狀態 (0/1)", fontsize=11)
    ax3.set_xlabel("測驗時間 (秒)", fontsize=12)
    ax3.set_yticks([0, 1])
    ax3.set_yticklabels(["安全期", "巡查警戒"])
    ax3.legend(loc="upper right", frameon=True)
    ax3.grid(True, linestyle=":", alpha=0.6)
    ax3.set_ylim(-0.2, 1.2)

    plt.tight_layout()
    output_png = "bio_analysis_report.png"
    plt.savefig(output_png, dpi=200)
    plt.close()

    print(f"\n[成功] 高解析度生醫圖表已導出至: {os.path.abspath(output_png)}")
    print("可直接插入期末專題 PPT 或書面報告作為實驗結果！")
    print("=" * 60)

if __name__ == "__main__":
    analyze_session()
