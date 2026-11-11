"""
NeuroCheat 巡考老師 AI 與警報機制 (Teacher AI)
管理老師的行為狀態機、蜂鳴器預警、假動作機制、以及抓包作弊判定
"""

import random

class TeacherState:
    WRITING_BOARD = "WRITING_BOARD"      # 背對黑板寫字 (安全期)
    BUZZER_WARNING = "BUZZER_WARNING"    # 蜂鳴器響起預警
    FALSE_ALARM = "FALSE_ALARM"          # 假動作：只是回頭拿板擦或咳嗽
    TURNING_AROUND = "TURNING_AROUND"    # 轉身面向考場
    PATROLLING = "PATROLLING"            # 走下走道巡視 (危險期，嚴禁開小抄！)
    RETURNING = "RETURNING"              # 巡查完畢走回講台

class TeacherAI:
    def __init__(self, sound_manager=None):
        self.sound_manager = sound_manager
        self.state = TeacherState.WRITING_BOARD
        self.state_timer = 5.0  # 初始在黑板寫字 5 秒
        
        # 老師位置與動畫進度 (0.0: 講台黑板, 1.0: 走到玩家桌前)
        self.patrol_progress = 0.0
        self.facing_player = False
        
        # 警報旗標
        self.buzzer_active = False
        self.is_false_alarm = False
        
        # 疑心值 (0 ~ 100)
        self.suspicion = 10.0

    def update(self, dt, bio_signals):
        """
        更新老師狀態
        bio_signals: 玩家生理狀態 (EMG按鈕, ECG心率, EEG專注)
        回傳值: is_busted (True 表示作弊被抓包)
        """
        self.state_timer -= dt
        
        # 心率越高，老師的疑心值上升越快
        if bio_signals.ecg_bpm > 95:
            self.suspicion += dt * 8.0
        elif bio_signals.ecg_bpm < 75:
            self.suspicion = max(5.0, self.suspicion - dt * 4.0)
            
        self.suspicion = max(0.0, min(100.0, self.suspicion))

        # --- 狀態機邏輯 ---
        if self.state == TeacherState.WRITING_BOARD:
            self.facing_player = False
            self.patrol_progress = 0.0
            self.buzzer_active = False
            
            # 安全期結束，進入預警
            if self.state_timer <= 0:
                self.state = TeacherState.BUZZER_WARNING
                self.state_timer = random.uniform(1.5, 2.3)
                self.buzzer_active = True
                if self.sound_manager:
                    self.sound_manager.play_buzzer()
                
                # 疑心值越高，假動作機率越低 (真巡視機率越高)
                false_alarm_prob = max(0.20, 0.50 - (self.suspicion / 200.0))
                self.is_false_alarm = (random.random() < false_alarm_prob)

        elif self.state == TeacherState.BUZZER_WARNING:
            self.buzzer_active = True
            # 老師準備動作 (轉身前夕)
            if self.state_timer <= 0:
                self.buzzer_active = False
                if self.is_false_alarm:
                    # 假動作：老師假裝回頭，實則只是找粉筆
                    self.state = TeacherState.FALSE_ALARM
                    self.state_timer = random.uniform(1.2, 2.0)
                else:
                    # 真巡邏：老師猛然回頭
                    self.state = TeacherState.TURNING_AROUND
                    self.state_timer = 1.0

        elif self.state == TeacherState.FALSE_ALARM:
            # 假動作狀態：老師側身
            self.facing_player = False
            if self.state_timer <= 0:
                # 虛驚一場，回去寫黑板
                self.state = TeacherState.WRITING_BOARD
                # 依疑心值決定下一輪安全期長短 (4~8 秒)
                base_time = random.uniform(4.5, 8.0) - (self.suspicion * 0.03)
                self.state_timer = max(3.0, base_time)

        elif self.state == TeacherState.TURNING_AROUND:
            self.facing_player = True
            if self.state_timer <= 0:
                # 正式走下講台巡查
                self.state = TeacherState.PATROLLING
                # 心率過高時，老師走得更近、巡視更久！
                self.state_timer = 3.5 + (1.5 if bio_signals.ecg_bpm > 100 else 0.0)

        elif self.state == TeacherState.PATROLLING:
            self.facing_player = True
            # 移動動畫進度 (從 0.0 前進到 1.0)
            self.patrol_progress = min(1.0, self.patrol_progress + dt * 0.45)
            
            if self.state_timer <= 0:
                self.state = TeacherState.RETURNING
                self.state_timer = 2.0

        elif self.state == TeacherState.RETURNING:
            self.facing_player = False
            self.patrol_progress = max(0.0, self.patrol_progress - dt * 0.55)
            if self.state_timer <= 0:
                self.state = TeacherState.WRITING_BOARD
                base_time = random.uniform(5.0, 9.0) - (self.suspicion * 0.04)
                self.state_timer = max(3.5, base_time)

        # --- 作弊抓包判定 (Busted Check) ---
        # 1. 老師只要轉過頭來 (TURNING_AROUND 或 PATROLLING)，且玩家按住按鈕打開小抄 (emg_active) -> 抓包！
        if (self.state in [TeacherState.TURNING_AROUND, TeacherState.PATROLLING]) and bio_signals.emg_active:
            if self.sound_manager:
                self.sound_manager.play_busted()
            return True

        # 2. 老師走到玩家桌旁 (patrol_progress > 0.75)，如果小抄還沒完全收好 (emg_signal_level > 0.15) -> 抓包！
        if self.patrol_progress > 0.75 and bio_signals.emg_signal_level > 0.15:
            if self.sound_manager:
                self.sound_manager.play_busted()
            return True

        return False

    def get_status_description(self):
        """回傳目前奶龍監考官行為的描述，用於提示玩家"""
        if self.state == TeacherState.WRITING_BOARD:
            return "★ 奶龍正挺著大肚子在黑板寫板書（安全期！可伸手開抽屜看小抄！）", (46, 204, 113)
        elif self.state == TeacherState.BUZZER_WARNING:
            return "【逼逼！警戒！】蜂鳴器響起！奶龍的大肚子開始抖動了！（可能在憋笑假動作）", (241, 196, 15)
        elif self.state == TeacherState.FALSE_ALARM:
            return "● 奶龍只是轉身摸摸肚子抓癢，虛驚一場！", (160, 200, 120)
        elif self.state == TeacherState.TURNING_AROUND:
            return "【哈哈哈哈！】奶龍捧著大肚子轉身狂笑！眼神掃視全場！", (231, 76, 60)
        elif self.state == TeacherState.PATROLLING:
            return "【極度危險】奶龍挺著大肚子巡查走道中！！千萬別開抽屜看小抄！", (255, 60, 60)
        elif self.state == TeacherState.RETURNING:
            return "奶龍巡查完畢，搖頭晃腦走回講台...", (150, 180, 220)
        return "", (0, 0, 0)
