"""
teacher.py - 監考老師 AI 狀態機、走道巡邏位置與心理博弈系統
==============================================================
升級重點：
  1. 支援三階難度設定 (EASY / NORMAL / HARD)，預設 NORMAL 更具壓迫感。
  2. 新增 3D 走道移動 (pos_z 從講台 5.05m 逼近第一排走道 1.55m) 與腳步聲提示；
     老師走近桌前時，連微開抽屜縫隙都會被直接識破！
  3. 假動作複合陷阱 (DOUBLE_FAKE)：假警報結束後高機率無縫銜接 SILENT_PEEK 突襲回頭。
"""

from enum import Enum
import math
import random


class TeacherState(Enum):
    WRITING_BOARD = 0    # 背對寫板書（安全）
    BUZZER_WARNING = 1   # 蜂鳴器響起，準備回頭
    FALSE_ALARM = 2      # 假動作（可能直接誘騙銜接 SILENT_PEEK）
    SILENT_PEEK = 3      # 無聲突襲前兆（輕咳，無蜂鳴器）
    TURNING_AROUND = 4   # 轉頭過程中
    PATROLLING = 5       # 正面巡視全班／走下走道（極危險）
    RETURNING = 6        # 走回講台並轉回黑板


DIFFICULTY_CONFIGS = {
    "EASY": {
        "label": "輕鬆練習",
        "write_range": (3.8, 6.2),
        "patrol_range": (2.3, 3.6),
        "silent_prob": 0.16,
        "feint_chain_prob": 0.12,
        "aisle_walk_prob": 0.25,
        "min_aisle_z": 2.95,
        "suspicion_mult": 0.78,
    },
    "NORMAL": {
        "label": "標準期末考",
        "write_range": (2.3, 4.2),
        "patrol_range": (2.8, 4.5),
        "silent_prob": 0.28,
        "feint_chain_prob": 0.36,
        "aisle_walk_prob": 0.52,
        "min_aisle_z": 1.68,
        "suspicion_mult": 1.05,
    },
    "HARD": {
        "label": "地獄大刀教授",
        "write_range": (1.6, 3.0),
        "patrol_range": (3.2, 5.2),
        "silent_prob": 0.36,
        "feint_chain_prob": 0.50,
        "aisle_walk_prob": 0.72,
        "min_aisle_z": 1.32,
        "suspicion_mult": 1.32,
    },
}


class TeacherAI:
    """動態監考奶龍老師 AI，結合 3D 走道巡邏與生理訊號監控。"""

    PODIUM_Z = 5.05

    def __init__(self, difficulty="NORMAL"):
        self.difficulty = difficulty if difficulty in DIFFICULTY_CONFIGS else "NORMAL"
        self.state = TeacherState.WRITING_BOARD
        self.state_timer = 3.5
        self.head_angle = 0.0         # 0°=背對面向黑板, 180°=正面面對學生
        self.suspicion = 0.0          # 0.0 ~ 100.0 %
        self.busted = False
        self.busted_reason = ""

        # 3D 教室空間座標與走動動畫
        self.pos_x = 0.0
        self.pos_z = self.PODIUM_Z
        self.target_z = self.PODIUM_Z
        self.walk_phase = 0.0
        self._step_accum = 0.0

        self.status_banner = "老師正在寫黑板 (安全)"
        self.banner_color = (80, 220, 120)

        self.total_warnings = 0
        self.false_alarms_count = 0
        self.silent_peeks_count = 0
        self.close_calls = 0
        self.aisle_walks_count = 0

        self._risky_before_patrol = False
        self._pending_hw_cmd = None
        self._pending_sfx = None

        self.next_distraction_in = 22.0
        self.distracted_timer = 0.0
        self.distraction_banner = ""

        self.rush_mode = False
        self.reset(self.difficulty)

    def _cfg(self):
        return DIFFICULTY_CONFIGS.get(self.difficulty, DIFFICULTY_CONFIGS["NORMAL"])

    def reset(self, difficulty=None):
        if difficulty in DIFFICULTY_CONFIGS:
            self.difficulty = difficulty
        cfg = self._cfg()
        self.state = TeacherState.WRITING_BOARD
        self.state_timer = random.uniform(*cfg["write_range"])
        self.head_angle = 0.0
        self.suspicion = 0.0
        self.busted = False
        self.busted_reason = ""

        self.pos_x = 0.0
        self.pos_z = self.PODIUM_Z
        self.target_z = self.PODIUM_Z
        self.walk_phase = 0.0
        self._step_accum = 0.0

        self.status_banner = f"老師正在寫黑板 [{cfg['label']}]"
        self.banner_color = (80, 220, 120)

        self.total_warnings = 0
        self.false_alarms_count = 0
        self.silent_peeks_count = 0
        self.close_calls = 0
        self.aisle_walks_count = 0
        self._risky_before_patrol = False
        self._pending_hw_cmd = None
        self._pending_sfx = None

        self.next_distraction_in = random.uniform(18.0, 28.0)
        self.distracted_timer = 0.0
        self.distraction_banner = ""
        self.rush_mode = False

    def consume_hw_command(self):
        cmd = self._pending_hw_cmd
        self._pending_hw_cmd = None
        return cmd

    def consume_sfx(self):
        sfx = self._pending_sfx
        self._pending_sfx = None
        return sfx

    def honest_relief(self, amount=6.0):
        """靠自己不開小抄答對題目時，老師信任感微升（降低懷疑值）。"""
        self.suspicion = max(0.0, self.suspicion - amount)

    def trigger_slam_alert(self):
        """EMG 肌肉抽筋導致抽屜「啪」一聲關上：增加懷疑並立即驚動老師。"""
        self.suspicion = min(98.0, self.suspicion + 26.0)
        if self.state == TeacherState.WRITING_BOARD:
            self.state_timer = min(self.state_timer, 0.55)
            self.status_banner = "抽屜撞擊巨響！老師立刻停筆要回頭了！"
            self.banner_color = (255, 115, 50)

    def is_facing_player(self):
        return self.head_angle >= 115.0

    def is_close_aisle(self):
        return self.pos_z <= 2.65

    def get_alert_level(self):
        base = {
            TeacherState.WRITING_BOARD: 0.08,
            TeacherState.FALSE_ALARM: 0.34,
            TeacherState.RETURNING: 0.30,
            TeacherState.SILENT_PEEK: 0.72,
            TeacherState.BUZZER_WARNING: 0.65,
            TeacherState.TURNING_AROUND: 0.86,
            TeacherState.PATROLLING: 1.0,
        }.get(self.state, 0.2)
        if self.pos_z < 3.5:
            base = max(base, 0.85)
        if self.distracted_timer > 0.0:
            base *= 0.45
        return min(1.0, max(base, self.suspicion / 100.0))

    def _trigger_busted(self, reason):
        if not self.busted:
            self.busted = True
            self.busted_reason = reason
            self._pending_hw_cmd = "BUZZER_BUSTED"
            self.status_banner = "抓包！奶娃老師站在你面前嘲笑！"
            self.banner_color = (255, 50, 50)

    def _update_aisle_movement(self, dt):
        """平滑移動老師在走道上的 3D 位置並觸發腳步聲。"""
        diff = self.target_z - self.pos_z
        if abs(diff) > 0.04:
            walk_speed = 1.65 if self.state == TeacherState.PATROLLING else 2.15
            step = math.copysign(min(abs(diff), walk_speed * dt), diff)
            self.pos_z += step
            self.walk_phase += abs(step) * 4.5
            self.pos_x = math.sin(self.walk_phase) * 0.07
            self._step_accum += dt
            if self._step_accum >= 0.36:
                self._step_accum = 0.0
                if self._pending_sfx is None:
                    self._pending_sfx = "footstep"
        else:
            self.pos_x *= max(0.0, 1.0 - 8.0 * dt)
            self._step_accum = 0.25

    def update(
        self,
        dt,
        bio_signals,
        camera_yaw=0.0,
        peeking_side=None,
        exam_time_remaining=95.0,
    ):
        """更新老師狀態機、3D 走道巡邏位置與懷疑值。"""
        if self.busted:
            return False, False, False

        dt = max(0.001, min(0.1, dt))
        cfg = self._cfg()
        self.rush_mode = exam_time_remaining <= 28.0

        entered_warning = False
        entered_patrol = False
        triggered_false = False

        # 更新教室干擾事件 (較罕見且縮短時間，避免過度降低難度)
        if self.distracted_timer > 0.0:
            self.distracted_timer = max(0.0, self.distracted_timer - dt)
            if self.distracted_timer <= 0.0:
                self.distraction_banner = ""
        else:
            self.next_distraction_in -= dt
            if self.next_distraction_in <= 0.0:
                self.next_distraction_in = random.uniform(24.0, 36.0)
                if self.state in (TeacherState.PATROLLING, TeacherState.WRITING_BOARD) and not self.is_close_aisle():
                    self.distracted_timer = 1.9
                    self.distraction_banner = random.choice([
                        "前排同學橡皮擦掉地上！老師目光暫移 1.9 秒",
                        "窗外剛好飛過一隻鳥，老師分神看了一眼",
                    ])
                    self._pending_sfx = "distraction"

        drawer_ratio = bio_signals.get_drawer_open_ratio()
        peeking_drawer = drawer_ratio >= 0.22
        full_open_drawer = drawer_ratio >= 0.56
        looking_neighbor = (peeking_side is not None) or (abs(camera_yaw) >= 0.34)

        ecg_valid = bio_signals.ecg_quality != "bad"
        bpm_delta = bio_signals.bpm_delta if ecg_valid else 0.0
        ecg_high = ecg_valid and (bpm_delta >= 8.0)
        deep_calm = bio_signals.deep_breath_active

        if self.state in (TeacherState.BUZZER_WARNING, TeacherState.SILENT_PEEK, TeacherState.TURNING_AROUND):
            if peeking_drawer or looking_neighbor:
                self._risky_before_patrol = True

        self.state_timer -= dt
        rush_mult = (1.28 if self.rush_mode else 1.0) * cfg["suspicion_mult"]

        # ------------------------------------------------------------------
        # 狀態機轉換
        # ------------------------------------------------------------------
        if self.state == TeacherState.WRITING_BOARD:
            self.head_angle = max(0.0, self.head_angle - 240.0 * dt)
            self.target_z = self.PODIUM_Z
            if self.state_timer <= 0.0:
                peek_prob = cfg["silent_prob"] + (0.08 if self.rush_mode else 0.0)
                self._risky_before_patrol = False
                if random.random() < peek_prob:
                    self.state = TeacherState.SILENT_PEEK
                    self.state_timer = random.uniform(0.65, 1.05)
                    self.silent_peeks_count += 1
                    self._pending_sfx = "cough"
                    self.status_banner = "老師突然停筆輕咳！無蜂鳴器突襲回頭！"
                    self.banner_color = (255, 165, 55)
                else:
                    self.state = TeacherState.BUZZER_WARNING
                    self.state_timer = random.uniform(0.95, 1.55)
                    self.total_warnings += 1
                    entered_warning = True
                    self._pending_hw_cmd = "BUZZER_WARN"
                    self.status_banner = "警告蜂鳴器響起！老師準備轉身！"
                    self.banner_color = (255, 195, 50)

        elif self.state == TeacherState.BUZZER_WARNING:
            self.head_angle = min(28.0, self.head_angle + 30.0 * dt)
            if self.state_timer <= 0.0:
                false_prob = 0.24 if self.suspicion > 45.0 else 0.34
                if random.random() < false_prob:
                    self.state = TeacherState.FALSE_ALARM
                    self.state_timer = random.uniform(0.75, 1.25)
                    self.false_alarms_count += 1
                    triggered_false = True
                    self.status_banner = "假動作！老師放下粉筆沒轉過來..."
                    self.banner_color = (120, 200, 255)
                else:
                    self.state = TeacherState.TURNING_AROUND
                    self.state_timer = 0.52
                    self.status_banner = "快收手！老師轉過身來了！"
                    self.banner_color = (255, 105, 45)

        elif self.state == TeacherState.SILENT_PEEK:
            self.head_angle = min(44.0, self.head_angle + 62.0 * dt)
            if self.state_timer <= 0.0:
                self.state = TeacherState.TURNING_AROUND
                self.state_timer = 0.45
                self.status_banner = "無聲突襲！老師猛然回頭盯着你！"
                self.banner_color = (255, 80, 40)

        elif self.state == TeacherState.FALSE_ALARM:
            self.head_angle = max(0.0, self.head_angle - 65.0 * dt)
            if self.state_timer <= 0.0:
                # 假動作後可能接續無聲回頭陷阱！
                chain_prob = cfg["feint_chain_prob"] + (0.10 if self.suspicion > 40.0 else 0.0)
                if random.random() < chain_prob:
                    self.state = TeacherState.SILENT_PEEK
                    self.state_timer = random.uniform(0.55, 0.85)
                    self.silent_peeks_count += 1
                    self._pending_sfx = "cough"
                    self.status_banner = "回馬槍陷阱！老師假裝寫字又突然回頭！"
                    self.banner_color = (255, 140, 45)
                else:
                    w_min, w_max = cfg["write_range"]
                    scale = 0.72 if self.rush_mode else 1.0
                    self.state = TeacherState.WRITING_BOARD
                    self.state_timer = random.uniform(w_min, w_max) * scale
                    self.status_banner = "老師繼續寫板書 (暫時安全)"
                    self.banner_color = (80, 220, 120)

        elif self.state == TeacherState.TURNING_AROUND:
            self.head_angle = min(180.0, self.head_angle + 320.0 * dt)
            if full_open_drawer:
                self.suspicion = min(100.0, self.suspicion + 42.0 * rush_mult * dt)
            elif peeking_drawer:
                self.suspicion = min(100.0, self.suspicion + 16.0 * rush_mult * dt)

            if self.head_angle >= 175.0 or self.state_timer <= 0.0:
                self.head_angle = 180.0
                self.state = TeacherState.PATROLLING
                p_min, p_max = cfg["patrol_range"]
                self.state_timer = random.uniform(p_min, p_max) + (0.8 if self.suspicion > 50.0 else 0.0)
                entered_patrol = True

                # 決定這次是否走下講台進入走道逼近你
                walk_prob = cfg["aisle_walk_prob"] + (0.25 if (self.suspicion >= 28.0 or self.rush_mode) else 0.0)
                if random.random() < walk_prob:
                    self.target_z = random.uniform(cfg["min_aisle_z"], 3.05)
                    self.aisle_walks_count += 1
                    self.status_banner = "危險！奶娃老師走下講台逼近走道巡視！！"
                else:
                    self.target_z = random.uniform(3.95, 4.75)
                    self.status_banner = "危險！老師正睜大雙眼盯著全班！"

                if self._risky_before_patrol and not peeking_drawer and not looking_neighbor:
                    self.close_calls += 1
                    self._risky_before_patrol = False
                self.banner_color = (255, 60, 60)

        elif self.state == TeacherState.PATROLLING:
            self.head_angle = 180.0
            if self.distracted_timer > 0.0:
                self.state_timer -= 0.7 * dt
                self.status_banner = "老師暫時被突發聲響吸引目光！"
                self.banner_color = (120, 210, 255)
            else:
                close_now = self.is_close_aisle()

                # 1. 抽屜全開直接抓包；老師走近桌前時連微縫都立刻抓包！
                if full_open_drawer:
                    self._trigger_busted("巡堂時抽屜整個大開看小抄，被老師當場逮捕！")
                    return entered_warning, entered_patrol, triggered_false

                if peeking_drawer and close_now:
                    self._trigger_busted("老師已經走到前面走道！微開抽屜縫隙被近距離抓包！")
                    return entered_warning, entered_patrol, triggered_false

                # 2. 講台遠距離時微縫偷窺給極短 (~0.8s) 逃生反應
                if peeking_drawer:
                    self.suspicion += 105.0 * rush_mult * dt
                    self.status_banner = "老師朝你這邊看過來！立刻放開抽屜！"
                    self.banner_color = (255, 65, 45)
                    if self.suspicion >= 100.0:
                        self._trigger_busted("巡堂還不關抽屜，被老師走到桌前當場逮住！")
                        return entered_warning, entered_patrol, triggered_false

                # 3. 轉頭偷看鄰座 (走近走道時極度危險)
                if looking_neighbor:
                    mult = 1.85 if close_now else 1.0
                    self.suspicion += 68.0 * mult * rush_mult * dt
                    self.status_banner = "老師正盯著走道！不要再往隔壁瞟了！"
                    self.banner_color = (255, 95, 50)
                    if self.suspicion >= 100.0:
                        self._trigger_busted("當著巡堂老師的面一直轉頭抄隔壁考卷，被當場記過！")
                        return entered_warning, entered_patrol, triggered_false

                # 4. ECG 心率相對飆高
                if ecg_high:
                    excess = max(1.0, (bpm_delta - 8.0) / 12.0)
                    self.suspicion += (14.0 + 16.0 * excess) * rush_mult * dt
                    if not peeking_drawer and not looking_neighbor:
                        self.status_banner = f"心率狂飆 (+{bpm_delta:.0f} BPM) 引起注意！按住 R 深呼吸！"
                        self.banner_color = (255, 155, 60)
                    if self.suspicion >= 100.0:
                        self._trigger_busted("心虛喘氣與心率異常飆高，被老師走來搜查抓包！")
                        return entered_warning, entered_patrol, triggered_false
                elif deep_calm and not peeking_drawer and not looking_neighbor:
                    self.suspicion = max(0.0, self.suspicion - 10.5 * dt)
                    self.state_timer -= 0.35 * dt

            if self.state_timer <= 0.0:
                self.state = TeacherState.RETURNING
                self.target_z = self.PODIUM_Z
                self.state_timer = 0.90 if self.pos_z < 3.6 else 0.55
                self.status_banner = "老師正走回講台轉回黑板..."
                self.banner_color = (140, 225, 175)

        elif self.state == TeacherState.RETURNING:
            self.target_z = self.PODIUM_Z
            # 走回講台的後半段才完全背過身，剛起步轉回去時依然不能急著開抽屜
            if self.pos_z > 3.85:
                self.head_angle = max(0.0, self.head_angle - 280.0 * dt)
            if self.head_angle <= 5.0 and abs(self.pos_z - self.PODIUM_Z) < 0.15:
                self.head_angle = 0.0
                self.pos_z = self.PODIUM_Z
                self.state = TeacherState.WRITING_BOARD
                w_min, w_max = cfg["write_range"]
                scale = 0.72 if self.rush_mode else 1.0
                self.state_timer = random.uniform(w_min, w_max) * scale
                self.status_banner = "老師回到黑板繼續板書 (暫時安全)"
                self.banner_color = (80, 220, 120)

        self._update_aisle_movement(dt)

        # 通用懷疑值冷卻（被動冷卻大幅減慢，必須靠深呼吸或誠實答對降低）
        if not peeking_drawer and not looking_neighbor and not ecg_high:
            cool_rate = 10.5 if deep_calm else (2.1 if self.state == TeacherState.WRITING_BOARD else 0.6)
            self.suspicion = max(0.0, self.suspicion - cool_rate * dt)

        return entered_warning, entered_patrol, triggered_false
