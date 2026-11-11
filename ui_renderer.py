"""
NeuroCheat UI 與 3D 教室整合渲染模組 (UIRenderer)
結合 `Classroom3DRenderer` 實作：
1. 3D 第一人稱教室視角 (滑鼠控制視角 Yaw/Pitch，抬頭看黑板奶龍、左右轉頭看其他學生、低頭看書桌考卷與抽屜小抄)
2. 玩家坐在書桌前，考卷平鋪在書桌桌面上，可直接點擊桌面考卷作答
3. 小抄藏在書桌抽屜裡，按空白鍵/EMG按鈕打開小抄時，會伸出雙手拉開抽屜並攤開小抄
4. 右側懸浮式生醫訊號監控儀表板 (支援模式一：手動調控模式 / 模式二：外部訊號輸入模式)
"""

import pygame
import math
import os
from classroom_3d import Classroom3DRenderer


class UIRenderer:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height

        # 初始化 3D 教室透視建模渲染器
        self.classroom_3d = Classroom3DRenderer(width, height)
        self.hud_rect = pygame.Rect(width - 385, 48, 375, 655)

        # 載入經典迷因「奶龍」透明貼圖
        self.img_nailong = None
        try:
            if os.path.exists("nailong.png"):
                self.img_nailong = pygame.image.load("nailong.png").convert_alpha()
        except Exception as e:
            print("[UIRenderer] 載入 nailong.png 失敗:", e)

        font_path = pygame.font.match_font("microsoftjhenghei") or \
                    pygame.font.match_font("simsun") or \
                    pygame.font.match_font("arial")

        try:
            self.font_title = pygame.font.Font(font_path, 26)
            self.font_main = pygame.font.Font(font_path, 19)
            self.font_large = pygame.font.Font(font_path, 32)
            self.font_small = pygame.font.Font(font_path, 14)
            self.font_bold = pygame.font.Font(font_path, 21)
            self.font_bold.set_bold(True)
            self.font_large.set_bold(True)
        except Exception:
            self.font_title = pygame.font.SysFont("sans-serif", 24)
            self.font_main = pygame.font.SysFont("sans-serif", 18)
            self.font_large = pygame.font.SysFont("sans-serif", 30)
            self.font_small = pygame.font.SysFont("sans-serif", 14)
            self.font_bold = pygame.font.SysFont("sans-serif", 20)

        # 顏色常量
        self.COLOR_BG = (210, 218, 226)
        self.COLOR_BOARD = (34, 76, 56)
        self.COLOR_PAPER = (252, 250, 242)
        self.COLOR_CHEAT = (255, 249, 196)
        self.COLOR_TEXT = (30, 30, 30)
        self.COLOR_ACCENT = (41, 128, 185)
        self.COLOR_ALERT = (231, 76, 60)
        self.COLOR_WARN = (230, 126, 34)
        self.COLOR_SUCCESS = (46, 204, 113)

        # 互動按鈕 Rect 記錄
        self.btn_options = []
        self.btn_prev = pygame.Rect(0, 0, 0, 0)
        self.btn_next = pygame.Rect(0, 0, 0, 0)
        self.btn_submit = pygame.Rect(0, 0, 0, 0)
        self.btn_emg = pygame.Rect(0, 0, 0, 0)
        self.btn_breathe = pygame.Rect(0, 0, 0, 0)
        self.btn_ecg_up = pygame.Rect(0, 0, 0, 0)
        self.btn_ecg_down = pygame.Rect(0, 0, 0, 0)
        self.btn_focus_up = pygame.Rect(0, 0, 0, 0)
        self.btn_focus_down = pygame.Rect(0, 0, 0, 0)
        self.btn_restart = pygame.Rect(0, 0, 0, 0)
        self.btn_back_title = pygame.Rect(0, 0, 0, 0)

        self.btn_mode_manual = pygame.Rect(0, 0, 0, 0)
        self.btn_mode_external = pygame.Rect(0, 0, 0, 0)
        self.btn_switch_mode = pygame.Rect(0, 0, 0, 0)
        self.btn_cycle_port = pygame.Rect(0, 0, 0, 0)

        self.feedback_message = ""
        self.feedback_timer = 0.0
        self.feedback_color = (255, 255, 255)
        self.active_btn_name = None
        self.btn_press_timer = 0.0

    def trigger_feedback(self, text, color=(46, 204, 113), btn_name=None):
        self.feedback_message = text
        self.feedback_timer = 1.6
        self.feedback_color = color
        self.active_btn_name = btn_name
        self.btn_press_timer = 0.22

    def update_feedback(self, dt):
        if self.feedback_timer > 0:
            self.feedback_timer = max(0.0, self.feedback_timer - dt)
        if self.btn_press_timer > 0:
            self.btn_press_timer = max(0.0, self.btn_press_timer - dt)
            if self.btn_press_timer <= 0:
                self.active_btn_name = None

    def update_camera(self, mouse_pos, dt):
        """每幀依據滑鼠位置平滑更新 3D 教室相機視角"""
        self.classroom_3d.camera.update_from_mouse(mouse_pos, dt, hud_rect=self.hud_rect)

    def _get_anim_rect_and_active(self, rect, btn_name):
        is_pressed = (btn_name is not None and self.active_btn_name == btn_name and self.btn_press_timer > 0)
        draw_rect = rect.move(0, 2) if is_pressed else rect
        return draw_rect, is_pressed

    def render_3d_classroom_world(self, teacher, exam, bio, mouse_pos):
        """
        一次渲染完整的 3D 第一人稱教室世界：
        1. 教室立體牆面、地板、窗戶、講台、黑板、蜂鳴器
        2. 旁邊與前排的其他學生 (3D 桌椅與動態考生) + 奶龍監考官 3D 巡邏
        3. 玩家正前方的書桌、桌面考卷、桌下抽屜與「伸手拉開抽屜翻小抄」動畫
        """
        # 1. 繪製 3D 教室外殼與黑板
        bb_pts, buzz_pts = self.classroom_3d.render_room_shell(self.screen, teacher)

        # 在 3D 黑板上繪製粉筆字與蜂鳴器文字
        if bb_pts and len(bb_pts) >= 4:
            bxs = [p[0] for p in bb_pts]
            bys = [p[1] for p in bb_pts]
            bx_min, bx_max = min(bxs), max(bxs)
            by_min, by_max = min(bys), max(bys)
            if bx_max - bx_min > 180 and by_max - by_min > 45:
                t1 = self.font_small.render("【生醫工程期末考】嚴禁偷看抽屜小抄！違者當掉！", True, (235, 242, 235))
                t2 = self.font_small.render("移動滑鼠可轉動視角：抬頭看奶龍 | 左右看其他同學 | 低頭看書桌考卷與抽屜", True, (195, 230, 200))
                self.screen.blit(t1, (bx_min + 18, by_min + 10))
                self.screen.blit(t2, (bx_min + 18, by_min + 32))

        if buzz_pts and len(buzz_pts) >= 4:
            zxs = [p[0] for p in buzz_pts]
            zys = [p[1] for p in buzz_pts]
            zx_c = (min(zxs) + max(zxs)) // 2
            zy_c = (min(zys) + max(zys)) // 2
            b_txt = self.font_small.render("🚨逼逼警報!" if teacher.buzzer_active else "蜂鳴器靜音", True, (0, 0, 0) if teacher.buzzer_active else (210, 215, 220))
            self.screen.blit(b_txt, (zx_c - b_txt.get_width() // 2, zy_c - b_txt.get_height() // 2))

        # 2. 繪製教室裡的其他學生與 3D 奶龍監考官
        self.classroom_3d.render_classmates_and_teacher(
            self.screen, teacher, self.img_nailong, self.font_small, self.font_bold
        )

        # 3. 繪製玩家書桌、桌面考卷、書桌抽屜與伸手翻小抄動畫
        (
            self.btn_options,
            self.btn_prev,
            self.btn_next,
            self.btn_submit,
        ) = self.classroom_3d.render_player_desk_and_drawer(
            self.screen,
            exam,
            bio,
            mouse_pos,
            (self.font_small, self.font_main, self.font_bold),
            self._get_anim_rect_and_active,
        )

        # 4. 畫面左上角顯示奶龍即時警戒狀態條與滑鼠視角方位指示器
        desc, color = teacher.get_status_description()
        status_bg = pygame.Rect(14, 48, self.width - 410, 34)
        pygame.draw.rect(self.screen, (25, 32, 42), status_bg, border_radius=6)
        pygame.draw.rect(self.screen, color, status_bg, 2, border_radius=6)
        txt_status = self.font_bold.render(desc, True, color)
        self.screen.blit(txt_status, (status_bg.x + 12, status_bg.y + 4))

        # 視角方位角小提示
        cam = self.classroom_3d.camera
        yaw_deg = int(math.degrees(cam.yaw))
        pitch_deg = int(math.degrees(cam.pitch))
        if yaw_deg < -12:
            look_dir = "★ 視角：往左轉頭看鄰座同學與窗戶"
        elif yaw_deg > 12:
            look_dir = "★ 視角：往右轉頭看鄰座同學與教室門"
        elif pitch_deg > -10:
            look_dir = "★ 視角：抬頭注視黑板與奶龍監考官"
        elif pitch_deg < -20:
            look_dir = "★ 視角：低頭注視書桌考卷與抽屜內部"
        else:
            look_dir = "★ 視角：正前方書桌與講台 (移動滑鼠可自由轉頭)"

        cam_badge = pygame.Rect(14, 86, 420, 26)
        pygame.draw.rect(self.screen, (30, 40, 52), cam_badge, border_radius=5)
        pygame.draw.rect(self.screen, (90, 150, 210), cam_badge, 1, border_radius=5)
        t_cam = self.font_small.render(f"{look_dir} ({yaw_deg}°, {pitch_deg}°)", True, (190, 230, 255))
        self.screen.blit(t_cam, (cam_badge.x + 10, cam_badge.y + 3))

    def render_feedback_toast(self):
        if self.feedback_timer <= 0 or not self.feedback_message:
            return

        alpha = min(255, int(self.feedback_timer * 255 / 0.5))
        toast_surf = self.font_bold.render(self.feedback_message, True, (255, 255, 255))
        pad_x = 20
        pad_y = 8
        box_w = toast_surf.get_width() + pad_x * 2
        box_h = toast_surf.get_height() + pad_y * 2

        bg_surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pygame.draw.rect(bg_surf, (20, 28, 40, min(240, alpha)), (0, 0, box_w, box_h), border_radius=8)
        pygame.draw.rect(bg_surf, (*self.feedback_color, alpha), (0, 0, box_w, box_h), 2, border_radius=8)

        toast_surf.set_alpha(alpha)
        bg_surf.blit(toast_surf, (pad_x, pad_y))

        center_x = (self.width - 385) // 2
        self.screen.blit(bg_surf, (max(15, center_x - box_w // 2), 118))

    def render_header(self, exam, bio=None):
        hud_h = 42
        hud_rect = pygame.Rect(0, 0, self.width, hud_h)
        pygame.draw.rect(self.screen, (28, 40, 54), hud_rect)

        title_surf = self.font_bold.render("NeuroCheat 3D 考場：生醫工程期末考", True, (255, 255, 255))
        self.screen.blit(title_surf, (15, 8))

        if bio is not None:
            if bio.is_external_mode():
                mode_tag = "【模式二：外部訊號輸入】"
                tag_col = (155, 89, 182)
            else:
                mode_tag = "【模式一：手動調控測試】"
                tag_col = (39, 174, 96)
            tag_rect = pygame.Rect(380, 7, 190, 28)
            pygame.draw.rect(self.screen, tag_col, tag_rect, border_radius=5)
            t_tag = self.font_small.render(mode_tag, True, (255, 255, 255))
            self.screen.blit(t_tag, (tag_rect.centerx - t_tag.get_width() // 2, tag_rect.y + 5))

        t_color = (255, 100, 100) if exam.time_left < 30 else (255, 255, 255)
        mins = int(exam.time_left) // 60
        secs = int(exam.time_left) % 60
        time_str = f"剩餘時間：{mins:02d}:{secs:02d}"
        time_surf = self.font_bold.render(time_str, True, t_color)
        self.screen.blit(time_surf, (self.width // 2 - 45, 8))

        score = exam.calculate_score()
        score_color = self.COLOR_SUCCESS if score >= 90 else (255, 215, 0)
        score_str = f"已答: {exam.answered_count()}/10 | 預估分: {score} 分 (過關: 90分)"
        score_surf = self.font_main.render(score_str, True, score_color)
        self.screen.blit(score_surf, (self.width - score_surf.get_width() - 18, 9))

    def render_bio_dashboard(self, bio, mouse_pos, hw_bridge=None):
        """
        繪製右側懸浮式生醫訊號監測儀表板 (375px 寬)，保留左側 900px 完整 3D 教室視野
        """
        dash_rect = self.hud_rect
        # 半透明深色科技面板
        panel_surf = pygame.Surface((dash_rect.width, dash_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(panel_surf, (20, 26, 34, 232), (0, 0, dash_rect.width, dash_rect.height), border_radius=10)
        pygame.draw.rect(panel_surf, (65, 85, 110, 255), (0, 0, dash_rect.width, dash_rect.height), 2, border_radius=10)
        self.screen.blit(panel_surf, dash_rect.topleft)

        is_ext = bio.is_external_mode()

        # 抬頭與模式切換按鈕
        dash_title = self.font_bold.render("★ 生醫生理訊號監控儀", True, (100, 210, 255))
        self.screen.blit(dash_title, (dash_rect.x + 14, dash_rect.y + 10))

        self.btn_switch_mode = pygame.Rect(dash_rect.x + 14, dash_rect.y + 40, dash_rect.width - 28, 30)
        sw_rect, sw_pressed = self._get_anim_rect_and_active(self.btn_switch_mode, "MODE_SWITCH")
        sw_col = (142, 68, 173) if is_ext else (39, 174, 96)
        pygame.draw.rect(self.screen, sw_col, sw_rect, border_radius=5)
        pygame.draw.rect(self.screen, (255, 230, 80) if sw_pressed else (220, 220, 220), sw_rect, 2 if sw_pressed else 1, border_radius=5)
        sw_txt_str = "★ 目前：外部訊號模式 (點此或按 M 切換)" if is_ext else "★ 目前：手動調控模式 (點此或按 M 切換)"
        sw_txt = self.font_small.render(sw_txt_str, True, (255, 255, 255))
        self.screen.blit(sw_txt, (sw_rect.centerx - sw_txt.get_width() // 2, sw_rect.centery - sw_txt.get_height() // 2))

        # ==================== 1. EMG 手部伸入抽屜打開小抄 (以按鈕代替) ====================
        emg_y = dash_rect.y + 82
        txt_emg_title = self.font_main.render("1. EMG 肌電 [伸手拉開抽屜看小抄]", True, (255, 255, 255))
        self.screen.blit(txt_emg_title, (dash_rect.x + 14, emg_y))

        self.btn_emg = pygame.Rect(dash_rect.x + 14, emg_y + 26, dash_rect.width - 28, 42)
        emg_draw_rect, emg_pressed = self._get_anim_rect_and_active(self.btn_emg, "EMG")
        btn_col = (231, 76, 60) if bio.emg_active else (52, 152, 219)
        pygame.draw.rect(self.screen, btn_col, emg_draw_rect, border_radius=6)
        pygame.draw.rect(self.screen, (255, 230, 80) if emg_pressed else (255, 255, 255), emg_draw_rect, 3 if emg_pressed else 2, border_radius=6)

        btn_label = "【已伸手打開抽屜小抄】空白鍵/點此收回" if bio.emg_active else "【小抄在抽屜裡】按空白鍵/點此伸手打開"
        txt_btn = self.font_main.render(btn_label, True, (255, 255, 255))
        self.screen.blit(txt_btn, (emg_draw_rect.centerx - txt_btn.get_width() // 2, emg_draw_rect.centery - txt_btn.get_height() // 2))

        bar_bg = pygame.Rect(dash_rect.x + 14, emg_y + 74, dash_rect.width - 28, 22)
        pygame.draw.rect(self.screen, (40, 45, 55), bar_bg, border_radius=4)
        active_w = int(bio.emg_signal_level * bar_bg.width)
        if active_w > 0:
            bar_color = (255, 80, 80) if bio.emg_signal_level > 0.6 else (100, 220, 100)
            pygame.draw.rect(self.screen, bar_color, (bar_bg.x, bar_bg.y, active_w, bar_bg.height), border_radius=4)
        txt_level = self.font_small.render(f"伸手抽屜開度 (EMG電位): {bio.emg_signal_level*100:.0f}%", True, (230, 230, 230))
        self.screen.blit(txt_level, (bar_bg.x + 10, bar_bg.y + 2))

        # ==================== 2. ECG 心率與示波器 ====================
        ecg_y = dash_rect.y + 190
        ecg_status_color = self.COLOR_ALERT if bio.ecg_bpm > 95 else (100, 255, 150)
        ecg_hint = "[外部輸入🔒]" if is_ext else "(↑/↓ 微調)"
        txt_ecg = self.font_main.render(f"2. ECG 心電 [{bio.ecg_bpm:.0f} BPM] {ecg_hint}", True, ecg_status_color)
        self.screen.blit(txt_ecg, (dash_rect.x + 14, ecg_y))

        scope_rect = pygame.Rect(dash_rect.x + 14, ecg_y + 26, dash_rect.width - 28, 82)
        pygame.draw.rect(self.screen, (10, 18, 14), scope_rect, border_radius=6)
        pygame.draw.rect(self.screen, (40, 80, 50), scope_rect, 1, border_radius=6)

        for gx in range(scope_rect.x, scope_rect.right, 28):
            pygame.draw.line(self.screen, (18, 35, 25), (gx, scope_rect.y), (gx, scope_rect.bottom))
        for gy in range(scope_rect.y, scope_rect.bottom, 20):
            pygame.draw.line(self.screen, (18, 35, 25), (scope_rect.x, gy), (scope_rect.right, gy))

        wave_pts = []
        wave_list = list(bio.ecg_wave)
        mid_y = scope_rect.y + scope_rect.height // 2
        step_x = scope_rect.width / len(wave_list)
        for idx, val in enumerate(wave_list):
            px = scope_rect.x + idx * step_x
            py = mid_y - (val * 30)
            wave_pts.append((px, py))

        if len(wave_pts) > 1:
            line_color = (255, 60, 60) if bio.ecg_bpm > 100 else (50, 255, 120)
            pygame.draw.lines(self.screen, line_color, False, wave_pts, 2)

        # ECG 控制按鈕列
        ctrl_ecg_y = ecg_y + 114
        self.btn_ecg_down = pygame.Rect(dash_rect.x + 14, ctrl_ecg_y, 95, 34)
        self.btn_ecg_up = pygame.Rect(dash_rect.x + 116, ctrl_ecg_y, 95, 34)
        self.btn_breathe = pygame.Rect(dash_rect.x + 218, ctrl_ecg_y, 143, 34)

        ed_rect, ed_p = self._get_anim_rect_and_active(self.btn_ecg_down, "ECG_DOWN")
        eu_rect, eu_p = self._get_anim_rect_and_active(self.btn_ecg_up, "ECG_UP")
        br_rect, br_p = self._get_anim_rect_and_active(self.btn_breathe, "BREATHE")

        btn_ecg_bg = (38, 42, 48) if is_ext else (65, 80, 100)
        btn_ecg_fg = (110, 115, 125) if is_ext else (235, 240, 245)
        for r_b, is_p, lbl in [
            (ed_rect, ed_p, "[鎖]BPM▼" if is_ext else "BPM▼ (↓)"),
            (eu_rect, eu_p, "[鎖]BPM▲" if is_ext else "BPM▲ (↑)"),
        ]:
            pygame.draw.rect(self.screen, btn_ecg_bg, r_b, border_radius=5)
            pygame.draw.rect(self.screen, (255, 220, 80) if is_p else (100, 115, 135), r_b, 2 if is_p else 1, border_radius=5)
            ts = self.font_small.render(lbl, True, btn_ecg_fg)
            self.screen.blit(ts, (r_b.centerx - ts.get_width() // 2, r_b.centery - ts.get_height() // 2))

        breathe_col = (38, 42, 48) if is_ext else ((39, 174, 96) if bio.is_deep_breathing else (46, 95, 78))
        pygame.draw.rect(self.screen, breathe_col, br_rect, border_radius=5)
        pygame.draw.rect(self.screen, (255, 220, 80) if br_p else (100, 145, 125), br_rect, 2 if br_p else 1, border_radius=5)
        t_br = self.font_small.render("[鎖定]外部控制" if is_ext else "★ 深呼吸(按R)", True, btn_ecg_fg if is_ext else (255, 255, 255))
        self.screen.blit(t_br, (br_rect.centerx - t_br.get_width() // 2, br_rect.centery - t_br.get_height() // 2))

        # ==================== 3. EEG 腦波專注度 ====================
        eeg_y = dash_rect.y + 350
        eeg_hint = "[外部輸入🔒]" if is_ext else "(W/S 微調)"
        txt_eeg = self.font_main.render(f"3. EEG 專注度 [{bio.eeg_focus:.0f}%] {eeg_hint}", True, (255, 255, 255))
        self.screen.blit(txt_eeg, (dash_rect.x + 14, eeg_y))

        eeg_bar_bg = pygame.Rect(dash_rect.x + 14, eeg_y + 26, dash_rect.width - 28, 28)
        pygame.draw.rect(self.screen, (40, 45, 55), eeg_bar_bg, border_radius=6)
        focus_w = int((bio.eeg_focus / 100.0) * eeg_bar_bg.width)

        if bio.eeg_focus >= 70:
            focus_col = (241, 196, 15)
        elif bio.eeg_focus >= 45:
            focus_col = (52, 152, 219)
        else:
            focus_col = (120, 120, 130)

        pygame.draw.rect(self.screen, focus_col, (eeg_bar_bg.x, eeg_bar_bg.y, focus_w, eeg_bar_bg.height), border_radius=6)
        pygame.draw.rect(self.screen, (100, 110, 130), eeg_bar_bg, 1, border_radius=6)

        _, clarity_desc = bio.get_cheat_opacity_and_blur()
        txt_focus_desc = self.font_small.render(f"小抄清晰度：{clarity_desc}", True, (255, 255, 255))
        self.screen.blit(txt_focus_desc, (eeg_bar_bg.x + 10, eeg_bar_bg.y + 5))

        self.btn_focus_down = pygame.Rect(dash_rect.x + 14, eeg_y + 60, (dash_rect.width - 36) // 2, 32)
        self.btn_focus_up = pygame.Rect(dash_rect.x + 22 + (dash_rect.width - 36) // 2, eeg_y + 60, (dash_rect.width - 36) // 2, 32)
        fd_rect, fd_p = self._get_anim_rect_and_active(self.btn_focus_down, "FOCUS_DOWN")
        fu_rect, fu_p = self._get_anim_rect_and_active(self.btn_focus_up, "FOCUS_UP")

        for r_b, is_p, lbl in [
            (fd_rect, fd_p, "[鎖]分心 (外部)" if is_ext else "腦波分心 (S鍵)"),
            (fu_rect, fu_p, "[鎖]專注 (外部)" if is_ext else "腦波專注 (W鍵)"),
        ]:
            pygame.draw.rect(self.screen, btn_ecg_bg, r_b, border_radius=5)
            pygame.draw.rect(self.screen, (255, 220, 80) if is_p else (100, 115, 135), r_b, 2 if is_p else 1, border_radius=5)
            ts = self.font_small.render(lbl, True, btn_ecg_fg)
            self.screen.blit(ts, (r_b.centerx - ts.get_width() // 2, r_b.centery - ts.get_height() // 2))

        # ==================== 4. 底部 3D 教室操作與外部訊號狀態區 ====================
        op_rect = pygame.Rect(dash_rect.x + 12, dash_rect.y + 452, dash_rect.width - 24, 190)
        pygame.draw.rect(self.screen, (28, 34, 44), op_rect, border_radius=6)
        pygame.draw.rect(self.screen, (55, 70, 90), op_rect, 1, border_radius=6)

        if not is_ext:
            self.btn_cycle_port = pygame.Rect(0, 0, 0, 0)
            lines = [
                ("【3D 教室視角 & 手動模式指南】", (100, 240, 150)),
                ("• 滑鼠移動：自由轉動第一人稱視角", (190, 230, 255)),
                ("  - 往上移：抬頭看黑板與奶龍監考官", (210, 220, 230)),
                ("  - 往左右：轉頭看旁邊其他學生作答", (210, 220, 230)),
                ("  - 往下移：低頭看書桌考卷與抽屜小抄", (210, 220, 230)),
                ("• [空白鍵/右鍵/EMG]：伸手拉開抽屜看小抄", (255, 225, 130)),
                ("• [↑ / ↓] 調控 ECG 心率 | [R] 深呼吸", (255, 185, 185)),
                ("• [W / S] 調控 EEG 專注度 | [M] 切換模式", (180, 220, 255)),
            ]
            cy = op_rect.y + 8
            for text_l, col_l in lines:
                s = self.font_small.render(text_l, True, col_l)
                self.screen.blit(s, (op_rect.x + 10, cy))
                cy += 22
        else:
            is_live = bio.is_external_signal_active()
            status_col = (46, 204, 113) if is_live else (241, 196, 15)
            live_str = f"🟢 接收中 ({bio.external_source_name} | 封包:{bio.external_packet_count})" if is_live else "🟡 等待外部輸入 ECG, EEG..."
            self.screen.blit(self.font_small.render("【模式二：外部訊號輸入】", True, (220, 180, 255)), (op_rect.x + 10, op_rect.y + 8))
            self.screen.blit(self.font_small.render(live_str, True, status_col), (op_rect.x + 10, op_rect.y + 30))

            self.btn_cycle_port = pygame.Rect(op_rect.x + 10, op_rect.y + 56, op_rect.width - 20, 28)
            cp_rect, cp_p = self._get_anim_rect_and_active(self.btn_cycle_port, "PORT_CYCLE")
            pygame.draw.rect(self.screen, (60, 82, 112), cp_rect, border_radius=4)
            pygame.draw.rect(self.screen, (255, 220, 80) if cp_p else (160, 190, 230), cp_rect, 1, border_radius=4)
            port_lbl = f"🔌 切換序列埠 (目前: {hw_bridge.port or 'UDP:5005'})" if hw_bridge else "🔌 切換 COM 埠"
            t_cp = self.font_small.render(port_lbl, True, (255, 255, 255))
            self.screen.blit(t_cp, (cp_rect.centerx - t_cp.get_width() // 2, cp_rect.centery - t_cp.get_height() // 2))

            ext_lines = [
                "• 滑鼠移動可轉頭看同學、黑板與桌下抽屜",
                "• [空白鍵/右鍵] 伸手進抽屜打開小抄",
                "• 外部傳入格式：ECG:85,EEG:78",
                "• 可執行 external_signal_sender.py 測試",
            ]
            cy = op_rect.y + 92
            for el in ext_lines:
                self.screen.blit(self.font_small.render(el, True, (205, 215, 230)), (op_rect.x + 10, cy))
                cy += 22

    def _draw_bio_chart(self, chart_rect, records):
        pygame.draw.rect(self.screen, (20, 25, 32), chart_rect, border_radius=6)
        pygame.draw.rect(self.screen, (70, 80, 95), chart_rect, 1, border_radius=6)

        if not records or len(records) < 2:
            no_data = self.font_small.render("尚無足夠生理訊號記錄", True, (150, 150, 150))
            self.screen.blit(no_data, (chart_rect.centerx - no_data.get_width() // 2, chart_rect.centery - no_data.get_height() // 2))
            return

        c_title = self.font_small.render("📊 受試者生理歷程回顧 [紅: ECG心率(BPM) | 金: EEG專注度(%) | 灰區: 伸手開抽屜看小抄]", True, (230, 230, 230))
        self.screen.blit(c_title, (chart_rect.x + 12, chart_rect.y + 6))

        plot_x = chart_rect.x + 15
        plot_w = chart_rect.width - 30
        plot_y = chart_rect.y + 28
        plot_h = chart_rect.height - 35

        pygame.draw.line(self.screen, (40, 50, 60), (plot_x, plot_y + plot_h // 2), (plot_x + plot_w, plot_y + plot_h // 2), 1)

        ecg_pts = []
        eeg_pts = []
        n = len(records)
        step = plot_w / max(1, n - 1)

        for i, rec in enumerate(records):
            px = plot_x + i * step
            if rec.get("emg_active", 0) == 1:
                pygame.draw.line(self.screen, (60, 65, 80), (px, plot_y), (px, plot_y + plot_h), max(1, int(step) + 1))

            bpm = rec.get("ecg_bpm", 75)
            bpm_norm = min(1.0, max(0.0, (bpm - 50.0) / 100.0))
            py_bpm = (plot_y + plot_h) - (bpm_norm * plot_h)
            ecg_pts.append((px, py_bpm))

            focus = rec.get("eeg_focus", 70)
            focus_norm = min(1.0, max(0.0, focus / 100.0))
            py_focus = (plot_y + plot_h) - (focus_norm * plot_h)
            eeg_pts.append((px, py_focus))

        if len(ecg_pts) > 1:
            pygame.draw.lines(self.screen, (255, 80, 80), False, ecg_pts, 2)
        if len(eeg_pts) > 1:
            pygame.draw.lines(self.screen, (241, 196, 15), False, eeg_pts, 2)

    def render_game_over(self, reason, score, records=None):
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 195))
        self.screen.blit(overlay, (0, 0))

        box = pygame.Rect(self.width // 2 - 360, self.height // 2 - 225, 720, 450)
        pygame.draw.rect(self.screen, (245, 245, 245), box, border_radius=12)
        pygame.draw.rect(self.screen, self.COLOR_ALERT, box, 4, border_radius=12)

        t_over = self.font_large.render("【伸手看抽屜小抄被奶龍抓包！】" if reason == "BUSTED" else "【成績不合格！只能停修！】", True, self.COLOR_ALERT)
        self.screen.blit(t_over, (box.centerx - t_over.get_width() // 2, box.y + 22))

        if reason == "BUSTED" and self.img_nailong:
            nl_small = pygame.transform.smoothscale(self.img_nailong, (70, 90))
            self.screen.blit(nl_small, (box.right - 88, box.y + 16))

        if reason == "BUSTED":
            t_sub1 = self.font_bold.render("🟡 奶龍走到你書桌前捧肚狂笑：『手伸進抽屜裡翻什麼？零分！』", True, (50, 50, 50))
            t_sub2 = self.font_main.render("你已被奶龍監考官記下學號，移送學生獎懲委員會辦理！", True, (100, 100, 100))
        else:
            t_sub1 = self.font_bold.render(f"測驗時間結束！你的最終成績為：{score} 分", True, (50, 50, 50))
            t_sub2 = self.font_main.render("奶龍摸摸肚子搖搖頭：未滿 90 分無法拿到 A+，你只能去辦停修了！", True, (100, 100, 100))

        self.screen.blit(t_sub1, (box.centerx - t_sub1.get_width() // 2, box.y + 70))
        self.screen.blit(t_sub2, (box.centerx - t_sub2.get_width() // 2, box.y + 102))

        chart_rect = pygame.Rect(box.x + 35, box.y + 140, box.width - 70, 145)
        self._draw_bio_chart(chart_rect, records)

        csv_hint = self.font_small.render("📁 整場生理數據已自動儲存至 neurocheat_session_data.csv (供生醫報告分析)", True, (100, 110, 130))
        self.screen.blit(csv_hint, (box.centerx - csv_hint.get_width() // 2, box.y + 300))

        self.btn_restart = pygame.Rect(box.centerx - 220, box.y + 345, 220, 52)
        self.btn_back_title = pygame.Rect(box.centerx + 15, box.y + 345, 205, 52)

        pygame.draw.rect(self.screen, self.COLOR_ALERT, self.btn_restart, border_radius=8)
        pygame.draw.rect(self.screen, (255, 255, 255), self.btn_restart, 2, border_radius=8)
        txt_rst = self.font_bold.render("重新挑戰 (空白鍵)", True, (255, 255, 255))
        self.screen.blit(txt_rst, (self.btn_restart.centerx - txt_rst.get_width() // 2, self.btn_restart.centery - txt_rst.get_height() // 2))

        pygame.draw.rect(self.screen, (52, 73, 94), self.btn_back_title, border_radius=8)
        pygame.draw.rect(self.screen, (255, 255, 255), self.btn_back_title, 2, border_radius=8)
        txt_back = self.font_bold.render("回模式選單 (ESC)", True, (255, 255, 255))
        self.screen.blit(txt_back, (self.btn_back_title.centerx - txt_back.get_width() // 2, self.btn_back_title.centery - txt_back.get_height() // 2))

    def render_victory(self, score, records=None):
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 185))
        self.screen.blit(overlay, (0, 0))

        box = pygame.Rect(self.width // 2 - 360, self.height // 2 - 225, 720, 450)
        pygame.draw.rect(self.screen, (245, 255, 245), box, border_radius=12)
        pygame.draw.rect(self.screen, self.COLOR_SUCCESS, box, 4, border_radius=12)

        t_win = self.font_large.render("【恭喜通關！成功奪得 A+！】", True, (39, 174, 96))
        self.screen.blit(t_win, (box.centerx - t_win.get_width() // 2, box.y + 22))

        t_sub1 = self.font_bold.render(f"最終成績：{score} 分 (完美達到 90 分以上！)", True, (40, 40, 40))
        t_sub2 = self.font_main.render("你在 3D 考場中精準掌控抽屜小抄、心率與腦波專注度，完美瞞過奶龍教授！", True, (80, 80, 80))
        self.screen.blit(t_sub1, (box.centerx - t_sub1.get_width() // 2, box.y + 70))
        self.screen.blit(t_sub2, (box.centerx - t_sub2.get_width() // 2, box.y + 102))

        chart_rect = pygame.Rect(box.x + 35, box.y + 140, box.width - 70, 145)
        self._draw_bio_chart(chart_rect, records)

        csv_hint = self.font_small.render("📁 整場生理數據已自動儲存至 neurocheat_session_data.csv (供生醫報告分析)", True, (40, 130, 70))
        self.screen.blit(csv_hint, (box.centerx - csv_hint.get_width() // 2, box.y + 300))

        self.btn_restart = pygame.Rect(box.centerx - 220, box.y + 345, 220, 52)
        self.btn_back_title = pygame.Rect(box.centerx + 15, box.y + 345, 205, 52)

        pygame.draw.rect(self.screen, self.COLOR_SUCCESS, self.btn_restart, border_radius=8)
        pygame.draw.rect(self.screen, (255, 255, 255), self.btn_restart, 2, border_radius=8)
        txt_rst = self.font_bold.render("再玩一次 (空白鍵)", True, (255, 255, 255))
        self.screen.blit(txt_rst, (self.btn_restart.centerx - txt_rst.get_width() // 2, self.btn_restart.centery - txt_rst.get_height() // 2))

        pygame.draw.rect(self.screen, (52, 73, 94), self.btn_back_title, border_radius=8)
        pygame.draw.rect(self.screen, (255, 255, 255), self.btn_back_title, 2, border_radius=8)
        txt_back = self.font_bold.render("回模式選單 (ESC)", True, (255, 255, 255))
        self.screen.blit(txt_back, (self.btn_back_title.centerx - txt_back.get_width() // 2, self.btn_back_title.centery - txt_back.get_height() // 2))

    def render_title_screen(self, mouse_pos, bio=None, hw_bridge=None):
        self.screen.fill((20, 28, 40))

        frame_rect = pygame.Rect(40, 25, self.width - 80, self.height - 50)
        pygame.draw.rect(self.screen, (35, 48, 68), frame_rect, border_radius=12)
        pygame.draw.rect(self.screen, (52, 152, 219), frame_rect, 2, border_radius=12)

        title_main = self.font_large.render("NeuroCheat 3D", True, (255, 255, 255))
        scaled_title = pygame.transform.smoothscale(title_main, (int(title_main.get_width() * 1.45), int(title_main.get_height() * 1.45)))
        t_x = self.width // 2 - scaled_title.get_width() // 2
        t_y = 50
        self.screen.blit(scaled_title, (t_x, t_y))

        if self.img_nailong:
            nl_icon = pygame.transform.smoothscale(self.img_nailong, (52, 66))
            self.screen.blit(nl_icon, (t_x - 68, t_y - 6))
            nl_flip = pygame.transform.flip(nl_icon, True, False)
            self.screen.blit(nl_flip, (t_x + scaled_title.get_width() + 16, t_y - 6))

        subtitle = self.font_bold.render("3D 第一人稱考場生存遊戲 — 滑鼠自由視角 • 書桌考卷 • 伸手拉開抽屜看小抄", True, (130, 200, 255))
        self.screen.blit(subtitle, (self.width // 2 - subtitle.get_width() // 2, 115))

        group_txt = self.font_main.render("生醫工程期末專題 — Group 6  |  B13502162 黃建澄  •  B13901094 王家佑  •  B13901135 張嘉宸", True, (241, 196, 15))
        self.screen.blit(group_txt, (self.width // 2 - group_txt.get_width() // 2, 148))

        card_w = 340
        card_h = 135
        card_y = 185

        c1 = pygame.Rect(self.width // 2 - card_w * 1.5 - 20, card_y, card_w, card_h)
        pygame.draw.rect(self.screen, (28, 38, 54), c1, border_radius=8)
        pygame.draw.rect(self.screen, (231, 76, 60), c1, 2, border_radius=8)
        self.screen.blit(self.font_bold.render("1. 抽屜小抄 & 伸手動作 (EMG)", True, (255, 120, 120)), (c1.x + 15, c1.y + 12))
        self.screen.blit(self.font_small.render("• 小抄藏在書桌下方的立體抽屜裡", True, (210, 210, 210)), (c1.x + 15, c1.y + 46))
        self.screen.blit(self.font_small.render("• 按 [空白鍵/右鍵] 伸手拉開抽屜並展開小抄", True, (210, 210, 210)), (c1.x + 15, c1.y + 72))
        self.screen.blit(self.font_small.render("• 奶龍走下講台巡視時務必把抽屜推回！", True, (255, 180, 180)), (c1.x + 15, c1.y + 98))

        c2 = pygame.Rect(self.width // 2 - card_w // 2, card_y, card_w, card_h)
        pygame.draw.rect(self.screen, (28, 38, 54), c2, border_radius=8)
        pygame.draw.rect(self.screen, (241, 196, 15), c2, 2, border_radius=8)
        self.screen.blit(self.font_bold.render("2. 3D 滑鼠視角 & 腦波專注 (EEG)", True, (255, 220, 100)), (c2.x + 15, c2.y + 12))
        self.screen.blit(self.font_small.render("• 滑鼠控制視角：抬頭看黑板、左右看同學", True, (210, 210, 210)), (c2.x + 15, c2.y + 46))
        self.screen.blit(self.font_small.render("• 低頭看書桌上的考卷與抽屜內的小抄", True, (210, 210, 210)), (c2.x + 15, c2.y + 72))
        self.screen.blit(self.font_small.render("• EEG 專注度決定抽屜內小抄字體清晰度！", True, (210, 210, 210)), (c2.x + 15, c2.y + 98))

        c3 = pygame.Rect(self.width // 2 + card_w * 0.5 + 20, card_y, card_w, card_h)
        pygame.draw.rect(self.screen, (28, 38, 54), c3, border_radius=8)
        pygame.draw.rect(self.screen, (46, 204, 113), c3, 2, border_radius=8)
        self.screen.blit(self.font_bold.render("3. 心電波形與奶龍巡邏 (ECG)", True, (120, 255, 160)), (c3.x + 15, c3.y + 12))
        self.screen.blit(self.font_small.render("• 即時繪製 P-Q-R-S-T 心電圖示波器", True, (210, 210, 210)), (c3.x + 15, c3.y + 46))
        self.screen.blit(self.font_small.render("• 心率飆高會觸發蜂鳴器並吸引奶龍走近書桌", True, (210, 210, 210)), (c3.x + 15, c3.y + 72))
        self.screen.blit(self.font_small.render("• 維持心率平穩可大幅降低被抓風險", True, (210, 210, 210)), (c3.x + 15, c3.y + 98))

        req_txt = self.font_bold.render("★ 過關條件：120 秒內於書桌考卷取得 90 分以上 (A+) 即可過關，寫完可提早交卷！", True, (255, 185, 60))
        self.screen.blit(req_txt, (self.width // 2 - req_txt.get_width() // 2, 335))

        mode_y = 378
        mode_w = 500
        mode_h = 185

        self.btn_mode_manual = pygame.Rect(self.width // 2 - mode_w - 20, mode_y, mode_w, mode_h)
        m1_hover = self.btn_mode_manual.collidepoint(mouse_pos)
        m1_bg = (36, 95, 68) if m1_hover else (28, 72, 52)
        pygame.draw.rect(self.screen, m1_bg, self.btn_mode_manual, border_radius=10)
        pygame.draw.rect(self.screen, (46, 204, 113), self.btn_mode_manual, 3 if m1_hover else 2, border_radius=10)

        self.screen.blit(self.font_large.render("🟢 模式一：手動調控模式", True, (255, 255, 255)), (self.btn_mode_manual.x + 22, self.btn_mode_manual.y + 14))
        self.screen.blit(self.font_bold.render("【自己調控 ECG、EEG、EMG】(按 1 或空白鍵開始)", True, (140, 255, 180)), (self.btn_mode_manual.x + 22, self.btn_mode_manual.y + 56))
        self.screen.blit(self.font_small.render("• 玩家可自行用方向鍵 [↑/↓] 與螢幕按鈕自由控制 ECG 心率", True, (225, 235, 230)), (self.btn_mode_manual.x + 22, self.btn_mode_manual.y + 92))
        self.screen.blit(self.font_small.render("• 可自行用 [W/S 鍵] 調整 EEG 專注度，[空白鍵] 伸手開抽屜小抄", True, (225, 235, 230)), (self.btn_mode_manual.x + 22, self.btn_mode_manual.y + 118))
        self.screen.blit(self.font_small.render("👉 適合單機遊玩、體驗 3D 考場視角與課堂 Demo 展示", True, (255, 230, 120)), (self.btn_mode_manual.x + 22, self.btn_mode_manual.y + 146))

        self.btn_mode_external = pygame.Rect(self.width // 2 + 20, mode_y, mode_w, mode_h)
        m2_hover = self.btn_mode_external.collidepoint(mouse_pos)
        m2_bg = (82, 48, 108) if m2_hover else (62, 36, 84)
        pygame.draw.rect(self.screen, m2_bg, self.btn_mode_external, border_radius=10)
        pygame.draw.rect(self.screen, (187, 143, 206), self.btn_mode_external, 3 if m2_hover else 2, border_radius=10)

        self.screen.blit(self.font_large.render("🟣 模式二：外部訊號模式", True, (255, 255, 255)), (self.btn_mode_external.x + 22, self.btn_mode_external.y + 14))
        self.screen.blit(self.font_bold.render("【必須從外部輸入 ECG、EEG】(按 2 或點擊開始)", True, (235, 190, 255)), (self.btn_mode_external.x + 22, self.btn_mode_external.y + 56))
        self.screen.blit(self.font_small.render("• 鎖定鍵盤/畫面之 ECG 與 EEG 手動微調，必須由外部訊號驅動！", True, (235, 225, 240)), (self.btn_mode_external.x + 22, self.btn_mode_external.y + 92))
        self.screen.blit(self.font_small.render("• 支援 Arduino/ESP32 Serial COM 埠、UDP:5005 與 JSON 即時串流", True, (235, 225, 240)), (self.btn_mode_external.x + 22, self.btn_mode_external.y + 118))
        self.screen.blit(self.font_small.render("• 抽屜小抄開闔 (EMG) 維持以按鈕 (空白鍵/右鍵/畫面按鈕) 觸發", True, (255, 230, 120)), (self.btn_mode_external.x + 22, self.btn_mode_external.y + 146))

        hw_y = 582
        self.btn_cycle_port = pygame.Rect(self.width // 2 - 260, hw_y, 520, 42)
        cp_hover = self.btn_cycle_port.collidepoint(mouse_pos)
        pygame.draw.rect(self.screen, (45, 62, 85) if cp_hover else (32, 44, 62), self.btn_cycle_port, border_radius=8)
        pygame.draw.rect(self.screen, (100, 180, 240), self.btn_cycle_port, 1, border_radius=8)

        port_info = hw_bridge.status_text if hw_bridge else "UDP:5005 就緒"
        t_port = self.font_main.render(f"🔌 外部訊號通道：{port_info} (點此切換 COM 埠)", True, (180, 230, 255))
        self.screen.blit(t_port, (self.btn_cycle_port.centerx - t_port.get_width() // 2, self.btn_cycle_port.centery - t_port.get_height() // 2))

        footer_hint = self.font_small.render("提示：進入 3D 教室後移動滑鼠即可控制視角，按 [M 鍵] 隨時切換模式，按 [ESC] 返回此選單", True, (170, 185, 205))
        self.screen.blit(footer_hint, (self.width // 2 - footer_hint.get_width() // 2, 638))
