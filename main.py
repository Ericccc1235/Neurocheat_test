"""
main.py - NeuroCheat: 生醫電子考場潛行 主程式進入點
==================================================
支援單機鍵鼠模擬與 Exp 2 (Arduino ECG/EMG) + Exp 3 (BrainLink EEG) 即時硬體串流。
"""

import ctypes
import os
import sys
import threading
import pygame

# 確保無論從哪個工作目錄啟動都能正確匯入 game / bio_bridge / analytics
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from game.bio_signals import BioSignalManager
from game.hardware_bridge import HardwareBridge
from game.exam import ExamManager
from game.teacher import TeacherAI
from game.classroom_3d import Classroom3DRenderer
from game.ui_renderer import UIRenderer
from game.sound_generator import SoundManager
from game.data_logger import BioDataLogger
from analytics.analyze_bio_data import analyze_session


SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60
CALIB_STEP_DUR = 5.0


def _enable_windows_dpi_awareness():
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class NeuroCheatApp:
    def __init__(self):
        _enable_windows_dpi_awareness()
        pygame.init()
        pygame.display.set_caption("NeuroCheat: 生醫電子考場潛行 (Exp 2 + Exp 3)")
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()

        self.bio = BioSignalManager(initial_mode=BioSignalManager.MODE_MANUAL)
        self.hw_bridge = HardwareBridge(self.bio, udp_port=5005, cmd_port=5006)
        self.hw_bridge.start()

        self.difficulty = "NORMAL"
        self.exam = ExamManager(difficulty=self.difficulty)
        self.teacher = TeacherAI(difficulty=self.difficulty)
        self.sound = SoundManager()
        self.logger = BioDataLogger(record_interval=0.25)

        self.ui = UIRenderer(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.classroom = Classroom3DRenderer(self.ui.viewport_rect)

        self.state = "TITLE"  # TITLE | CALIBRATION | PLAYING | BUSTED | TIMEOUT_FAIL | VICTORY
        self.running = True
        self.last_csv_path = None
        self._heartbeat_accum = 0.0
        self._manual_full_toggle = False

        # 3 步驟考前基線校正狀態 (15 秒)
        self.calib_step = 0
        self.calib_elapsed = 0.0
        self._calib_bpm_samples = []

    def start_new_exam(self):
        self.exam.reset(self.difficulty)
        self.teacher.reset(self.difficulty)
        self.bio.reset()
        self.classroom.reset()
        self.logger.reset()
        self.last_csv_path = None
        self._manual_full_toggle = False
        self._heartbeat_accum = 0.0
        self.state = "PLAYING"

    def start_calibration(self):
        self.bio.reset()
        self.calib_step = 0
        self.calib_elapsed = 0.0
        self._calib_bpm_samples = []
        self.hw_bridge.send_game_command("CALIB_REST")
        self.state = "CALIBRATION"

    def _finish_exam_session(self, end_state):
        self.state = end_state
        try:
            self.last_csv_path = self.logger.export_csv()
            png_path = os.path.join(os.path.dirname(self.last_csv_path), "bio_analysis_report.png")
            threading.Thread(
                target=analyze_session,
                kwargs={"csv_path": self.last_csv_path, "save_path": png_path, "show": False},
                daemon=True,
            ).start()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 主迴圈與事件派發
    # ------------------------------------------------------------------
    def run(self):
        while self.running:
            dt = min(0.05, self.clock.tick(FPS) / 1000.0)
            self._handle_events()
            self._update(dt)
            self._render()
            pygame.display.flip()

        self.hw_bridge.stop()
        pygame.quit()

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                self.screen = pygame.display.set_mode((max(1000, event.w), max(640, event.h)), pygame.RESIZABLE)
                self.ui.update_layout(*self.screen.get_size())
                self.classroom.set_viewport(self.ui.viewport_rect)

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F1:
                    self.bio.toggle_mode()
                elif event.key == pygame.K_F2:
                    self.hw_bridge.cycle_serial_port()
                else:
                    self._on_keydown(event.key)

            elif event.type == pygame.KEYUP:
                if self.state == "PLAYING" and event.key == pygame.K_f:
                    if not self._manual_full_toggle:
                        self.bio.set_manual_peek(False)
                elif self.state == "PLAYING" and event.key == pygame.K_r:
                    self.bio.set_deep_breath(False)
                elif self.state == "PLAYING" and event.key == pygame.K_v:
                    self.classroom.set_lean_forward(False)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if self.ui.mode_btn_rect.collidepoint(event.pos):
                    self.bio.toggle_mode()
                    continue
                self._on_mouse_down(event)

    def _on_keydown(self, key):
        if self.state == "TITLE":
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self.start_new_exam()
            elif key == pygame.K_c:
                self.start_calibration()

        elif self.state == "CALIBRATION":
            if key in (pygame.K_ESCAPE, pygame.K_RETURN):
                self.hw_bridge.send_game_command("CALIB_DONE")
                self.start_new_exam()

        elif self.state == "PLAYING":
            if key == pygame.K_ESCAPE:
                self.state = "TITLE"
            elif key == pygame.K_SPACE:
                self._manual_full_toggle = not self._manual_full_toggle
                self.bio.trigger_emg_clench(self._manual_full_toggle)
                self.sound.play_paper()
            elif key == pygame.K_f:
                if not self._manual_full_toggle:
                    self.bio.set_manual_peek(True)
                    self.sound.play_paper()
            elif key == pygame.K_r:
                self.bio.set_deep_breath(True)
            elif key == pygame.K_v:
                self.classroom.set_lean_forward(True)
            elif key == pygame.K_TAB:
                self.bio.flip_cheat_page()
                self.sound.play_page_flip()
            elif key in (pygame.K_LEFT, pygame.K_a):
                self.exam.prev_question()
                self.sound.play_click()
            elif key in (pygame.K_RIGHT, pygame.K_d):
                self.exam.next_question()
                self.sound.play_click()
            elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                self._select_exam_option(key - pygame.K_1)
            elif key == pygame.K_q:
                self.bio.adjust_manual(d_focus=-10.0)
            elif key == pygame.K_e:
                self.bio.adjust_manual(d_focus=+10.0)
            elif key == pygame.K_z:
                self.bio.adjust_manual(d_stroop=+12.0)
            elif key == pygame.K_x:
                self.bio.adjust_manual(d_stroop=-12.0)
            elif key in (pygame.K_UP, pygame.K_w):
                self.bio.adjust_manual(d_bpm=+6.0)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.bio.adjust_manual(d_bpm=-6.0)

        elif self.state in ("BUSTED", "TIMEOUT_FAIL", "VICTORY"):
            if key in (pygame.K_r, pygame.K_SPACE):
                self.start_new_exam()
            elif key in (pygame.K_m, pygame.K_ESCAPE):
                self.state = "TITLE"

    def _on_mouse_down(self, event):
        if self.state == "TITLE":
            for diff_key, rect in self.ui.diff_rects.items():
                if rect.collidepoint(event.pos):
                    self.difficulty = diff_key
                    self.sound.play_click()
                    return
            if self.ui.start_manual_rect.collidepoint(event.pos):
                self.start_new_exam()
            elif self.ui.start_calib_rect.collidepoint(event.pos):
                self.start_calibration()

        elif self.state == "CALIBRATION":
            if self.ui.calib_skip_rect.collidepoint(event.pos):
                self.hw_bridge.send_game_command("CALIB_DONE")
                self.start_new_exam()

        elif self.state == "PLAYING":
            if event.button == 3:
                self._manual_full_toggle = not self._manual_full_toggle
                self.bio.trigger_emg_clench(self._manual_full_toggle)
                self.sound.play_paper()
            elif event.button == 1:
                kind, val = self.classroom.hit_test_paper(*event.pos)
                if kind == "opt":
                    self._select_exam_option(val)
                elif kind == "prev":
                    self.exam.prev_question()
                    self.sound.play_click()
                elif kind == "next":
                    self.exam.next_question()
                    self.sound.play_click()

        elif self.state in ("BUSTED", "TIMEOUT_FAIL", "VICTORY"):
            if self.ui.restart_rect.collidepoint(event.pos):
                self.start_new_exam()
            elif self.ui.menu_rect.collidepoint(event.pos):
                self.state = "TITLE"

    def _select_exam_option(self, opt_idx):
        q_idx = self.exam.current_q_idx
        peeked_this_q = (q_idx, "left") in self.classroom.peek_unlocked or (q_idx, "right") in self.classroom.peek_unlocked
        cheated = self.bio.emg_clenched or peeked_this_q
        _ok, honest_bonus = self.exam.select_option(opt_idx, cheated=cheated)
        self.sound.play_click()
        if honest_bonus:
            self.teacher.honest_relief(7.0)

    # ------------------------------------------------------------------
    # 更新邏輯
    # ------------------------------------------------------------------
    def _update(self, dt):
        if self.state == "CALIBRATION":
            self.bio.update(dt)
            self.calib_elapsed += dt
            if self.calib_step == 0 and self.bio.ecg_quality != "bad":
                self._calib_bpm_samples.append(self.bio.ecg_bpm)

            if self.calib_elapsed >= CALIB_STEP_DUR:
                self.calib_elapsed = 0.0
                if self.calib_step == 0:
                    if self._calib_bpm_samples:
                        avg_bpm = sum(self._calib_bpm_samples) / len(self._calib_bpm_samples)
                        self.bio.set_baseline_bpm(avg_bpm)
                    self.calib_step = 1
                    self.hw_bridge.send_game_command("CALIB_MVC")
                elif self.calib_step == 1:
                    self.calib_step = 2
                    self.hw_bridge.send_game_command("CALIB_FOCUS")
                else:
                    self.hw_bridge.send_game_command("CALIB_DONE")
                    self.start_new_exam()
            return

        if self.state != "PLAYING":
            return

        mouse_pos = pygame.mouse.get_pos()
        self.classroom.update(dt, self.exam.current_q_idx, mouse_screen_pos=mouse_pos)
        peek_side = self.classroom.camera.get_looking_neighbor_side()

        self.exam.update(dt)
        self.bio.update(
            dt,
            teacher_alert_level=self.teacher.get_alert_level(),
            teacher_facing_player=self.teacher.is_facing_player(),
            peeking_neighbor=(peek_side is not None),
        )

        # 雙眨眼自動翻頁 / 疲勞抽筋撞擊
        if self.bio.consume_double_blink():
            self.bio.flip_cheat_page()
            self.sound.play_page_flip()

        if self.bio.consume_cramp_slam():
            self._manual_full_toggle = False
            self.sound.play_slam()
            self.teacher.trigger_slam_alert()

        if self.classroom.consume_peek_unlocked_sfx():
            self.sound.play_peek()

        # 更新老師 AI
        entered_warn, _entered_patrol, _false_alarm = self.teacher.update(
            dt,
            self.bio,
            camera_yaw=self.classroom.camera.yaw,
            peeking_side=peek_side,
            exam_time_remaining=self.exam.time_remaining,
        )
        if entered_warn:
            self.sound.play_buzzer()

        hw_cmd = self.teacher.consume_hw_command()
        if hw_cmd:
            self.hw_bridge.send_game_command(hw_cmd)

        sfx = self.teacher.consume_sfx()
        if sfx == "cough":
            self.sound.play_cough()
        elif sfx == "distraction":
            self.sound.play_distraction()
        elif sfx == "footstep":
            self.sound.play_footstep()

        # 高壓心跳聲音效
        if self.bio.bpm_delta >= 12.0 or self.teacher.suspicion >= 60.0:
            beat_period = 60.0 / max(60.0, self.bio.ecg_bpm)
            self._heartbeat_accum += dt
            if self._heartbeat_accum >= beat_period:
                self._heartbeat_accum -= beat_period
                self.sound.play_heartbeat()
        else:
            self._heartbeat_accum = 0.0

        # 紀錄遙測資料
        self.logger.update(dt, self.bio, self.teacher, self.exam, peek_side=peek_side)

        # 勝負判定
        if self.teacher.busted:
            self.sound.play_busted()
            self._finish_exam_session("BUSTED")
        elif self.exam.is_all_answered() and self.exam.calculate_score() >= 90:
            self.sound.play_victory()
            self._finish_exam_session("VICTORY")
        elif self.exam.finished:
            if self.exam.calculate_score() >= 90:
                self.sound.play_victory()
                self._finish_exam_session("VICTORY")
            else:
                self.sound.play_busted()
                self._finish_exam_session("TIMEOUT_FAIL")

    # ------------------------------------------------------------------
    # 畫面渲染
    # ------------------------------------------------------------------
    def _render(self):
        if self.state == "TITLE":
            self.ui.render_title_screen(self.screen, self.hw_bridge, difficulty=self.difficulty)
            return

        if self.state == "CALIBRATION":
            self.ui.render_calibration_screen(
                self.screen, self.calib_step, self.calib_elapsed, CALIB_STEP_DUR, self.bio
            )
            return

        self.screen.fill((12, 16, 24))
        self.classroom.render(self.screen, self.exam, self.teacher, self.bio)
        self.ui.render_top_bar(self.screen, self.bio, self.exam, self.hw_bridge)
        self.ui.render_bio_dashboard(self.screen, self.bio, self.teacher, self.classroom.camera.yaw)

        if self.state in ("BUSTED", "TIMEOUT_FAIL"):
            self.ui.render_game_over(
                self.screen, self.state, self.exam, self.bio, self.teacher, self.last_csv_path
            )
        elif self.state == "VICTORY":
            self.ui.render_victory(self.screen, self.exam, self.bio, self.teacher, self.last_csv_path)


if __name__ == "__main__":
    app = NeuroCheatApp()
    app.run()
