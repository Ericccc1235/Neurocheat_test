"""
NeuroCheat UI 渲染模組
負責繪製教室考場視角、課桌考卷、作答選項、手中拿著的小抄透明度濾鏡、
以及支援「雙模式 (手動調控模式 / 外部訊號輸入模式)」的生醫儀表板 (ECG 示波器、EEG 專注條、EMG 按鈕)
"""

import pygame
import math
import os

class UIRenderer:
    def __init__(self, screen, width, height):
        self.screen = screen
        self.width = width
        self.height = height

        # 載入經典迷因「奶龍」透明貼圖
        self.img_nailong = None
        try:
            if os.path.exists("nailong.png"):
                self.img_nailong = pygame.image.load("nailong.png").convert_alpha()
        except Exception as e:
            print("[UIRenderer] 載入 nailong.png 失敗:", e)

        # 載入 Windows 支援中文的中文字體
        font_path = pygame.font.match_font("microsoftjhenghei") or \
                    pygame.font.match_font("simsun") or \
                    pygame.font.match_font("arial")

        try:
            self.font_title = pygame.font.Font(font_path, 26)
            self.font_main = pygame.font.Font(font_path, 20)
            self.font_large = pygame.font.Font(font_path, 32)
            self.font_small = pygame.font.Font(font_path, 15)
            self.font_bold = pygame.font.Font(font_path, 22)
            self.font_bold.set_bold(True)
            self.font_large.set_bold(True)
        except Exception:
            self.font_title = pygame.font.SysFont("sans-serif", 24)
            self.font_main = pygame.font.SysFont("sans-serif", 18)
            self.font_large = pygame.font.SysFont("sans-serif", 30)
            self.font_small = pygame.font.SysFont("sans-serif", 14)
            self.font_bold = pygame.font.SysFont("sans-serif", 20)

        # 顏色常量
        self.COLOR_BG = (235, 238, 242)
        self.COLOR_BOARD = (34, 76, 56)
        self.COLOR_PAPER = (252, 250, 242)
        self.COLOR_CHEAT = (255, 249, 196)
        self.COLOR_TEXT = (30, 30, 30)
        self.COLOR_ACCENT = (41, 128, 185)
        self.COLOR_ALERT = (231, 76, 60)
        self.COLOR_WARN = (230, 126, 34)
        self.COLOR_SUCCESS = (46, 204, 113)

        # 互動按鈕 Rect 記錄 (供點擊偵測)
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

        # 首頁與遊戲內雙模式切換按鈕
        self.btn_mode_manual = pygame.Rect(0, 0, 0, 0)
        self.btn_mode_external = pygame.Rect(0, 0, 0, 0)
        self.btn_switch_mode = pygame.Rect(0, 0, 0, 0)
        self.btn_cycle_port = pygame.Rect(0, 0, 0, 0)

        # 點擊即時反饋系統 (Toast Feedback & Button Press Animation)
        self.feedback_message = ""
        self.feedback_timer = 0.0
        self.feedback_color = (255, 255, 255)
        self.active_btn_name = None
        self.btn_press_timer = 0.0

    def trigger_feedback(self, text, color=(46, 204, 113), btn_name=None):
        """觸發畫面按鈕點擊反饋文字與按鈕發光下沉效果"""
        self.feedback_message = text
        self.feedback_timer = 1.6  # 顯示 1.6 秒
        self.feedback_color = color
        self.active_btn_name = btn_name
        self.btn_press_timer = 0.22  # 按鈕下壓發光 0.22 秒

    def update_feedback(self, dt):
        """每幀更新反饋計時器"""
        if self.feedback_timer > 0:
            self.feedback_timer = max(0.0, self.feedback_timer - dt)
        if self.btn_press_timer > 0:
            self.btn_press_timer = max(0.0, self.btn_press_timer - dt)
            if self.btn_press_timer <= 0:
                self.active_btn_name = None

    def _get_anim_rect_and_active(self, rect, btn_name):
        """【Bug 修正】實際套用按鈕被按下時的下沉位移與高亮發光狀態"""
        is_pressed = (btn_name is not None and self.active_btn_name == btn_name and self.btn_press_timer > 0)
        draw_rect = rect.move(0, 2) if is_pressed else rect
        return draw_rect, is_pressed

    def render_feedback_toast(self):
        """在畫面上方渲染極為醒目的動態操作反饋橫幅"""
        if self.feedback_timer <= 0 or not self.feedback_message:
            return

        alpha = min(255, int(self.feedback_timer * 255 / 0.5))
        toast_surf = self.font_bold.render(self.feedback_message, True, (255, 255, 255))
        pad_x = 24
        pad_y = 10
        box_w = toast_surf.get_width() + pad_x * 2
        box_h = toast_surf.get_height() + pad_y * 2

        bg_surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pygame.draw.rect(bg_surf, (25, 35, 48, min(240, alpha)), (0, 0, box_w, box_h), border_radius=8)
        pygame.draw.rect(bg_surf, (*self.feedback_color, alpha), (0, 0, box_w, box_h), 2, border_radius=8)

        toast_surf.set_alpha(alpha)
        bg_surf.blit(toast_surf, (pad_x, pad_y))

        center_x = self.width // 2
        self.screen.blit(bg_surf, (center_x - box_w // 2, 205))

    def render_classroom_scene(self, teacher, bio):
        """繪製上半部的考場場景 (黑板、奶龍老師動畫、蜂鳴器)"""
        top_h = 240
        pygame.draw.rect(self.screen, (218, 225, 231), (0, 0, self.width, top_h))
        pygame.draw.rect(self.screen, (178, 150, 125), (0, top_h - 45, self.width, 45))

        # 黑板
        board_rect = pygame.Rect(70, 15, self.width - 140, 160)
        pygame.draw.rect(self.screen, (100, 60, 30), board_rect, border_radius=6)
        inner_board = board_rect.inflate(-10, -10)
        pygame.draw.rect(self.screen, self.COLOR_BOARD, inner_board, border_radius=4)

        txt_board_1 = self.font_small.render("【生醫工程期末考】禁止作弊！違者扣考當掉停修！ (按 ESC 可返回模式選單)", True, (240, 240, 240))
        txt_board_2 = self.font_small.render("成績 >= 90 分過關 (A+) | 滿分 100 分 | 心率過高者加強巡邏！", True, (200, 230, 200))
        self.screen.blit(txt_board_1, (inner_board.x + 25, inner_board.y + 12))
        self.screen.blit(txt_board_2, (inner_board.x + 25, inner_board.y + 35))

        # 蜂鳴器預警警示燈
        buzzer_box = pygame.Rect(board_rect.right - 140, board_rect.y + 12, 120, 42)
        if teacher.buzzer_active:
            blink = (pygame.time.get_ticks() // 150) % 2 == 0
            lamp_color = (255, 50, 50) if blink else (255, 200, 0)
            pygame.draw.rect(self.screen, lamp_color, buzzer_box, border_radius=6)
            pygame.draw.rect(self.screen, (255, 255, 255), buzzer_box, 2, border_radius=6)
            txt_buzz = self.font_bold.render("逼逼!警報", True, (0, 0, 0))
            self.screen.blit(txt_buzz, (buzzer_box.x + 12, buzzer_box.y + 8))
        else:
            pygame.draw.rect(self.screen, (50, 60, 65), buzzer_box, border_radius=6)
            txt_buzz = self.font_small.render("蜂鳴器靜音", True, (160, 170, 175))
            self.screen.blit(txt_buzz, (buzzer_box.x + 24, buzzer_box.y + 12))

        # 左右鄰座同學
        c_left_x = 180
        c_left_y = top_h - 48
        pygame.draw.rect(self.screen, (150, 120, 95), (c_left_x - 30, c_left_y + 8, 60, 24))
        pygame.draw.rect(self.screen, (52, 100, 75), (c_left_x - 18, c_left_y - 28, 36, 40), border_radius=4)
        pygame.draw.circle(self.screen, (30, 25, 20), (c_left_x, c_left_y - 36), 15)
        pen_tick = math.sin(pygame.time.get_ticks() * 0.015) * 4
        pygame.draw.circle(self.screen, (240, 195, 165), (c_left_x + 12 + int(pen_tick), c_left_y - 5), 5)

        c_right_x = self.width - 180
        c_right_y = top_h - 48
        pygame.draw.rect(self.screen, (150, 120, 95), (c_right_x - 30, c_right_y + 8, 60, 24))
        pygame.draw.rect(self.screen, (70, 70, 90), (c_right_x - 18, c_right_y - 28, 36, 40), border_radius=4)
        pygame.draw.circle(self.screen, (40, 30, 25), (c_right_x, c_right_y - 36), 15)
        scratch_tick = math.sin(pygame.time.get_ticks() * 0.005) * 6
        pygame.draw.circle(self.screen, (240, 195, 165), (c_right_x - 14, c_right_y - 38 + int(scratch_tick)), 5)

        # 【奶龍監考官 (Prof. Nailong)】形象與動畫
        center_x = self.width // 2
        scale = 1.0 + teacher.patrol_progress * 0.95
        waddle_shake = 0
        if teacher.state == "PATROLLING":
            waddle_shake = int(math.sin(pygame.time.get_ticks() * 0.012) * 8 * scale)

        base_y = top_h - 45 + int(teacher.patrol_progress * 48)
        COLOR_NAILONG_YELLOW = (248, 202, 58)
        COLOR_NAILONG_BELLY = (245, 230, 205)
        COLOR_NAILONG_HAND = (85, 75, 65)

        if not teacher.facing_player:
            dragon_w = int(72 * scale)
            dragon_h = int(82 * scale)
            dragon_rect = pygame.Rect(center_x - dragon_w // 2, base_y - dragon_h, dragon_w, dragon_h)

            leg_w = int(20 * scale)
            leg_h = int(24 * scale)
            pygame.draw.ellipse(self.screen, (230, 185, 45), (dragon_rect.x + int(4*scale), dragon_rect.bottom - leg_h + 4, leg_w, leg_h))
            pygame.draw.ellipse(self.screen, (230, 185, 45), (dragon_rect.right - int(24*scale), dragon_rect.bottom - leg_h + 4, leg_w, leg_h))

            pygame.draw.ellipse(self.screen, COLOR_NAILONG_YELLOW, dragon_rect)
            pygame.draw.ellipse(self.screen, (255, 218, 90), (dragon_rect.centerx - int(20*scale), dragon_rect.y + int(6*scale), int(40*scale), int(35*scale)))

            hand_anim = math.sin(pygame.time.get_ticks() * 0.01) * 6
            hand_x = dragon_rect.right + int(4 * scale)
            hand_y = dragon_rect.y + int(24 * scale + hand_anim)
            pygame.draw.circle(self.screen, COLOR_NAILONG_HAND, (hand_x, hand_y), int(7 * scale))
            pygame.draw.rect(self.screen, (255, 255, 255), (hand_x + 2, hand_y - 8, 4, 10))

            if teacher.buzzer_active:
                belly_shake = int(math.sin(pygame.time.get_ticks() * 0.035) * 7 * scale)
                pygame.draw.ellipse(self.screen, (255, 225, 100), (dragon_rect.x + belly_shake, dragon_rect.y + int(25*scale), dragon_w, int(45*scale)), 2)
        else:
            if self.img_nailong:
                target_h = int(115 * scale)
                aspect = self.img_nailong.get_width() / self.img_nailong.get_height()
                target_w = int(target_h * aspect)
                scaled_nl = pygame.transform.smoothscale(self.img_nailong, (target_w, target_h))
                nl_x = center_x - target_w // 2 + waddle_shake
                nl_y = base_y - target_h + 8
                self.screen.blit(scaled_nl, (nl_x, nl_y))
            else:
                d_w = int(78 * scale)
                d_h = int(95 * scale)
                d_rect = pygame.Rect(center_x - d_w // 2 + waddle_shake, base_y - d_h, d_w, d_h)
                pygame.draw.ellipse(self.screen, COLOR_NAILONG_YELLOW, d_rect)
                pygame.draw.ellipse(self.screen, COLOR_NAILONG_BELLY, (d_rect.centerx - int(24*scale), d_rect.y + int(32*scale), int(48*scale), int(50*scale)))
                pygame.draw.ellipse(self.screen, COLOR_NAILONG_HAND, (d_rect.centerx - int(22*scale), d_rect.y + int(52*scale), int(18*scale), int(12*scale)))
                pygame.draw.ellipse(self.screen, COLOR_NAILONG_HAND, (d_rect.centerx + int(4*scale), d_rect.y + int(52*scale), int(18*scale), int(12*scale)))

        desk_w = int(95 * scale)
        desk_h = int(20 * scale)
        desk_rect = pygame.Rect(center_x - desk_w // 2, base_y + 2, desk_w, desk_h)
        pygame.draw.rect(self.screen, (120, 80, 45), desk_rect, border_radius=4)
        pygame.draw.rect(self.screen, (240, 200, 80), desk_rect, 1, border_radius=4)
        t_prof = self.font_small.render("監考官: 奶龍教授🟡", True, (255, 240, 180))
        self.screen.blit(t_prof, (desk_rect.centerx - t_prof.get_width() // 2, desk_rect.centery - t_prof.get_height() // 2))

        desc, color = teacher.get_status_description()
        txt_status = self.font_bold.render(desc, True, color)
        status_bg = pygame.Rect(board_rect.x, top_h - 38, board_rect.width, 32)
        pygame.draw.rect(self.screen, (245, 245, 248), status_bg, border_radius=4)
        pygame.draw.rect(self.screen, color, status_bg, 2, border_radius=4)
        self.screen.blit(txt_status, (status_bg.x + 15, status_bg.y + 4))

    def render_header(self, exam, bio=None):
        """渲染頂部資訊 HUD (考試名稱、倒數計時、目前成績)"""
        hud_h = 42
        hud_rect = pygame.Rect(0, 0, self.width, hud_h)
        pygame.draw.rect(self.screen, (34, 49, 63), hud_rect)

        title_surf = self.font_bold.render("NeuroCheat：生醫工程期末考", True, (255, 255, 255))
        self.screen.blit(title_surf, (15, 8))

        # 顯示當前模式標籤
        if bio is not None:
            if bio.is_external_mode():
                mode_tag = "【模式二：外部訊號輸入】"
                tag_col = (155, 89, 182)
            else:
                mode_tag = "【模式一：手動調控測試】"
                tag_col = (39, 174, 96)
            tag_rect = pygame.Rect(305, 7, 195, 28)
            pygame.draw.rect(self.screen, tag_col, tag_rect, border_radius=5)
            t_tag = self.font_small.render(mode_tag, True, (255, 255, 255))
            self.screen.blit(t_tag, (tag_rect.centerx - t_tag.get_width() // 2, tag_rect.y + 5))

        t_color = (255, 100, 100) if exam.time_left < 30 else (255, 255, 255)
        mins = int(exam.time_left) // 60
        secs = int(exam.time_left) % 60
        time_str = f"剩餘時間：{mins:02d}:{secs:02d}"
        time_surf = self.font_bold.render(time_str, True, t_color)
        self.screen.blit(time_surf, (self.width // 2 - 40, 8))

        score = exam.calculate_score()
        score_color = self.COLOR_SUCCESS if score >= 90 else (255, 215, 0)
        score_str = f"已答: {exam.answered_count()}/10 | 預估分: {score} 分 (過關: 90分)"
        score_surf = self.font_main.render(score_str, True, score_color)
        self.screen.blit(score_surf, (self.width - score_surf.get_width() - 20, 9))

    def render_exam_sheet(self, exam, mouse_pos):
        """繪製考卷題目與選項"""
        sheet_rect = pygame.Rect(35, 255, 680, 425)
        pygame.draw.rect(self.screen, (190, 195, 205), sheet_rect.move(4, 4), border_radius=8)
        pygame.draw.rect(self.screen, self.COLOR_PAPER, sheet_rect, border_radius=8)
        pygame.draw.rect(self.screen, (215, 215, 215), sheet_rect, 2, border_radius=8)

        header_text = self.font_small.render("國立臺灣大學 生物醫學工程學系 期末定期測驗試卷 (請用滑鼠或鍵盤 1~4 作答)", True, (120, 120, 120))
        self.screen.blit(header_text, (sheet_rect.x + 25, sheet_rect.y + 12))
        pygame.draw.line(self.screen, (220, 220, 220), (sheet_rect.x + 20, sheet_rect.y + 32), (sheet_rect.right - 20, sheet_rect.y + 32), 1)

        q = exam.current_question()
        q_num_txt = self.font_bold.render(f"【第 {exam.current_idx + 1} / {len(exam.questions)} 題】", True, self.COLOR_ACCENT)
        self.screen.blit(q_num_txt, (sheet_rect.x + 25, sheet_rect.y + 42))

        prompt_lines = self._wrap_text(q.prompt, self.font_bold, 630)
        curr_y = sheet_rect.y + 70
        for line in prompt_lines:
            line_surf = self.font_bold.render(line, True, self.COLOR_TEXT)
            self.screen.blit(line_surf, (sheet_rect.x + 25, curr_y))
            curr_y += 28

        self.btn_options = []
        opt_start_y = sheet_rect.y + 140
        btn_h = 44
        btn_w = sheet_rect.width - 50

        for i, opt in enumerate(q.options):
            raw_rect = pygame.Rect(sheet_rect.x + 25, opt_start_y + i * (btn_h + 10), btn_w, btn_h)
            self.btn_options.append(raw_rect)
            b_rect, is_pressed = self._get_anim_rect_and_active(raw_rect, f"OPT_{i}")

            is_selected = (q.user_answer == i)
            is_hover = raw_rect.collidepoint(mouse_pos)

            if is_pressed:
                bg_color = (205, 230, 255)
                border_color = (255, 200, 0)
                border_width = 3
            elif is_selected:
                bg_color = (225, 240, 255)
                border_color = self.COLOR_ACCENT
                border_width = 3
            elif is_hover:
                bg_color = (240, 245, 250)
                border_color = (150, 180, 220)
                border_width = 2
            else:
                bg_color = (255, 255, 255)
                border_color = (210, 210, 210)
                border_width = 1

            pygame.draw.rect(self.screen, bg_color, b_rect, border_radius=6)
            pygame.draw.rect(self.screen, border_color, b_rect, border_width, border_radius=6)

            opt_letter = ["A", "B", "C", "D"][i]
            circle_color = self.COLOR_ACCENT if is_selected else (140, 140, 140)
            pygame.draw.circle(self.screen, circle_color, (b_rect.x + 24, b_rect.y + btn_h // 2), 14, 0 if is_selected else 2)
            letter_color = (255, 255, 255) if is_selected else (80, 80, 80)
            letter_surf = self.font_small.render(opt_letter, True, letter_color)
            self.screen.blit(letter_surf, (b_rect.x + 20, b_rect.y + btn_h // 2 - 9))

            opt_text = opt[3:]
            opt_surf = self.font_main.render(opt_text, True, self.COLOR_TEXT)
            self.screen.blit(opt_surf, (b_rect.x + 48, b_rect.y + 11))

        nav_y = sheet_rect.bottom - 48
        self.btn_prev = pygame.Rect(sheet_rect.x + 25, nav_y, 105, 36)
        self.btn_submit = pygame.Rect(sheet_rect.centerx - 60, nav_y, 120, 36)
        self.btn_next = pygame.Rect(sheet_rect.right - 130, nav_y, 105, 36)

        for raw_btn, label, enabled, b_name in [
            (self.btn_prev, "< 上一題", exam.current_idx > 0, "PREV"),
            (self.btn_next, "下一題 >", exam.current_idx < len(exam.questions) - 1, "NEXT")
        ]:
            btn, is_p = self._get_anim_rect_and_active(raw_btn, b_name)
            color = (230, 235, 245) if enabled else (235, 235, 235)
            text_col = self.COLOR_TEXT if enabled else (170, 170, 170)
            pygame.draw.rect(self.screen, color, btn, border_radius=5)
            pygame.draw.rect(self.screen, (255, 200, 0) if is_p else (190, 190, 200), btn, 2 if is_p else 1, border_radius=5)
            lbl_surf = self.font_main.render(label, True, text_col)
            self.screen.blit(lbl_surf, (btn.centerx - lbl_surf.get_width() // 2, btn.centery - lbl_surf.get_height() // 2))

        sub_rect, is_sub_p = self._get_anim_rect_and_active(self.btn_submit, "SUBMIT")
        pygame.draw.rect(self.screen, (46, 204, 113), sub_rect, border_radius=5)
        pygame.draw.rect(self.screen, (255, 230, 80) if is_sub_p else (39, 174, 96), sub_rect, 2 if is_sub_p else 1, border_radius=5)
        lbl_sub = self.font_bold.render("提早交卷", True, (255, 255, 255))
        self.screen.blit(lbl_sub, (sub_rect.centerx - lbl_sub.get_width() // 2, sub_rect.centery - lbl_sub.get_height() // 2))

    def render_cheat_sheet(self, exam, bio):
        """繪製拿在手上的小抄 (Handheld Cheat Sheet) - 位於遊戲畫面正中央"""
        center_x = self.width // 2
        lift = bio.emg_signal_level

        if lift <= 0.01:
            hint_w = 430
            hint_rect = pygame.Rect(center_x - hint_w // 2, self.height - 34, hint_w, 30)
            pygame.draw.rect(self.screen, (255, 235, 140), hint_rect, border_radius=6)
            pygame.draw.rect(self.screen, (200, 150, 40), hint_rect, 2, border_radius=6)
            txt_hint = self.font_small.render("🖐️ 小抄藏在桌下 [按空白鍵 / C鍵 / 滑鼠右鍵 / 點EMG按鈕 舉起]", True, (70, 50, 10))
            self.screen.blit(txt_hint, (hint_rect.centerx - txt_hint.get_width() // 2, hint_rect.y + 6))
            return

        cheat_w = 540
        cheat_h = 205
        curr_y = int(self.height - (lift * 235))
        cheat_x = center_x - cheat_w // 2

        skin_color = (242, 198, 168)
        skin_shadow = (215, 165, 135)
        sleeve_color = (45, 55, 75)

        left_wrist_x = cheat_x + 30
        left_wrist_y = curr_y + cheat_h - 15
        pygame.draw.polygon(self.screen, sleeve_color, [
            (left_wrist_x - 45, self.height),
            (left_wrist_x + 35, self.height),
            (left_wrist_x + 25, left_wrist_y + 35),
            (left_wrist_x - 35, left_wrist_y + 35)
        ])
        pygame.draw.ellipse(self.screen, skin_color, (left_wrist_x - 30, left_wrist_y + 5, 60, 40))
        pygame.draw.ellipse(self.screen, skin_shadow, (left_wrist_x - 20, left_wrist_y - 8, 48, 24))

        right_wrist_x = cheat_x + cheat_w - 30
        right_wrist_y = curr_y + cheat_h - 15
        pygame.draw.polygon(self.screen, sleeve_color, [
            (right_wrist_x - 35, self.height),
            (right_wrist_x + 45, self.height),
            (right_wrist_x + 35, right_wrist_y + 35),
            (right_wrist_x - 25, right_wrist_y + 35)
        ])
        pygame.draw.ellipse(self.screen, skin_color, (right_wrist_x - 30, right_wrist_y + 5, 60, 40))
        pygame.draw.ellipse(self.screen, skin_shadow, (right_wrist_x - 28, right_wrist_y - 8, 48, 24))

        cheat_surf = pygame.Surface((cheat_w, cheat_h), pygame.SRCALPHA)
        paper_alpha = int(min(255, lift * 255))
        pygame.draw.rect(cheat_surf, (254, 250, 195, paper_alpha), (0, 0, cheat_w, cheat_h), border_radius=8)
        pygame.draw.rect(cheat_surf, (205, 175, 75, paper_alpha), (0, 0, cheat_w, cheat_h), 2, border_radius=8)

        line_alpha = int(paper_alpha * 0.25)
        for ly in range(45, cheat_h - 20, 26):
            pygame.draw.line(cheat_surf, (150, 180, 220, line_alpha), (20, ly), (cheat_w - 20, ly), 1)

        text_alpha, clarity = bio.get_cheat_opacity_and_blur()

        txt_title = self.font_small.render(f"📑【手中密藏小抄】EEG 專注度: {bio.eeg_focus:.0f}% ({clarity})", True, (160, 85, 10))
        txt_title.set_alpha(text_alpha)
        cheat_surf.blit(txt_title, (20, 10))

        q = exam.current_question()
        hint_lines = self._wrap_text(q.cheat_hint, self.font_bold, cheat_w - 40)

        curr_text_y = 44
        for line in hint_lines:
            line_surf = self.font_bold.render(line, True, (200, 25, 25))
            line_surf.set_alpha(text_alpha)
            cheat_surf.blit(line_surf, (20, curr_text_y))
            curr_text_y += 30

        if bio.eeg_focus <= 35:
            warn_hint = "⚠️ 腦波不專注！文字已幾近完全透明隱形！"
            warn_msg = self.font_small.render(warn_hint, True, (220, 40, 40))
            warn_msg.set_alpha(max(80, int(lift * 230)))
            cheat_surf.blit(warn_msg, (20, cheat_h - 32))

        self.screen.blit(cheat_surf, (cheat_x, curr_y))

        pygame.draw.ellipse(self.screen, skin_color, (left_wrist_x - 12, left_wrist_y - 22, 28, 38))
        pygame.draw.ellipse(self.screen, skin_shadow, (left_wrist_x - 10, left_wrist_y - 12, 16, 20), 1)
        pygame.draw.ellipse(self.screen, skin_color, (right_wrist_x - 16, right_wrist_y - 22, 28, 38))
        pygame.draw.ellipse(self.screen, skin_shadow, (right_wrist_x - 6, right_wrist_y - 12, 16, 20), 1)

    def render_bio_dashboard(self, bio, mouse_pos, hw_bridge=None):
        """
        繪製右側的生醫訊號監測儀表板 (Bio-Dashboard)
        支援「手動調控模式」與「外部訊號輸入模式」即時切換與狀態顯示
        """
        dash_rect = pygame.Rect(730, 255, 520, 425)
        pygame.draw.rect(self.screen, (25, 30, 36), dash_rect, border_radius=8)
        pygame.draw.rect(self.screen, (50, 60, 75), dash_rect, 2, border_radius=8)

        is_ext = bio.is_external_mode()

        # 儀表板抬頭 + 右上角【模式切換按鈕】
        dash_title = self.font_bold.render("生醫生理訊號監控儀", True, (100, 210, 255))
        self.screen.blit(dash_title, (dash_rect.x + 18, dash_rect.y + 10))

        self.btn_switch_mode = pygame.Rect(dash_rect.right - 255, dash_rect.y + 8, 240, 28)
        sw_rect, sw_pressed = self._get_anim_rect_and_active(self.btn_switch_mode, "MODE_SWITCH")
        sw_col = (142, 68, 173) if is_ext else (39, 174, 96)
        pygame.draw.rect(self.screen, sw_col, sw_rect, border_radius=5)
        pygame.draw.rect(self.screen, (255, 230, 80) if sw_pressed else (220, 220, 220), sw_rect, 2 if sw_pressed else 1, border_radius=5)
        sw_txt_str = "🟣 外部訊號模式 (點此/M切換)" if is_ext else "🟢 手動調控模式 (點此/M切換)"
        sw_txt = self.font_small.render(sw_txt_str, True, (255, 255, 255))
        self.screen.blit(sw_txt, (sw_rect.centerx - sw_txt.get_width() // 2, sw_rect.centery - sw_txt.get_height() // 2))

        # ==================== 1. EMG 手部用力 (以按鈕代替，兩模式皆可按鈕控制) ====================
        emg_y = dash_rect.y + 44
        txt_emg_title = self.font_main.render("1. EMG 肌電訊號 [握拳按鈕 -> 拿取/收起小抄]", True, (255, 255, 255))
        self.screen.blit(txt_emg_title, (dash_rect.x + 18, emg_y))

        self.btn_emg = pygame.Rect(dash_rect.x + 20, emg_y + 25, 260, 42)
        emg_draw_rect, emg_pressed = self._get_anim_rect_and_active(self.btn_emg, "EMG")
        btn_col = (231, 76, 60) if bio.emg_active else (52, 152, 219)
        pygame.draw.rect(self.screen, btn_col, emg_draw_rect, border_radius=6)
        pygame.draw.rect(self.screen, (255, 230, 80) if emg_pressed else (255, 255, 255), emg_draw_rect, 3 if emg_pressed else 2, border_radius=6)

        btn_label = "【小抄拿在眼前】按空白鍵/點此收起" if bio.emg_active else "【小抄藏在桌下】按空白鍵/點此舉起"
        txt_btn = self.font_main.render(btn_label, True, (255, 255, 255))
        self.screen.blit(txt_btn, (emg_draw_rect.centerx - txt_btn.get_width() // 2, emg_draw_rect.centery - txt_btn.get_height() // 2))

        bar_bg = pygame.Rect(dash_rect.x + 295, emg_y + 31, 195, 28)
        pygame.draw.rect(self.screen, (40, 45, 55), bar_bg, border_radius=4)
        active_w = int(bio.emg_signal_level * 195)
        if active_w > 0:
            bar_color = (255, 80, 80) if bio.emg_signal_level > 0.6 else (100, 220, 100)
            pygame.draw.rect(self.screen, bar_color, (bar_bg.x, bar_bg.y, active_w, bar_bg.height), border_radius=4)
        txt_level = self.font_small.render(f"肌電電位: {bio.emg_signal_level*100:.0f}%", True, (220, 220, 220))
        self.screen.blit(txt_level, (bar_bg.x + 10, bar_bg.y + 5))

        # ==================== 2. ECG 心率與示波器 ====================
        ecg_y = dash_rect.y + 122
        ecg_status_color = self.COLOR_ALERT if bio.ecg_bpm > 95 else (100, 255, 150)
        ecg_hint = "[外部訊號輸入中🔒]" if is_ext else "(按鍵盤 ↑/↓ 或按鈕微調)"
        txt_ecg = self.font_main.render(f"2. ECG 心電 [心率：{bio.ecg_bpm:.0f} BPM] {ecg_hint}", True, ecg_status_color)
        self.screen.blit(txt_ecg, (dash_rect.x + 18, ecg_y))

        scope_rect = pygame.Rect(dash_rect.x + 20, ecg_y + 26, 330, 85)
        pygame.draw.rect(self.screen, (10, 18, 14), scope_rect, border_radius=6)
        pygame.draw.rect(self.screen, (40, 80, 50), scope_rect, 1, border_radius=6)

        for gx in range(scope_rect.x, scope_rect.right, 30):
            pygame.draw.line(self.screen, (18, 35, 25), (gx, scope_rect.y), (gx, scope_rect.bottom))
        for gy in range(scope_rect.y, scope_rect.bottom, 20):
            pygame.draw.line(self.screen, (18, 35, 25), (scope_rect.x, gy), (scope_rect.right, gy))

        wave_pts = []
        wave_list = list(bio.ecg_wave)
        mid_y = scope_rect.y + scope_rect.height // 2
        step_x = scope_rect.width / len(wave_list)

        for idx, val in enumerate(wave_list):
            px = scope_rect.x + idx * step_x
            py = mid_y - (val * 32)
            wave_pts.append((px, py))

        if len(wave_pts) > 1:
            line_color = (255, 60, 60) if bio.ecg_bpm > 100 else (50, 255, 120)
            pygame.draw.lines(self.screen, line_color, False, wave_pts, 2)

        # 心率上下微調按鈕與深呼吸按鈕 (在外部模式下顯示鎖定灰階)
        self.btn_ecg_down = pygame.Rect(dash_rect.x + 365, ecg_y + 24, 62, 26)
        self.btn_ecg_up = pygame.Rect(dash_rect.x + 435, ecg_y + 24, 65, 26)
        ed_rect, ed_p = self._get_anim_rect_and_active(self.btn_ecg_down, "ECG_DOWN")
        eu_rect, eu_p = self._get_anim_rect_and_active(self.btn_ecg_up, "ECG_UP")

        btn_ecg_bg = (38, 42, 48) if is_ext else (65, 80, 100)
        btn_ecg_fg = (110, 115, 125) if is_ext else (235, 240, 245)
        pygame.draw.rect(self.screen, btn_ecg_bg, ed_rect, border_radius=4)
        pygame.draw.rect(self.screen, btn_ecg_bg, eu_rect, border_radius=4)
        if ed_p:
            pygame.draw.rect(self.screen, (255, 220, 80), ed_rect, 2, border_radius=4)
        if eu_p:
            pygame.draw.rect(self.screen, (255, 220, 80), eu_rect, 2, border_radius=4)

        t_ed = self.font_small.render("🔒BPM▼" if is_ext else "BPM▼", True, btn_ecg_fg)
        t_eu = self.font_small.render("🔒BPM▲" if is_ext else "BPM▲", True, btn_ecg_fg)
        self.screen.blit(t_ed, (ed_rect.centerx - t_ed.get_width() // 2, ed_rect.centery - t_ed.get_height() // 2))
        self.screen.blit(t_eu, (eu_rect.centerx - t_eu.get_width() // 2, eu_rect.centery - t_eu.get_height() // 2))

        self.btn_breathe = pygame.Rect(dash_rect.x + 365, ecg_y + 56, 135, 55)
        br_rect, br_p = self._get_anim_rect_and_active(self.btn_breathe, "BREATHE")
        if is_ext:
            breathe_col = (38, 42, 48)
            txt_br1 = self.font_main.render("🔒外部ECG控制", True, (120, 125, 135))
            txt_br2 = self.font_small.render("[停用手動深呼吸]", True, (100, 105, 115))
        else:
            breathe_col = (39, 174, 96) if bio.is_deep_breathing else (52, 73, 94)
            txt_br1 = self.font_bold.render("深呼吸放鬆", True, (255, 255, 255))
            txt_br2 = self.font_small.render("[按住 R 降心率]", True, (200, 240, 220))

        pygame.draw.rect(self.screen, breathe_col, br_rect, border_radius=6)
        pygame.draw.rect(self.screen, (255, 220, 80) if br_p else (100, 110, 125), br_rect, 2 if br_p else 1, border_radius=6)
        self.screen.blit(txt_br1, (br_rect.centerx - txt_br1.get_width() // 2, br_rect.y + 7))
        self.screen.blit(txt_br2, (br_rect.centerx - txt_br2.get_width() // 2, br_rect.y + 32))

        # ==================== 3. EEG 腦波專注度 ====================
        eeg_y = dash_rect.y + 245
        eeg_hint = "[外部訊號輸入中🔒]" if is_ext else "(按鍵盤 W/S 微調透明度)"
        txt_eeg = self.font_main.render(f"3. EEG 專注度 [目前：{bio.eeg_focus:.0f}%] {eeg_hint}", True, (255, 255, 255))
        self.screen.blit(txt_eeg, (dash_rect.x + 18, eeg_y))

        eeg_bar_bg = pygame.Rect(dash_rect.x + 20, eeg_y + 28, 330, 30)
        pygame.draw.rect(self.screen, (40, 45, 55), eeg_bar_bg, border_radius=6)
        focus_w = int((bio.eeg_focus / 100.0) * 330)

        if bio.eeg_focus >= 70:
            focus_col = (241, 196, 15)
        elif bio.eeg_focus >= 45:
            focus_col = (52, 152, 219)
        else:
            focus_col = (120, 120, 130)

        pygame.draw.rect(self.screen, focus_col, (eeg_bar_bg.x, eeg_bar_bg.y, focus_w, eeg_bar_bg.height), border_radius=6)
        pygame.draw.rect(self.screen, (100, 110, 130), eeg_bar_bg, 1, border_radius=6)

        _, clarity_desc = bio.get_cheat_opacity_and_blur()
        txt_focus_desc = self.font_small.render(f"狀態：{clarity_desc}", True, (255, 255, 255))
        self.screen.blit(txt_focus_desc, (eeg_bar_bg.x + 10, eeg_bar_bg.y + 6))

        self.btn_focus_down = pygame.Rect(dash_rect.x + 365, eeg_y + 24, 62, 36)
        self.btn_focus_up = pygame.Rect(dash_rect.x + 435, eeg_y + 24, 65, 36)
        fd_rect, fd_p = self._get_anim_rect_and_active(self.btn_focus_down, "FOCUS_DOWN")
        fu_rect, fu_p = self._get_anim_rect_and_active(self.btn_focus_up, "FOCUS_UP")

        pygame.draw.rect(self.screen, btn_ecg_bg, fd_rect, border_radius=4)
        pygame.draw.rect(self.screen, btn_ecg_bg, fu_rect, border_radius=4)
        if fd_p:
            pygame.draw.rect(self.screen, (255, 220, 80), fd_rect, 2, border_radius=4)
        if fu_p:
            pygame.draw.rect(self.screen, (255, 220, 80), fu_rect, 2, border_radius=4)

        t_fd = self.font_small.render("🔒分心" if is_ext else "分心(S)", True, btn_ecg_fg)
        t_fu = self.font_small.render("🔒專注" if is_ext else "專注(W)", True, btn_ecg_fg)
        self.screen.blit(t_fd, (fd_rect.centerx - t_fd.get_width() // 2, fd_rect.centery - t_fd.get_height() // 2))
        self.screen.blit(t_fu, (fu_rect.centerx - t_fu.get_width() // 2, fu_rect.centery - t_fu.get_height() // 2))

        # ==================== 4. 底部操作說明 / 外部訊號狀態區 ====================
        op_rect = pygame.Rect(dash_rect.x + 15, dash_rect.y + 318, 490, 95)
        pygame.draw.rect(self.screen, (32, 38, 48), op_rect, border_radius=6)

        if not is_ext:
            self.btn_cycle_port = pygame.Rect(0, 0, 0, 0)
            op_title = self.font_small.render("【模式一：手動調控指南】(可隨時按 M 鍵切換外部模式)", True, (100, 240, 150))
            op_t1 = self.font_small.render("• [空白鍵] / [C鍵] / [滑鼠右鍵] / [點EMG]：切換拿起/收起手中密藏小抄", True, (210, 220, 235))
            op_t2 = self.font_small.render("• [方向鍵 ↑ / ↓] 或 [BPM▲/▼]：直接調控 ECG 心率 | [R 鍵]：深呼吸降心率", True, (255, 190, 190))
            op_t3 = self.font_small.render("• [W / S 鍵] 或 [專注/分心]：直接調控 EEG 專注度 (控制小抄透明度)", True, (180, 220, 255))
            self.screen.blit(op_title, (op_rect.x + 10, op_rect.y + 6))
            self.screen.blit(op_t1, (op_rect.x + 10, op_rect.y + 28))
            self.screen.blit(op_t2, (op_rect.x + 10, op_rect.y + 50))
            self.screen.blit(op_t3, (op_rect.x + 10, op_rect.y + 72))
        else:
            # 外部訊號輸入模式面板
            is_live = bio.is_external_signal_active()
            status_col = (46, 204, 113) if is_live else (241, 196, 15)
            live_str = f"🟢 已連線接收中 ({bio.external_source_name} | 封包:{bio.external_packet_count})" if is_live else "🟡 等待外部輸入 ECG, EEG 訊號..."
            op_title = self.font_small.render(f"【模式二：外部訊號輸入】{live_str}", True, status_col)
            self.screen.blit(op_title, (op_rect.x + 10, op_rect.y + 6))

            # 切換 Serial COM 埠按鈕
            self.btn_cycle_port = pygame.Rect(op_rect.right - 145, op_rect.y + 4, 138, 24)
            cp_rect, cp_p = self._get_anim_rect_and_active(self.btn_cycle_port, "PORT_CYCLE")
            pygame.draw.rect(self.screen, (65, 85, 115), cp_rect, border_radius=4)
            pygame.draw.rect(self.screen, (255, 220, 80) if cp_p else (160, 190, 230), cp_rect, 1, border_radius=4)
            port_lbl = f"COM埠: {hw_bridge.port or '自動/UDP'}" if hw_bridge else "切換 COM 埠"
            t_cp = self.font_small.render(port_lbl, True, (255, 255, 255))
            self.screen.blit(t_cp, (cp_rect.centerx - t_cp.get_width() // 2, cp_rect.centery - t_cp.get_height() // 2))

            op_t1 = self.font_small.render("• 手動調控 ECG/EEG 已鎖定！小抄(EMG)仍可由 [空白鍵/滑鼠右鍵/按鈕] 觸發", True, (220, 200, 255))
            op_t2 = self.font_small.render("• 外部輸入方式 1 (Arduino/序列埠)：傳送 \"ECG:85,EEG:78\" 至 COM 埠", True, (200, 220, 235))
            op_t3 = self.font_small.render("• 外部輸入方式 2 (UDP/Python)：執行 external_signal_sender.py 傳至埠 5005", True, (200, 220, 235))
            self.screen.blit(op_t1, (op_rect.x + 10, op_rect.y + 30))
            self.screen.blit(op_t2, (op_rect.x + 10, op_rect.y + 51))
            self.screen.blit(op_t3, (op_rect.x + 10, op_rect.y + 72))

    def _draw_bio_chart(self, chart_rect, records):
        """在結算畫面上繪製整場考試的生理趨勢走勢圖 (心率 & 專注度)"""
        pygame.draw.rect(self.screen, (20, 25, 32), chart_rect, border_radius=6)
        pygame.draw.rect(self.screen, (70, 80, 95), chart_rect, 1, border_radius=6)

        if not records or len(records) < 2:
            no_data = self.font_small.render("尚無足夠生理訊號記錄", True, (150, 150, 150))
            self.screen.blit(no_data, (chart_rect.centerx - no_data.get_width() // 2, chart_rect.centery - no_data.get_height() // 2))
            return

        c_title = self.font_small.render("📊 受試者生理歷程回顧 [紅: ECG心率(BPM) | 金: EEG專注度(%) | 灰區: 開小抄]", True, (230, 230, 230))
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
        """渲染被抓包或未達 90 分之失敗結算畫面"""
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 195))
        self.screen.blit(overlay, (0, 0))

        box = pygame.Rect(self.width // 2 - 360, self.height // 2 - 225, 720, 450)
        pygame.draw.rect(self.screen, (245, 245, 245), box, border_radius=12)
        pygame.draw.rect(self.screen, self.COLOR_ALERT, box, 4, border_radius=12)

        t_over = self.font_large.render("【作弊被奶龍抓包！慘遭當掉！】" if reason == "BUSTED" else "【成績不合格！只能停修！】", True, self.COLOR_ALERT)
        self.screen.blit(t_over, (box.centerx - t_over.get_width() // 2, box.y + 22))

        if reason == "BUSTED" and self.img_nailong:
            nl_small = pygame.transform.smoothscale(self.img_nailong, (70, 90))
            self.screen.blit(nl_small, (box.right - 88, box.y + 16))

        if reason == "BUSTED":
            t_sub1 = self.font_bold.render("🟡 奶龍捧著大肚子仰天狂笑：『哈哈哈哈！被我抓到了吧！零分！』", True, (50, 50, 50))
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
        """渲染成功拿高分通過 (>= 90分)"""
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 185))
        self.screen.blit(overlay, (0, 0))

        box = pygame.Rect(self.width // 2 - 360, self.height // 2 - 225, 720, 450)
        pygame.draw.rect(self.screen, (245, 255, 245), box, border_radius=12)
        pygame.draw.rect(self.screen, self.COLOR_SUCCESS, box, 4, border_radius=12)

        t_win = self.font_large.render("【恭喜通關！成功奪得 A+！】", True, (39, 174, 96))
        self.screen.blit(t_win, (box.centerx - t_win.get_width() // 2, box.y + 22))

        t_sub1 = self.font_bold.render(f"最終成績：{score} 分 (完美達到 90 分以上！)", True, (40, 40, 40))
        t_sub2 = self.font_main.render("你成功在奶龍的狂笑法眼下精準控制心率與專注度，未被抓包順利生存！", True, (80, 80, 80))
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
        """渲染遊戲首頁封面與【雙模式選擇介面】"""
        self.screen.fill((20, 28, 40))

        frame_rect = pygame.Rect(40, 25, self.width - 80, self.height - 50)
        pygame.draw.rect(self.screen, (35, 48, 68), frame_rect, border_radius=12)
        pygame.draw.rect(self.screen, (52, 152, 219), frame_rect, 2, border_radius=12)

        # 主標題
        title_main = self.font_large.render("NeuroCheat", True, (255, 255, 255))
        scaled_title = pygame.transform.smoothscale(title_main, (int(title_main.get_width() * 1.45), int(title_main.get_height() * 1.45)))
        t_x = self.width // 2 - scaled_title.get_width() // 2
        t_y = 50
        self.screen.blit(scaled_title, (t_x, t_y))

        if self.img_nailong:
            nl_icon = pygame.transform.smoothscale(self.img_nailong, (52, 66))
            self.screen.blit(nl_icon, (t_x - 68, t_y - 6))
            nl_flip = pygame.transform.flip(nl_icon, True, False)
            self.screen.blit(nl_flip, (t_x + scaled_title.get_width() + 16, t_y - 6))

        subtitle = self.font_bold.render("Don't Get Caught, a Brain Control Exam Survival Game", True, (130, 200, 255))
        self.screen.blit(subtitle, (self.width // 2 - subtitle.get_width() // 2, 115))

        group_txt = self.font_main.render("生醫工程期末專題 — Group 6  |  B13502162 黃建澄  •  B13901094 王家佑  •  B13901135 張嘉宸", True, (241, 196, 15))
        self.screen.blit(group_txt, (self.width // 2 - group_txt.get_width() // 2, 148))

        # 核心生理訊號機制卡片
        card_w = 340
        card_h = 135
        card_y = 185

        c1 = pygame.Rect(self.width // 2 - card_w * 1.5 - 20, card_y, card_w, card_h)
        pygame.draw.rect(self.screen, (28, 38, 54), c1, border_radius=8)
        pygame.draw.rect(self.screen, (231, 76, 60), c1, 2, border_radius=8)
        self.screen.blit(self.font_bold.render("1. EMG 握拳 (以按鈕代替)", True, (255, 120, 120)), (c1.x + 15, c1.y + 12))
        self.screen.blit(self.font_small.render("• 按 [空白鍵/右鍵/按鈕] 將小抄拿在手上", True, (210, 210, 210)), (c1.x + 15, c1.y + 46))
        self.screen.blit(self.font_small.render("• 奶龍轉身巡視時務必放開收起小抄", True, (210, 210, 210)), (c1.x + 15, c1.y + 72))
        self.screen.blit(self.font_small.render("• 被奶龍抓包直接記零分當掉！", True, (255, 180, 180)), (c1.x + 15, c1.y + 98))

        c2 = pygame.Rect(self.width // 2 - card_w // 2, card_y, card_w, card_h)
        pygame.draw.rect(self.screen, (28, 38, 54), c2, border_radius=8)
        pygame.draw.rect(self.screen, (241, 196, 15), c2, 2, border_radius=8)
        self.screen.blit(self.font_bold.render("2. EEG 腦波專注度", True, (255, 220, 100)), (c2.x + 15, c2.y + 12))
        self.screen.blit(self.font_small.render("• 專注度決定手中密藏小抄的字體透明度", True, (210, 210, 210)), (c2.x + 15, c2.y + 46))
        self.screen.blit(self.font_small.render("• 專注 (>80%)：字體 100% 飽和清晰", True, (210, 210, 210)), (c2.x + 15, c2.y + 72))
        self.screen.blit(self.font_small.render("• 分心 (<25%)：字體完全透明隱形！", True, (210, 210, 210)), (c2.x + 15, c2.y + 98))

        c3 = pygame.Rect(self.width // 2 + card_w * 0.5 + 20, card_y, card_w, card_h)
        pygame.draw.rect(self.screen, (28, 38, 54), c3, border_radius=8)
        pygame.draw.rect(self.screen, (46, 204, 113), c3, 2, border_radius=8)
        self.screen.blit(self.font_bold.render("3. ECG 心率與緊張度", True, (120, 255, 160)), (c3.x + 15, c3.y + 12))
        self.screen.blit(self.font_small.render("• 即時繪製 P-Q-R-S-T 心電圖示波器", True, (210, 210, 210)), (c3.x + 15, c3.y + 46))
        self.screen.blit(self.font_small.render("• 心率飆高會觸發蜂鳴器並吸引奶龍巡邏", True, (210, 210, 210)), (c3.x + 15, c3.y + 72))
        self.screen.blit(self.font_small.render("• 維持心率平穩可大幅降低被抓風險", True, (210, 210, 210)), (c3.x + 15, c3.y + 98))

        req_txt = self.font_bold.render("★ 過關條件：120 秒內取得 90 分以上 (A+) 即可過關，寫完可提早交卷！", True, (255, 185, 60))
        self.screen.blit(req_txt, (self.width // 2 - req_txt.get_width() // 2, 335))

        # ==================== 雙模式選擇區 ====================
        mode_y = 378
        mode_w = 500
        mode_h = 185

        # 模式一：手動調控模式
        self.btn_mode_manual = pygame.Rect(self.width // 2 - mode_w - 20, mode_y, mode_w, mode_h)
        m1_hover = self.btn_mode_manual.collidepoint(mouse_pos)
        m1_bg = (36, 95, 68) if m1_hover else (28, 72, 52)
        pygame.draw.rect(self.screen, m1_bg, self.btn_mode_manual, border_radius=10)
        pygame.draw.rect(self.screen, (46, 204, 113), self.btn_mode_manual, 3 if m1_hover else 2, border_radius=10)

        t_m1_title = self.font_large.render("🟢 模式一：手動調控模式", True, (255, 255, 255))
        t_m1_sub = self.font_bold.render("【自己調控 ECG、EEG、EMG】(按 1 或空白鍵開始)", True, (140, 255, 180))
        t_m1_d1 = self.font_small.render("• 玩家可自行用方向鍵 [↑/↓] 與螢幕按鈕自由控制 ECG 心率", True, (225, 235, 230))
        t_m1_d2 = self.font_small.render("• 可自行用 [W/S 鍵] 調整 EEG 專注度，[空白鍵/按鈕] 控制 EMG 小抄", True, (225, 235, 230))
        t_m1_d3 = self.font_small.render("👉 適合單機遊玩、測試遊戲機制與課堂 Demo 展示", True, (255, 230, 120))
        self.screen.blit(t_m1_title, (self.btn_mode_manual.x + 22, self.btn_mode_manual.y + 14))
        self.screen.blit(t_m1_sub, (self.btn_mode_manual.x + 22, self.btn_mode_manual.y + 56))
        self.screen.blit(t_m1_d1, (self.btn_mode_manual.x + 22, self.btn_mode_manual.y + 92))
        self.screen.blit(t_m1_d2, (self.btn_mode_manual.x + 22, self.btn_mode_manual.y + 118))
        self.screen.blit(t_m1_d3, (self.btn_mode_manual.x + 22, self.btn_mode_manual.y + 146))

        # 模式二：外部訊號輸入模式
        self.btn_mode_external = pygame.Rect(self.width // 2 + 20, mode_y, mode_w, mode_h)
        m2_hover = self.btn_mode_external.collidepoint(mouse_pos)
        m2_bg = (82, 48, 108) if m2_hover else (62, 36, 84)
        pygame.draw.rect(self.screen, m2_bg, self.btn_mode_external, border_radius=10)
        pygame.draw.rect(self.screen, (187, 143, 206), self.btn_mode_external, 3 if m2_hover else 2, border_radius=10)

        t_m2_title = self.font_large.render("🟣 模式二：外部訊號模式", True, (255, 255, 255))
        t_m2_sub = self.font_bold.render("【必須從外部輸入 ECG、EEG】(按 2 或點擊開始)", True, (235, 190, 255))
        t_m2_d1 = self.font_small.render("• 鎖定鍵盤/畫面之 ECG 與 EEG 手動微調，必須由外部訊號驅動！", True, (235, 225, 240))
        t_m2_d2 = self.font_small.render("• 支援 Arduino/ESP32 Serial COM 埠、UDP:5005 與 JSON 即時串流", True, (235, 225, 240))
        t_m2_d3 = self.font_small.render("• EMG 小抄依提案維持以按鈕 (空白鍵/右鍵/畫面按鈕/外部EMG) 觸發", True, (255, 230, 120))
        self.screen.blit(t_m2_title, (self.btn_mode_external.x + 22, self.btn_mode_external.y + 14))
        self.screen.blit(t_m2_sub, (self.btn_mode_external.x + 22, self.btn_mode_external.y + 56))
        self.screen.blit(t_m2_d1, (self.btn_mode_external.x + 22, self.btn_mode_external.y + 92))
        self.screen.blit(t_m2_d2, (self.btn_mode_external.x + 22, self.btn_mode_external.y + 118))
        self.screen.blit(t_m2_d3, (self.btn_mode_external.x + 22, self.btn_mode_external.y + 146))

        # 底部硬體連接狀態與 COM 埠切換按鈕
        hw_y = 582
        self.btn_cycle_port = pygame.Rect(self.width // 2 - 260, hw_y, 520, 42)
        cp_hover = self.btn_cycle_port.collidepoint(mouse_pos)
        pygame.draw.rect(self.screen, (45, 62, 85) if cp_hover else (32, 44, 62), self.btn_cycle_port, border_radius=8)
        pygame.draw.rect(self.screen, (100, 180, 240), self.btn_cycle_port, 1, border_radius=8)

        port_info = hw_bridge.status_text if hw_bridge else "UDP:5005 就緒"
        t_port = self.font_main.render(f"🔌 外部訊號通道：{port_info} (點此切換 COM 埠)", True, (180, 230, 255))
        self.screen.blit(t_port, (self.btn_cycle_port.centerx - t_port.get_width() // 2, self.btn_cycle_port.centery - t_port.get_height() // 2))

        footer_hint = self.font_small.render("提示：進入遊戲後仍可隨時點擊右側儀表板上方按鈕或按 [M 鍵] 切換模式，按 [ESC] 返回此選單", True, (170, 185, 205))
        self.screen.blit(footer_hint, (self.width // 2 - footer_hint.get_width() // 2, 638))

    def _wrap_text(self, text, font, max_width):
        """文字自動斷行換行演算法"""
        words = list(text)
        lines = []
        curr = ""
        for char in words:
            test = curr + char
            if font.size(test)[0] <= max_width:
                curr = test
            else:
                lines.append(curr)
                curr = char
        if curr:
            lines.append(curr)
        return lines
