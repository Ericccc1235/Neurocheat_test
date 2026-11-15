"""
ui_renderer.py - 抬頭顯示器、15秒校正精靈與主視窗 UI 渲染器
================================================================
繪製頂部狀態列、右側 EMG/ECG/EEG 即時生醫儀表板（含真實/合成示波器、
EMG 疲勞條、EEG Focus + Stroop 超載指標與雙眨眼翻頁狀態），
以及標題畫面、考前 3 步驟基線校正精靈與結算成績單。
"""

import os
import pygame
from game.classroom_3d import find_cjk_font_path


class UIRenderer:
    """負責全部非 3D 教室場景之介面與生醫儀表板繪製。"""

    def __init__(self, width=1280, height=720):
        cjk_reg = find_cjk_font_path(bold=False)
        cjk_bold = find_cjk_font_path(bold=True)
        if cjk_reg and cjk_bold:
            self.font_xs = pygame.font.Font(cjk_reg, 14)
            self.font_sm = pygame.font.Font(cjk_reg, 16)
            self.font_md = pygame.font.Font(cjk_bold, 19)
            self.font_lg = pygame.font.Font(cjk_bold, 26)
            self.font_xl = pygame.font.Font(cjk_bold, 40)
        else:
            fam = "microsoftjhenghei,simhei,arial"
            self.font_xs = pygame.font.SysFont(fam, 14)
            self.font_sm = pygame.font.SysFont(fam, 16)
            self.font_md = pygame.font.SysFont(fam, 19, bold=True)
            self.font_lg = pygame.font.SysFont(fam, 26, bold=True)
            self.font_xl = pygame.font.SysFont(fam, 40, bold=True)

        self.width = width
        self.height = height
        self.viewport_rect = pygame.Rect(0, 0, 100, 100)
        self.hud_rect = pygame.Rect(0, 0, 100, 100)
        self.mode_btn_rect = pygame.Rect(0, 0, 100, 30)

        # 互動按鈕判定框
        self.start_manual_rect = pygame.Rect(0, 0, 0, 0)
        self.start_calib_rect = pygame.Rect(0, 0, 0, 0)
        self.calib_skip_rect = pygame.Rect(0, 0, 0, 0)
        self.restart_rect = pygame.Rect(0, 0, 0, 0)
        self.menu_rect = pygame.Rect(0, 0, 0, 0)
        self.diff_rects = {}

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.laugh_badge = self._load_scaled_asset(project_root, "teacher_laugh.png", 165)
        self.peek_badge = self._load_scaled_asset(project_root, "teacher_peek.png", 155)

        self.update_layout(width, height)

    def _load_scaled_asset(self, project_root, filename, target_h):
        path = os.path.join(project_root, "assets", filename)
        if not os.path.exists(path):
            return None
        try:
            img = pygame.image.load(path).convert_alpha()
            w = max(20, int(img.get_width() * (target_h / max(1, img.get_height()))))
            return pygame.transform.smoothscale(img, (w, target_h))
        except Exception:
            return None

    def update_layout(self, width, height):
        self.width = max(1000, width)
        self.height = max(640, height)
        hud_w = 374
        top_h = 44
        self.viewport_rect = pygame.Rect(8, top_h + 6, self.width - hud_w - 24, self.height - top_h - 14)
        self.hud_rect = pygame.Rect(self.width - hud_w - 8, top_h + 6, hud_w, self.height - top_h - 14)
        self.mode_btn_rect = pygame.Rect(self.width - 215, 7, 205, 30)

    # ------------------------------------------------------------------
    # 頂部狀態列 + 右側生醫儀表板
    # ------------------------------------------------------------------
    def render_top_bar(self, surf, bio, exam, hw_bridge):
        pygame.draw.rect(surf, (18, 22, 32), (0, 0, self.width, 44))
        pygame.draw.line(surf, (52, 62, 84), (0, 43), (self.width, 43), 2)

        title = self.font_md.render("NeuroCheat: 生醫電子考場潛行", True, (110, 220, 255))
        surf.blit(title, (14, 10))

        # 考試計時與作答進度
        t_col = (255, 95, 95) if exam.time_remaining <= 30.0 else (120, 240, 160)
        exam_lbl = self.font_md.render(
            f"剩餘 {exam.time_remaining:05.1f}s | 進度 {exam.get_progress_str()}", True, t_col
        )
        surf.blit(exam_lbl, (315, 10))

        # 連線狀態
        bridge_txt = self.font_xs.render(hw_bridge.status_text[:44], True, (175, 190, 215))
        surf.blit(bridge_txt, (595, 14))

        # 模式切換按鈕
        is_ext = bio.mode == bio.MODE_EXTERNAL
        btn_bg = (36, 118, 86) if is_ext else (65, 78, 108)
        btn_border = (95, 235, 165) if is_ext else (130, 155, 205)
        pygame.draw.rect(surf, btn_bg, self.mode_btn_rect, border_radius=6)
        pygame.draw.rect(surf, btn_border, self.mode_btn_rect, 2, border_radius=6)
        mode_str = "[F1] 實機串流 (EXTERNAL)" if is_ext else "[F1] 鍵鼠模擬 (MANUAL)"
        mtxt = self.font_xs.render(mode_str, True, (245, 250, 255))
        surf.blit(
            mtxt,
            (
                self.mode_btn_rect.centerx - mtxt.get_width() // 2,
                self.mode_btn_rect.centery - mtxt.get_height() // 2,
            ),
        )

    def render_bio_dashboard(self, surf, bio, teacher, camera_yaw=0.0):
        x, y, w, h = self.hud_rect
        pygame.draw.rect(surf, (20, 24, 34), self.hud_rect, border_radius=10)
        pygame.draw.rect(surf, (58, 70, 96), self.hud_rect, 2, border_radius=10)

        cy = y + 10

        # 1. 老師懷疑值卡片
        cy = self._draw_suspicion_card(surf, x + 10, cy, w - 20, teacher)

        # 2. ECG 心電監測 + 即時示波器
        cy = self._draw_ecg_card(surf, x + 10, cy + 8, w - 20, bio)

        # 3. EMG 握力 & 疲勞度
        cy = self._draw_emg_card(surf, x + 10, cy + 8, w - 20, bio)

        # 4. EEG 專注度 & Stroop & 眨眼翻頁
        cy = self._draw_eeg_card(surf, x + 10, cy + 8, w - 20, bio)

        # 5. 底部快捷鍵說明
        foot_y = y + h - 54
        pygame.draw.line(surf, (45, 55, 75), (x + 12, foot_y - 4), (x + w - 12, foot_y - 4), 1)
        lines = [
            "[右鍵/空白]全開小抄  [F]微縫偷看  [Tab]小抄翻頁",
            "[R]深呼吸降心率  [Q/E]專注度  [Z/X]認知壓力  [F2]掃COM",
        ]
        for idx, line in enumerate(lines):
            t = self.font_xs.render(line, True, (150, 165, 190))
            surf.blit(t, (x + 12, foot_y + idx * 20))

    def _draw_card_box(self, surf, x, y, w, h, border_col=(55, 66, 88)):
        pygame.draw.rect(surf, (28, 34, 48), (x, y, w, h), border_radius=8)
        pygame.draw.rect(surf, border_col, (x, y, w, h), 1, border_radius=8)

    def _draw_bar(self, surf, x, y, w, h, ratio, fill_col, bg_col=(42, 48, 64)):
        pygame.draw.rect(surf, bg_col, (x, y, w, h), border_radius=4)
        fw = int(w * max(0.0, min(1.0, ratio)))
        if fw > 0:
            pygame.draw.rect(surf, fill_col, (x, y, fw, h), border_radius=4)

    def _draw_suspicion_card(self, surf, x, y, w, teacher):
        h = 74
        bcol = (220, 70, 70) if teacher.suspicion >= 65 else (58, 72, 98)
        self._draw_card_box(surf, x, y, w, h, bcol)

        hdr = self.font_sm.render(f"老師懷疑值: {teacher.suspicion:4.0f}%", True, (240, 240, 245))
        surf.blit(hdr, (x + 10, y + 7))

        cc_txt = self.font_xs.render(
            f"Close Call: {teacher.close_calls}  假動作: {teacher.false_alarms_count}",
            True,
            (175, 200, 230),
        )
        surf.blit(cc_txt, (x + w - cc_txt.get_width() - 10, y + 9))

        bar_col = (240, 65, 65) if teacher.suspicion >= 65 else ((245, 185, 55) if teacher.suspicion >= 35 else (75, 215, 130))
        self._draw_bar(surf, x + 10, y + 32, w - 20, 14, teacher.suspicion / 100.0, bar_col)

        tip = f"突襲: {teacher.silent_peeks_count} | 距離: {teacher.pos_z:.1f}m"
        if teacher.is_close_aisle():
            tip += " (極近!)"
        elif teacher.rush_mode:
            tip += " (衝刺!)"
        tip_col = (255, 115, 90) if teacher.is_close_aisle() else (185, 195, 210)
        surf.blit(self.font_xs.render(tip, True, tip_col), (x + 10, y + 51))
        return y + h

    def _draw_ecg_card(self, surf, x, y, w, bio):
        h = 166
        self._draw_card_box(surf, x, y, w, h)

        q_map = {
            "ok": ("訊號正常", (80, 220, 135)),
            "noisy": ("輕微雜訊", (245, 190, 60)),
            "bad": ("接觸不良(免罰)", (170, 175, 185)),
            "calib": ("校正中", (100, 200, 255)),
        }
        q_lbl, q_col = q_map.get(bio.ecg_quality, ("正常", (80, 220, 135)))

        bpm_str = f"ECG 心率: {bio.ecg_bpm:4.0f} BPM"
        surf.blit(self.font_sm.render(bpm_str, True, (245, 110, 125)), (x + 10, y + 8))

        q_pill = self.font_xs.render(q_lbl, True, q_col)
        surf.blit(q_pill, (x + w - q_pill.get_width() - 10, y + 9))

        delta_sign = "+" if bio.bpm_delta >= 0 else ""
        delta_col = (255, 100, 90) if bio.bpm_delta >= 9.0 else ((90, 235, 195) if bio.deep_breath_active else (190, 205, 225))
        sub = f"相對基線 {bio.bpm_base:.0f}: {delta_sign}{bio.bpm_delta:.1f} BPM"
        surf.blit(self.font_xs.render(sub, True, delta_col), (x + 10, y + 30))

        wave_tag = "真實實機波形" if bio.using_real_ecg_wave else "合成示波器"
        wt = self.font_xs.render(wave_tag, True, (90, 215, 255) if bio.using_real_ecg_wave else (130, 145, 165))
        surf.blit(wt, (x + w - wt.get_width() - 10, y + 30))

        # 示波器繪圖框
        osc = pygame.Rect(x + 10, y + 52, w - 20, 84)
        pygame.draw.rect(surf, (10, 16, 22), osc, border_radius=6)
        pygame.draw.rect(surf, (40, 75, 65), osc, 1, border_radius=6)
        # 網格線
        pygame.draw.line(surf, (22, 42, 38), (osc.left, osc.centery), (osc.right, osc.centery), 1)

        samples = list(bio.ecg_wave_buffer)
        if len(samples) >= 2:
            pts = []
            mid_y = osc.centery + 4
            amp_scale = osc.height * 0.36
            n = len(samples)
            for idx, v in enumerate(samples):
                px = osc.left + 4 + (idx / (n - 1)) * (osc.width - 8)
                py = max(osc.top + 4, min(osc.bottom - 4, mid_y - v * amp_scale))
                pts.append((px, py))
            line_col = (75, 245, 145) if bio.ecg_quality != "bad" else (140, 145, 155)
            pygame.draw.lines(surf, line_col, False, pts, 2)

        breath_msg = "[R] 深呼吸鎮定生效中..." if bio.deep_breath_active else "提示: 基線 +9 BPM 將引發懷疑，按住 R 深呼吸"
        bcol = (95, 240, 200) if bio.deep_breath_active else (150, 160, 180)
        surf.blit(self.font_xs.render(breath_msg, True, bcol), (x + 10, y + 143))
        return y + h

    def _draw_emg_card(self, surf, x, y, w, bio):
        h = 114
        self._draw_card_box(surf, x, y, w, h)

        if bio.emg_cramped:
            st_str, st_col = f"肌肉抽筋鎖定 ({bio.cramp_timer:.1f}s)", (255, 85, 85)
        elif bio.emg_signal_level >= 0.56:
            st_str, st_col = "抽屜全開 (高風險)", (255, 165, 65)
        elif bio.emg_signal_level >= 0.22:
            st_str, st_col = "微縫偷瞄中", (120, 225, 255)
        else:
            st_str, st_col = "已關閉 (安全)", (120, 220, 140)

        surf.blit(self.font_sm.render(f"EMG 握力: {bio.emg_signal_level * 100:3.0f}%", True, (245, 225, 110)), (x + 10, y + 8))
        st_lbl = self.font_xs.render(st_str, True, st_col)
        surf.blit(st_lbl, (x + w - st_lbl.get_width() - 10, y + 10))

        # 握力條 + 微縫/全開門檻刻度線
        bx, by, bw, bh = x + 10, y + 33, w - 20, 14
        g_col = (255, 145, 55) if bio.emg_signal_level >= 0.56 else (95, 215, 245)
        self._draw_bar(surf, bx, by, bw, bh, bio.emg_signal_level, g_col)
        for thresh in (0.22, 0.56):
            tx = int(bx + bw * thresh)
            pygame.draw.line(surf, (245, 245, 255), (tx, by - 2), (tx, by + bh + 2), 2)

        # 肌肉疲勞度條
        surf.blit(self.font_xs.render(f"手臂疲勞值: {bio.emg_fatigue:3.0f}% (滿100%會抽筋巨響!)", True, (205, 185, 175)), (x + 10, y + 57))
        f_col = (255, 70, 70) if bio.emg_fatigue >= 75 else ((245, 180, 60) if bio.emg_fatigue >= 45 else (110, 200, 145))
        self._draw_bar(surf, x + 10, y + 79, w - 20, 12, bio.emg_fatigue / 100.0, f_col)
        return y + h

    def _draw_eeg_card(self, surf, x, y, w, bio):
        h = 138
        self._draw_card_box(surf, x, y, w, h)

        q_col = (85, 220, 140) if bio.eeg_quality == "ok" else (245, 165, 65)
        surf.blit(self.font_sm.render(f"EEG 專注清晰度: {bio.eeg_focus:3.0f}%", True, (150, 185, 255)), (x + 10, y + 8))
        ql = self.font_xs.render("BrainLink OK" if bio.eeg_quality == "ok" else "訊號干擾", True, q_col)
        surf.blit(ql, (x + w - ql.get_width() - 10, y + 10))

        self._draw_bar(surf, x + 10, y + 32, w - 20, 13, bio.eeg_focus / 100.0, (95, 165, 255))

        # Stroop 認知超載指標
        stroop_col = (245, 85, 110) if bio.eeg_stroop >= 55 else (175, 140, 245)
        s_txt = f"Stroop 認知超載: {bio.eeg_stroop:3.0f}%" + (" (選項字色干擾!)" if bio.eeg_stroop > 50 else "")
        surf.blit(self.font_xs.render(s_txt, True, stroop_col), (x + 10, y + 55))
        self._draw_bar(surf, x + 10, y + 76, w - 20, 12, bio.eeg_stroop / 100.0, stroop_col)

        # 小抄頁數 + 眨眼指示
        page_str = f"目前小抄頁: 第 {bio.cheat_page + 1}/2 頁 ({'Q1~Q5' if bio.cheat_page == 0 else 'Q6~Q10'})"
        surf.blit(self.font_xs.render(page_str, True, (240, 230, 150)), (x + 10, y + 101))
        blink_col = (100, 255, 190) if bio.blink_detected else (75, 85, 105)
        pygame.draw.circle(surf, blink_col, (x + w - 20, y + 110), 6)
        bl_lbl = self.font_xs.render("Fp1眨眼", True, (175, 190, 210))
        surf.blit(bl_lbl, (x + w - 76, y + 101))
        return y + h

    # ------------------------------------------------------------------
    # 主標題畫面
    # ------------------------------------------------------------------
    def render_title_screen(self, surf, hw_bridge, difficulty="NORMAL"):
        surf.fill((14, 18, 28))
        cx = self.width // 2

        title = self.font_xl.render("NeuroCheat: 生醫電子考場潛行", True, (110, 225, 255))
        surf.blit(title, (cx - title.get_width() // 2, 34))

        sub = self.font_md.render(
            "整合 Exp 2 (ECG/EMG 類比電路 + 數位濾波) × Exp 3 (BrainLink 專注/Stroop/眨眼翻頁)",
            True,
            (195, 210, 232),
        )
        surf.blit(sub, (cx - sub.get_width() // 2, 86))

        # 三張生醫特色介紹卡
        cards = [
            (
                "Exp 2 EMG 肌電控制",
                (250, 215, 95),
                [
                    "輕握微縫僅見前半 / 全力拉開全頁",
                    "老師逼近走道時連微縫都會被抓包!",
                    "持續緊抓過久會疲勞抽筋撞響抽屜!",
                ],
            ),
            (
                "Exp 2 ECG 心電情緒",
                (255, 115, 130),
                [
                    "依個人開局基線追蹤相對 +ΔBPM",
                    "接觸不良自動品質門控防誤抓",
                    "按住 [R] 深呼吸可同時降心跳+提專注",
                ],
            ),
            (
                "Exp 3 BrainLink 腦波",
                (130, 185, 255),
                [
                    "專注度過低會模糊小抄，靠 R 回穩",
                    "雙眨眼 / [Tab] 免手翻閱第2頁小抄",
                    "Stroop 超載時考卷選項會字色干擾",
                ],
            ),
        ]
        cw = 340
        gap = 26
        start_x = cx - (3 * cw + 2 * gap) // 2
        for i, (ctitle, col, bullets) in enumerate(cards):
            rx = start_x + i * (cw + gap)
            ry = 132
            pygame.draw.rect(surf, (24, 30, 44), (rx, ry, cw, 168), border_radius=12)
            pygame.draw.rect(surf, col, (rx, ry, cw, 168), 2, border_radius=12)
            t = self.font_lg.render(ctitle, True, col)
            surf.blit(t, (rx + 18, ry + 14))
            for bi, b in enumerate(bullets):
                bt = self.font_sm.render("• " + b, True, (220, 228, 240))
                surf.blit(bt, (rx + 18, ry + 58 + bi * 32))

        # 考前提示與難度選擇列
        tip_box = pygame.Rect(cx - 535, 316, 1070, 92)
        pygame.draw.rect(surf, (22, 32, 46), tip_box, border_radius=10)
        pygame.draw.rect(surf, (70, 115, 165), tip_box, 1, border_radius=10)
        tips = [
            "考場規則：隨機抽 10 題打亂選項，90 分及格！小抄分 Q1~Q5 / Q6~Q10 兩頁，按 [V] 或下移滑鼠可傾身放大考卷。",
            "鄰座阿明與學霸小華隨時間進度作答，切忌對著走道過來的奶娃老師左顧右盼！",
            f"感測器連線狀態：{hw_bridge.status_text}",
        ]
        for idx, line in enumerate(tips):
            surf.blit(self.font_sm.render(line, True, (205, 222, 245)), (tip_box.x + 20, tip_box.y + 10 + idx * 26))

        # 難度挑選按鈕
        diff_opts = [
            ("EASY", "輕鬆練習 (115s | 遠距巡邏)", (65, 165, 115)),
            ("NORMAL", "標準期末考 (95s | 逼近走道+假動作)", (225, 165, 55)),
            ("HARD", "地獄大刀教授 (80s | 高頻突襲)", (225, 75, 75)),
        ]
        dw, dh, dgap = 330, 44, 22
        dx0 = cx - (3 * dw + 2 * dgap) // 2
        self.diff_rects = {}
        for i, (key, d_lbl, d_col) in enumerate(diff_opts):
            dr = pygame.Rect(dx0 + i * (dw + dgap), 426, dw, dh)
            self.diff_rects[key] = dr
            active = difficulty == key
            bg = (42, 54, 76) if active else (24, 30, 42)
            pygame.draw.rect(surf, bg, dr, border_radius=9)
            pygame.draw.rect(surf, d_col if active else (65, 76, 98), dr, 3 if active else 1, border_radius=9)
            dl = self.font_sm.render(("[已選] " if active else "") + d_lbl, True, (255, 255, 255) if active else (165, 178, 200))
            surf.blit(dl, (dr.centerx - dl.get_width() // 2, dr.centery - dl.get_height() // 2))

        # 兩個開始按鈕
        bw, bh = 408, 62
        self.start_manual_rect = pygame.Rect(cx - bw - 18, 496, bw, bh)
        self.start_calib_rect = pygame.Rect(cx + 18, 496, bw, bh)

        pygame.draw.rect(surf, (42, 130, 215), self.start_manual_rect, border_radius=12)
        pygame.draw.rect(surf, (135, 215, 255), self.start_manual_rect, 2, border_radius=12)
        m1 = self.font_lg.render("直接開始考場 (鍵鼠/快速)", True, (255, 255, 255))
        surf.blit(m1, (self.start_manual_rect.centerx - m1.get_width() // 2, self.start_manual_rect.centery - m1.get_height() // 2))

        pygame.draw.rect(surf, (38, 145, 96), self.start_calib_rect, border_radius=12)
        pygame.draw.rect(surf, (115, 245, 175), self.start_calib_rect, 2, border_radius=12)
        m2 = self.font_lg.render("15 秒基線校正後開考 (實機推薦)", True, (255, 255, 255))
        surf.blit(m2, (self.start_calib_rect.centerx - m2.get_width() // 2, self.start_calib_rect.centery - m2.get_height() // 2))

        hint = self.font_sm.render("按 [Enter] 開考 | [C] 進入 15 秒校正 | 點選上方難度列調整挑戰度 | [F1] 切換實機/模擬", True, (150, 165, 185))
        surf.blit(hint, (cx - hint.get_width() // 2, 580))

    # ------------------------------------------------------------------
    # 考前 15 秒生理基線校正精靈
    # ------------------------------------------------------------------
    def render_calibration_screen(self, surf, step_idx, step_elapsed, step_dur, bio):
        surf.fill((14, 20, 30))
        cx = self.width // 2

        steps = [
            ("步驟 1 / 3：靜息放鬆基線 (5 秒)", "請雙手自然垂放不握拳、正常平穩呼吸", "採樣項目：靜息心率 (bpm_base) + EMG 零點噪音"),
            ("步驟 2 / 3：最大握拳出力 MVC (5 秒)", "請持續緊握手臂 / 握緊測試按鈕約 5 秒", "採樣項目：EMG 個人最大肌電包絡線 (MVC)"),
            ("步驟 3 / 3：專注凝視準備 (5 秒)", "請看著螢幕中央文字默念題目公式準備開考", "採樣項目：EEG 專注力連線確認"),
        ]
        title, instr, target = steps[min(2, step_idx)]

        hdr = self.font_xl.render("考前生理基線個人化校正", True, (110, 230, 255))
        surf.blit(hdr, (cx - hdr.get_width() // 2, 62))

        card = pygame.Rect(cx - 420, 140, 840, 340)
        pygame.draw.rect(surf, (24, 32, 46), card, border_radius=14)
        pygame.draw.rect(surf, (80, 185, 245), card, 2, border_radius=14)

        t1 = self.font_lg.render(title, True, (255, 225, 120))
        t2 = self.font_lg.render(instr, True, (240, 248, 255))
        t3 = self.font_md.render(target, True, (165, 205, 235))
        surf.blit(t1, (cx - t1.get_width() // 2, 175))
        surf.blit(t2, (cx - t2.get_width() // 2, 235))
        surf.blit(t3, (cx - t3.get_width() // 2, 285))

        # 進度條
        rem = max(0.0, step_dur - step_elapsed)
        ratio = min(1.0, step_elapsed / max(0.1, step_dur))
        self._draw_bar(surf, cx - 320, 340, 640, 22, ratio, (90, 230, 165))
        rem_lbl = self.font_md.render(f"本階段剩餘 {rem:0.1f} 秒", True, (235, 245, 255))
        surf.blit(rem_lbl, (cx - rem_lbl.get_width() // 2, 374))

        # 即時生理讀數預覽
        live = self.font_md.render(
            f"即時讀數 | 心率: {bio.ecg_bpm:.0f} BPM ({bio.ecg_quality}) | EMG: {bio.emg_signal_level*100:.0f}% | EEG 專注: {bio.eeg_focus:.0f}%",
            True,
            (150, 235, 210),
        )
        surf.blit(live, (cx - live.get_width() // 2, 425))

        self.calib_skip_rect = pygame.Rect(cx - 160, 525, 320, 54)
        pygame.draw.rect(surf, (75, 86, 112), self.calib_skip_rect, border_radius=10)
        pygame.draw.rect(surf, (150, 170, 210), self.calib_skip_rect, 2, border_radius=10)
        sk = self.font_md.render("跳過校正，直接使用預設值開考", True, (245, 250, 255))
        surf.blit(sk, (self.calib_skip_rect.centerx - sk.get_width() // 2, self.calib_skip_rect.centery - sk.get_height() // 2))

    # ------------------------------------------------------------------
    # 結算畫面 (被抓 / 超時失敗 / 過關勝利)
    # ------------------------------------------------------------------
    def _render_end_summary(self, surf, heading, h_col, subtitle, exam, bio, teacher, csv_path, show_laugh=False):
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((10, 14, 22, 228))
        surf.blit(overlay, (0, 0))

        cx = self.width // 2
        card = pygame.Rect(cx - 435, 68, 870, 565)
        pygame.draw.rect(surf, (22, 28, 42), card, border_radius=14)
        pygame.draw.rect(surf, h_col, card, 3, border_radius=14)

        t_head = self.font_xl.render(heading, True, h_col)
        surf.blit(t_head, (cx - t_head.get_width() // 2, 98))

        t_sub = self.font_md.render(subtitle, True, (235, 240, 248))
        surf.blit(t_sub, (cx - t_sub.get_width() // 2, 160))

        score = exam.calculate_score()
        stats = [
            f"期末考成績：{score} / 100 分 （進度 {exam.get_progress_str()} | 難度 {exam.difficulty}）",
            f"最高心率：{bio.max_bpm:.1f} BPM （基線 {bio.bpm_base:.0f} 峰值 +{bio.max_bpm_delta:.1f} BPM）",
            f"驚險閃過: {teacher.close_calls} 次 | 假動作: {teacher.false_alarms_count} 次 | 走道逼近: {teacher.aisle_walks_count} 次",
            f"誠實答對：{exam.honest_correct_count} 題 | 開小抄/偷看：{exam.cheated_count} 題",
            f"遙測存檔：{os.path.basename(csv_path) if csv_path else '尚未匯出'}",
        ]
        for idx, line in enumerate(stats):
            st = self.font_md.render(line, True, (205, 220, 242))
            surf.blit(st, (card.x + 42, 225 + idx * 45))

        # 結算看板右側顯示 奶娃大笑 (被抓/超時) 或 不甘心偷瞄 (過關)
        badge = self.laugh_badge if show_laugh else self.peek_badge
        if badge is not None:
            surf.blit(badge, (card.right - badge.get_width() - 28, 228))

        self.restart_rect = pygame.Rect(cx - 290, 515, 250, 58)
        self.menu_rect = pygame.Rect(cx + 40, 515, 250, 58)

        pygame.draw.rect(surf, (40, 140, 95), self.restart_rect, border_radius=10)
        pygame.draw.rect(surf, (115, 240, 175), self.restart_rect, 2, border_radius=10)
        rtxt = self.font_lg.render("再挑戰一次 [R]", True, (255, 255, 255))
        surf.blit(rtxt, (self.restart_rect.centerx - rtxt.get_width() // 2, self.restart_rect.centery - rtxt.get_height() // 2))

        pygame.draw.rect(surf, (62, 76, 106), self.menu_rect, border_radius=10)
        pygame.draw.rect(surf, (145, 168, 212), self.menu_rect, 2, border_radius=10)
        mtxt = self.font_lg.render("回主畫面 [M]", True, (255, 255, 255))
        surf.blit(mtxt, (self.menu_rect.centerx - mtxt.get_width() // 2, self.menu_rect.centery - mtxt.get_height() // 2))

    def render_game_over(self, surf, state_name, exam, bio, teacher, csv_path=None):
        if state_name == "BUSTED":
            heading = "作弊被奶娃老師當場抓包！"
            sub = teacher.busted_reason or "你在監考老師視線下動作過於明顯，本次成績以 0 分計算！"
        else:
            heading = f"考試時間結束！未達及格標準 ({exam.calculate_score()} 分)"
            sub = "必須在時限內拿到 90 分以上才算過關，下次控制好握力與呼吸節奏！"
        self._render_end_summary(surf, heading, (255, 85, 85), sub, exam, bio, teacher, csv_path, show_laugh=True)

    def render_victory(self, surf, exam, bio, teacher, csv_path=None):
        score = exam.calculate_score()
        rank = "A+ 完美神偷" if score == 100 else "A 考場過關"
        if exam.cheated_count == 0 and score >= 90:
            rank = "A+ 真材實料電神"
        heading = f"恭喜通過期末考！[{rank}]"
        sub = f"你在高壓監考下成功穩住心電與腦波，拿下 {score} 分！"
        self._render_end_summary(surf, heading, (85, 240, 145), sub, exam, bio, teacher, csv_path, show_laugh=False)
