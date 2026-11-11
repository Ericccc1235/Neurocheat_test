"""
NeuroCheat: Don't Get Caught - 生醫工程期末專題遊戲
主程式 (Main Loop) — 支援雙模式：
1. 【模式一：手動調控模式 (MANUAL)】：可自己調控 ECG (心率)、EEG (專注度) 與 EMG (小抄按鈕)
2. 【模式二：外部訊號模式 (EXTERNAL)】：必須從外部輸入 ECG、EEG 訊號 (Serial COM / UDP:5005 / JSON)，按鈕控制 EMG
作者：Group 6 (黃建澄、王家佑、張嘉宸)
"""

import sys
import pygame
from sound_generator import SoundManager
from exam import ExamManager
from bio_signals import BioSignalManager
from teacher import TeacherAI
from ui_renderer import UIRenderer
from hardware_bridge import HardwareBridge
from data_logger import BioDataLogger

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60

def main():
    pygame.init()
    # 關閉 Windows IME 文字輸入，防止中文輸入法攔截空白鍵
    try:
        pygame.key.stop_text_input()
    except Exception:
        pass

    pygame.display.set_caption("NeuroCheat: Don't Get Caught - 生醫工程期末專題 (Group 6)")

    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pygame.time.Clock()

    # 初始化模組
    sound_mgr = SoundManager()
    exam_mgr = ExamManager()
    bio_signals = BioSignalManager(sound_manager=sound_mgr, mode=BioSignalManager.MODE_MANUAL)
    teacher = TeacherAI(sound_manager=sound_mgr)
    ui = UIRenderer(screen, SCREEN_WIDTH, SCREEN_HEIGHT)
    data_logger = BioDataLogger()

    # 外部硬體與訊號串接模組 (同時監聽 Serial COM 埠、UDP 127.0.0.1:5005 與 external_signals.json)
    hw_bridge = HardwareBridge(bio_signals, port=None)
    hw_bridge.start()

    # 遊戲狀態: "TITLE", "PLAYING", "BUSTED", "TIMEOUT_FAIL", "VICTORY"
    game_state = "TITLE"
    prev_space_down = False
    prev_c_down = False
    csv_exported = False

    def start_new_game(selected_mode=None):
        """重置並開始新局，保留 BioSignalManager 實例以避免 HardwareBridge 參照斷裂"""
        nonlocal exam_mgr, teacher, csv_exported, game_state
        exam_mgr = ExamManager()
        bio_signals.reset(keep_mode=True)
        if selected_mode is not None:
            bio_signals.set_mode(selected_mode)
        teacher = TeacherAI(sound_manager=sound_mgr)
        data_logger.start()
        csv_exported = False
        game_state = "PLAYING"
        sound_mgr.play_click()

        if bio_signals.is_external_mode():
            ui.trigger_feedback("🟣 已進入【模式二：外部訊號模式】！請由外部輸入 ECG & EEG 訊號", color=(187, 143, 206))
        else:
            ui.trigger_feedback("🟢 已進入【模式一：手動調控模式】！可自行調控 ECG、EEG、EMG", color=(46, 204, 113))

    def switch_game_mode():
        """在遊戲中即時切換手動模式與外部訊號模式"""
        sound_mgr.play_click()
        if bio_signals.is_external_mode():
            bio_signals.set_mode(BioSignalManager.MODE_MANUAL)
            ui.trigger_feedback("🟢 已切換為【模式一：手動調控模式】(可自己調控 ECG/EEG/EMG)", color=(46, 204, 113), btn_name="MODE_SWITCH")
        else:
            bio_signals.set_mode(BioSignalManager.MODE_EXTERNAL)
            ui.trigger_feedback("🟣 已切換為【模式二：外部訊號模式】(必須從外部輸入 ECG/EEG)", color=(187, 143, 206), btn_name="MODE_SWITCH")

    def notify_external_locked():
        """當處於外部訊號模式卻嘗試手動調整 ECG/EEG 時的提示"""
        ui.trigger_feedback("🔒 目前為【外部訊號模式】，必須從外部輸入 ECG/EEG！(按 M 可切換手動)", color=(231, 76, 60))

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        mouse_pos = pygame.mouse.get_pos()
        ui.update_feedback(dt)
        state_changed_this_frame = False

        # ---------------- 1. 事件監聽 (鍵盤 / 滑鼠) ----------------
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break

            elif event.type == pygame.KEYDOWN:
                if game_state == "TITLE":
                    if event.key in (pygame.K_1, pygame.K_KP1, pygame.K_SPACE, pygame.K_RETURN):
                        start_new_game(BioSignalManager.MODE_MANUAL)
                        state_changed_this_frame = True
                    elif event.key in (pygame.K_2, pygame.K_KP2):
                        start_new_game(BioSignalManager.MODE_EXTERNAL)
                        state_changed_this_frame = True
                    elif event.key == pygame.K_p:
                        status_msg = hw_bridge.cycle_serial_port()
                        sound_mgr.play_click()
                        ui.trigger_feedback(f"🔌 {status_msg}", color=(100, 200, 255), btn_name="PORT_CYCLE")

                elif game_state == "PLAYING":
                    # ESC 返回首頁模式選單
                    if event.key == pygame.K_ESCAPE:
                        sound_mgr.play_click()
                        game_state = "TITLE"
                        state_changed_this_frame = True
                        ui.trigger_feedback("🏠 已返回首頁模式選擇畫面", color=(100, 200, 255))

                    # M 鍵切換雙模式
                    elif event.key == pygame.K_m:
                        switch_game_mode()

                    # 空白鍵 / C / E 鍵由下方硬體輪詢統一處理，避免重複觸發
                    elif event.key in (pygame.K_SPACE, pygame.K_c, pygame.K_e):
                        pass

                    # 深呼吸放鬆 (R 鍵)
                    elif event.key == pygame.K_r:
                        if bio_signals.set_deep_breathing(True):
                            ui.trigger_feedback("🌿 [按住 R] 深呼吸放鬆中... 心率正在平復", color=(46, 204, 113), btn_name="BREATHE")
                        else:
                            notify_external_locked()

                    # 【方向鍵 ↑ / ↓ 控制 ECG 心率】
                    elif event.key in (pygame.K_UP, pygame.K_RIGHTBRACKET, pygame.K_p):
                        if bio_signals.adjust_bpm(5.0):
                            sound_mgr.play_click()
                            ui.trigger_feedback(f"💓 [上鍵 ↑] ECG心率調升：{bio_signals.ecg_bpm:.0f} BPM (基準:{bio_signals.base_bpm:.0f})", color=(255, 100, 100), btn_name="ECG_UP")
                        else:
                            notify_external_locked()

                    elif event.key in (pygame.K_DOWN, pygame.K_LEFTBRACKET, pygame.K_o):
                        if bio_signals.adjust_bpm(-5.0):
                            sound_mgr.play_click()
                            ui.trigger_feedback(f"💓 [下鍵 ↓] ECG心率調降：{bio_signals.ecg_bpm:.0f} BPM (基準:{bio_signals.base_bpm:.0f})", color=(100, 255, 150), btn_name="ECG_DOWN")
                        else:
                            notify_external_locked()

                    # 【W / S 鍵控制 EEG 腦波專注度】
                    elif event.key == pygame.K_w:
                        if bio_signals.adjust_focus(10.0):
                            sound_mgr.play_click()
                            ui.trigger_feedback(f"🧠 [W鍵] EEG專注度提高：{bio_signals.eeg_focus:.0f}% (小抄更清晰！)", color=(241, 196, 15), btn_name="FOCUS_UP")
                        else:
                            notify_external_locked()

                    elif event.key == pygame.K_s:
                        if bio_signals.adjust_focus(-10.0):
                            sound_mgr.play_click()
                            ui.trigger_feedback(f"🧠 [S鍵] EEG專注度降低：{bio_signals.eeg_focus:.0f}% (小抄更透明！)", color=(180, 180, 190), btn_name="FOCUS_DOWN")
                        else:
                            notify_external_locked()

                    # 鍵盤作答 1/2/3/4 或 A/B/D
                    elif event.key in (pygame.K_1, pygame.K_KP1, pygame.K_a):
                        exam_mgr.select_answer(0)
                        sound_mgr.play_click()
                        ui.trigger_feedback("✏️ 已作答選項 [A]", color=(100, 210, 255), btn_name="OPT_0")

                    elif event.key in (pygame.K_2, pygame.K_KP2, pygame.K_b):
                        exam_mgr.select_answer(1)
                        sound_mgr.play_click()
                        ui.trigger_feedback("✏️ 已作答選項 [B]", color=(100, 210, 255), btn_name="OPT_1")

                    elif event.key in (pygame.K_3, pygame.K_KP3):
                        exam_mgr.select_answer(2)
                        sound_mgr.play_click()
                        ui.trigger_feedback("✏️ 已作答選項 [C]", color=(100, 210, 255), btn_name="OPT_2")

                    elif event.key in (pygame.K_4, pygame.K_KP4, pygame.K_d):
                        exam_mgr.select_answer(3)
                        sound_mgr.play_click()
                        ui.trigger_feedback("✏️ 已作答選項 [D]", color=(100, 210, 255), btn_name="OPT_3")

                    # 切換題目
                    elif event.key == pygame.K_LEFT:
                        if exam_mgr.prev_question():
                            sound_mgr.play_click()
                            ui.trigger_feedback(f"📄 切換至第 {exam_mgr.current_idx + 1} 題", color=(200, 220, 240), btn_name="PREV")

                    elif event.key == pygame.K_RIGHT:
                        if exam_mgr.next_question():
                            sound_mgr.play_click()
                            ui.trigger_feedback(f"📄 切換至第 {exam_mgr.current_idx + 1} 題", color=(200, 220, 240), btn_name="NEXT")

                else:
                    # 結算畫面按鍵
                    if event.key == pygame.K_ESCAPE:
                        sound_mgr.play_click()
                        game_state = "TITLE"
                        state_changed_this_frame = True
                    elif event.key in (pygame.K_SPACE, pygame.K_RETURN):
                        start_new_game()
                        state_changed_this_frame = True

            elif event.type == pygame.KEYUP:
                if game_state == "PLAYING":
                    if event.key == pygame.K_r:
                        bio_signals.set_deep_breathing(False)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if game_state == "TITLE":
                    if event.button == 1:
                        if ui.btn_mode_manual.collidepoint(mouse_pos):
                            start_new_game(BioSignalManager.MODE_MANUAL)
                            state_changed_this_frame = True
                        elif ui.btn_mode_external.collidepoint(mouse_pos):
                            start_new_game(BioSignalManager.MODE_EXTERNAL)
                            state_changed_this_frame = True
                        elif ui.btn_cycle_port.collidepoint(mouse_pos):
                            status_msg = hw_bridge.cycle_serial_port()
                            sound_mgr.play_click()
                            ui.trigger_feedback(f"🔌 {status_msg}", color=(100, 200, 255), btn_name="PORT_CYCLE")

                elif game_state == "PLAYING":
                    if event.button == 3:  # 滑鼠右鍵點擊：直接切換伸手打開/收回抽屜小抄
                        bio_signals.toggle_emg()
                        if bio_signals.emg_active:
                            ui.trigger_feedback("🖐️ 【滑鼠右鍵】已伸手拉開書桌抽屜並打開小抄！", color=(241, 196, 15), btn_name="EMG")
                        else:
                            ui.trigger_feedback("📥 【滑鼠右鍵】已將小抄合上並推回抽屜！", color=(100, 200, 255), btn_name="EMG")

                    elif event.button == 1:
                        # 0. 檢查模式切換按鈕
                        if ui.btn_switch_mode.collidepoint(mouse_pos):
                            switch_game_mode()

                        # 0.5 檢查 COM 埠切換按鈕 (外部模式)
                        elif ui.btn_cycle_port.width > 0 and ui.btn_cycle_port.collidepoint(mouse_pos):
                            status_msg = hw_bridge.cycle_serial_port()
                            sound_mgr.play_click()
                            ui.trigger_feedback(f"🔌 {status_msg}", color=(100, 200, 255), btn_name="PORT_CYCLE")

                        # 1. 檢查 EMG 按鈕 (點擊切換伸手打開抽屜小抄)
                        elif ui.btn_emg.collidepoint(mouse_pos):
                            bio_signals.toggle_emg()
                            if bio_signals.emg_active:
                                ui.trigger_feedback("🖐️ 【點擊按鈕】已伸手拉開書桌抽屜並展開小抄！", color=(241, 196, 15), btn_name="EMG")
                            else:
                                ui.trigger_feedback("📥 【點擊按鈕】已將小抄合上並推回抽屜！", color=(100, 200, 255), btn_name="EMG")

                        # 2. 檢查心率上下微調按鈕
                        elif ui.btn_ecg_up.collidepoint(mouse_pos):
                            if bio_signals.adjust_bpm(5.0):
                                sound_mgr.play_click()
                                ui.trigger_feedback(f"💓 【點擊按鍵】ECG心率調升：{bio_signals.ecg_bpm:.0f} BPM", color=(255, 100, 100), btn_name="ECG_UP")
                            else:
                                notify_external_locked()

                        elif ui.btn_ecg_down.collidepoint(mouse_pos):
                            if bio_signals.adjust_bpm(-5.0):
                                sound_mgr.play_click()
                                ui.trigger_feedback(f"💓 【點擊按鍵】ECG心率調降：{bio_signals.ecg_bpm:.0f} BPM", color=(100, 255, 150), btn_name="ECG_DOWN")
                            else:
                                notify_external_locked()

                        # 3. 檢查深呼吸按鈕
                        elif ui.btn_breathe.collidepoint(mouse_pos):
                            if bio_signals.set_deep_breathing(True):
                                sound_mgr.play_click()
                                ui.trigger_feedback("🌿 【點擊按鍵】深呼吸放鬆中... 心率平復...", color=(46, 204, 113), btn_name="BREATHE")
                            else:
                                notify_external_locked()

                        # 4. 檢查專注度調節按鈕
                        elif ui.btn_focus_up.collidepoint(mouse_pos):
                            if bio_signals.adjust_focus(10.0):
                                sound_mgr.play_click()
                                ui.trigger_feedback(f"🧠 【點擊按鍵】EEG專注度提高：{bio_signals.eeg_focus:.0f}% (小抄更清晰！)", color=(241, 196, 15), btn_name="FOCUS_UP")
                            else:
                                notify_external_locked()

                        elif ui.btn_focus_down.collidepoint(mouse_pos):
                            if bio_signals.adjust_focus(-10.0):
                                sound_mgr.play_click()
                                ui.trigger_feedback(f"🧠 【點擊按鍵】EEG專注度降低：{bio_signals.eeg_focus:.0f}% (小抄更透明！)", color=(180, 180, 190), btn_name="FOCUS_DOWN")
                            else:
                                notify_external_locked()

                        # 5. 導航按鈕：上一題 / 下一題
                        elif ui.btn_prev.collidepoint(mouse_pos):
                            if exam_mgr.prev_question():
                                sound_mgr.play_click()
                                ui.trigger_feedback(f"📄 切換至第 {exam_mgr.current_idx + 1} 題", color=(200, 220, 240), btn_name="PREV")

                        elif ui.btn_next.collidepoint(mouse_pos):
                            if exam_mgr.next_question():
                                sound_mgr.play_click()
                                ui.trigger_feedback(f"📄 切換至第 {exam_mgr.current_idx + 1} 題", color=(200, 220, 240), btn_name="NEXT")

                        # 6. 提早交卷按鈕
                        elif ui.btn_submit.collidepoint(mouse_pos):
                            sound_mgr.play_click()
                            ui.trigger_feedback("📝 提早交卷！正在結算期末考成績...", color=(255, 215, 0), btn_name="SUBMIT")
                            final_score = exam_mgr.calculate_score()
                            if final_score >= 90:
                                game_state = "VICTORY"
                                sound_mgr.play_victory()
                            else:
                                game_state = "TIMEOUT_FAIL"
                                sound_mgr.play_busted()
                            state_changed_this_frame = True

                        else:
                            # 檢查是否點擊考卷選項 A, B, C, D
                            for idx, opt_btn in enumerate(ui.btn_options):
                                if opt_btn.collidepoint(mouse_pos):
                                    exam_mgr.select_answer(idx)
                                    sound_mgr.play_click()
                                    opt_letter = ["A", "B", "C", "D"][idx]
                                    ui.trigger_feedback(f"✏️ 【已點選答案】第 {exam_mgr.current_idx + 1} 題選 [{opt_letter}]", color=(100, 210, 255), btn_name=f"OPT_{idx}")
                                    break
                else:
                    # 結算畫面按鈕點擊
                    if event.button == 1:
                        if ui.btn_back_title.collidepoint(mouse_pos):
                            sound_mgr.play_click()
                            game_state = "TITLE"
                            state_changed_this_frame = True
                        elif ui.btn_restart.collidepoint(mouse_pos):
                            start_new_game()
                            state_changed_this_frame = True

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    bio_signals.set_deep_breathing(False)

        # ---------------- 1.5 硬體級別空白鍵/C鍵輪詢 (僅在 PLAYING 且非本幀剛切換狀態時觸發) ----------------
        keys = pygame.key.get_pressed()
        space_down_now = bool(keys[pygame.K_SPACE])
        c_down_now = bool(keys[pygame.K_c] or keys[pygame.K_e])

        if game_state == "PLAYING" and not state_changed_this_frame:
            if space_down_now and not prev_space_down:
                bio_signals.toggle_emg()
                if bio_signals.emg_active:
                    ui.trigger_feedback("🖐️ 【空白鍵】已伸手拉開抽屜並打開小抄！", color=(241, 196, 15), btn_name="EMG")
                else:
                    ui.trigger_feedback("📥 【空白鍵】已將小抄收回書桌抽屜！", color=(100, 200, 255), btn_name="EMG")

            if c_down_now and not prev_c_down:
                bio_signals.toggle_emg()
                if bio_signals.emg_active:
                    ui.trigger_feedback("🖐️ 【C鍵】已伸手拉開抽屜並打開小抄！", color=(241, 196, 15), btn_name="EMG")
                else:
                    ui.trigger_feedback("📥 【C鍵】已將小抄收回書桌抽屜！", color=(100, 200, 255), btn_name="EMG")

        prev_space_down = space_down_now
        prev_c_down = c_down_now

        # ---------------- 2. 遊戲邏輯與 3D 滑鼠視角更新 ----------------
        if game_state == "PLAYING":
            ui.update_camera(mouse_pos, dt)
            exam_mgr.time_left -= dt
            if exam_mgr.time_left <= 0:
                exam_mgr.time_left = 0
                final_score = exam_mgr.calculate_score()
                if final_score >= 90:
                    game_state = "VICTORY"
                    sound_mgr.play_victory()
                else:
                    game_state = "TIMEOUT_FAIL"
                    sound_mgr.play_busted()

            bio_signals.update(dt, teacher_alert=teacher.buzzer_active)
            data_logger.update(exam_mgr.time_left, bio_signals, teacher)

            is_busted = teacher.update(dt, bio_signals)
            if is_busted:
                game_state = "BUSTED"

        elif game_state in ("BUSTED", "TIMEOUT_FAIL", "VICTORY"):
            if not csv_exported:
                data_logger.export_csv("neurocheat_session_data.csv")
                csv_exported = True

        # ---------------- 3. 畫面繪製渲染 ----------------
        if game_state == "TITLE":
            ui.render_title_screen(mouse_pos, bio=bio_signals, hw_bridge=hw_bridge)
        else:
            screen.fill(ui.COLOR_BG)
            # 渲染完整 3D 教室、旁邊其他學生、奶龍監考官、書桌考卷與抽屜小抄伸手動畫
            ui.render_3d_classroom_world(teacher, exam_mgr, bio_signals, mouse_pos)
            ui.render_header(exam_mgr, bio=bio_signals)
            ui.render_bio_dashboard(bio_signals, mouse_pos, hw_bridge=hw_bridge)

            if game_state == "BUSTED":
                ui.render_game_over(reason="BUSTED", score=exam_mgr.calculate_score(), records=data_logger.records)
            elif game_state == "TIMEOUT_FAIL":
                ui.render_game_over(reason="TIMEOUT_FAIL", score=exam_mgr.calculate_score(), records=data_logger.records)
            elif game_state == "VICTORY":
                ui.render_victory(score=exam_mgr.calculate_score(), records=data_logger.records)

        ui.render_feedback_toast()
        pygame.display.flip()

    hw_bridge.stop()
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
