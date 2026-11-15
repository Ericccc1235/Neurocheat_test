"""
exam.py - 生醫電子期末考題庫、兩頁式公式小抄與鄰座偷看邏輯
============================================================
改良重點：
  1. 擴充為 18 題電機/生醫工程真實考題，每局隨機抽 10 題並打亂 ABCD 選項，避免背答案。
  2. 小抄改為「關鍵公式 / 關鍵字提醒」（無直接劇透選項），並分為第 1 頁 (Q1~Q5) 與第 2 頁 (Q6~Q10)，
     需要按 Tab 或 BrainLink Fp1 雙眨眼翻頁才能查看後半段提示。
  3. 整合鄰座偷看（左邊阿明 vs 右邊學霸小華）與誠實作答統計。
"""

import random


# (題幹, [正確選項(索引0), 干擾1, 干擾2, 干擾3], 公式/關鍵字小抄提示)
QUESTION_BANK = [
    (
        "儀表放大器 AD620 的差動電壓增益公式為何？",
        ["G = 1 + 49.4kΩ / Rg", "G = 49.4kΩ / Rg", "G = 1 + Rg / 49.4kΩ", "G = 2 * Rf / R1"],
        "AD620: G = 1 + 49.4k / Rg",
    ),
    (
        "實驗二 ECG 類比電路加入 Fliege Notch 濾波器主要是為了濾除哪個頻率？",
        ["60 Hz 市電干擾", "0.1 Hz 呼吸漂移", "500 Hz 肌電雜訊", "10 Hz Alpha 腦波"],
        "台灣市電頻率: 60 Hz Notch",
    ),
    (
        "表面肌電訊號 (sEMG) 主能量為 20~500 Hz，若以 200 Hz 取樣會發生什麼現象？",
        ["頻譜混疊 (Aliasing)", "量子化雜訊歸零", "共模拒斥比上升", "直流準位自動置中"],
        "Nyquist: fs >= 2*fmax -> 不足會混疊",
    ),
    (
        "在國際 10-20 腦波系統中，BrainLink 額頭單極點感測器通常量測哪個位置？",
        ["Fp1 (左前額葉)", "O1 (枕葉視覺區)", "C3 (中央運動區)", "T4 (右顳葉聽覺區)"],
        "前額單通道: Fp1 (耳夾為參考/地)",
    ),
    (
        "大腦處於「放鬆但不困倦、閉眼冥想」狀態時，哪個頻段的 EEG 能量最顯著？",
        ["Alpha 波 (8 ~ 13 Hz)", "Delta 波 (0.5 ~ 4 Hz)", "高 Beta 波 (20 ~ 30 Hz)", "Gamma 波 (35 ~ 80 Hz)"],
        "Delta深睡 / Theta困 / Alpha放鬆 / Beta專注",
    ),
    (
        "額頭 Fp1 通道上的「眨眼偽訊 (Blink Artifact)」在訊號上主要呈現何種特徵？",
        ["低頻大振幅瞬態突波", "高頻 60Hz 正弦共振", "均勻白雜訊平線", "純直流準位永久偏移"],
        "眼電眨眼 EOG -> 低頻大幅尖峰脈衝",
    ),
    (
        "Arduino UNO 程式碼寫 `analogRead(A0) >> 2`，其運算目的為何？",
        ["將 10-bit 降為 8-bit 單一 Byte", "將取樣率提升 4 倍", "進行二階低通濾波", "把電壓放大 4 倍"],
        "10bit(0~1023) 右移2bit -> 8bit(0~255)",
    ),
    (
        "為什麼即時生理遊戲中的濾波器必須採用「因果濾波 (Causal, 如 sosfilt)」？",
        ["不能使用未來尚未發生的取樣點", "因為因果濾波線性相位絕對完美", "可完全省去電源供應", "計算量比簡易平均小 1000 倍"],
        "即時線上解碼禁用 filtfilt/未來視窗",
    ),
    (
        "RC 高通濾波器若使用 R=1MΩ 與 C=10µF，為何在動作干擾後恢復極慢？",
        ["時間常數 τ = RC 高達 10 秒", "電容會燒毀變成斷路", "截止頻率變為 15.9 kHz", "會自動轉換成陷波濾波器"],
        "τ = R*C = 1M*10u = 10s ; fc = 1/(2πRC)",
    ),
    (
        "前級放大器追求極高 CMRR (共模拒斥比)，主要是為了抑制哪類雜訊？",
        ["人體同時感應到的 60Hz 共模雜訊", "電極線材的直流電阻", "Arduino PWM 的數位脈衝", "螢幕背光的紅外線"],
        "CMRR = 20log(Ad/Acm) 抑制雙臂共模干擾",
    ),
    (
        "擷取 sEMG 握拳力道大小時，對 20~500Hz 濾波訊號常做什麼處理？",
        ["全波整流加上低通濾波取包絡線", "直接對原始正負波做長期平均", "濾除所有 100 Hz 以下訊號後微分", "只保留 0.1 Hz 以下成分"],
        "EMG包絡線: |x|整流 -> LPF平滑",
    ),
    (
        "ECG 訊號進入 Arduino ADC 前加入 2.5V 位準平移電路 (Level Shifter) 是為了？",
        ["讓雙極性交流波形落在 0~5V 單極輸入內", "直接替代藍牙通訊調變", "提供 2.5V 給電極片加熱", "強制將心率鎖定在 75 BPM"],
        "UNO ADC僅吃 0~5V -> 需加 Vref ≈ 2.5V 偏壓",
    ),
    (
        "生醫感測電路要求受試者測量端使用電池供電與藍牙無線傳輸，最核心的理由是？",
        ["電氣隔離確保人體防觸電與降低市電漏電", "電池電壓比市電更容易產生 60Hz", "藍牙頻寬比有線 USB 還大", "法律禁止電極使用任何導線"],
        "醫療安全: 電氣隔離 (電池 + 無線藍牙)",
    ),
    (
        "標準 ECG 監測常採 0.5~40 Hz 帶通濾波，這個範圍主要保留並突出哪個特徵？",
        ["QRS 波群主能量並抑制基線漂移", "超過 200 Hz 的心室微電位", "純直流皮膚電阻變化", "僅保留 P 波並刪除 R 波"],
        "ECG 主頻段 0.5-40 Hz -> 抑漂移與高頻雜訊",
    ),
    (
        "在 EEG 少樣本分類器中採用 Shrinkage LDA (收縮線性判別分析) 的主要好處為？",
        ["正則化共變異數矩陣避免過擬合", "將線性分類變成 100 層深度卷積", "不需標記類別即可自動發電", "完全不需要對特徵做標準化"],
        "Shrinkage: (1-λ)Σ + λμI 高維穩健不易過擬合",
    ),
    (
        "當雙手緊抓或總放大倍率過大導致波形頂端變平時，這在電路稱為？",
        ["軌到軌截波飽和 (Rail Saturation)", "完美正弦波調變", "隨機白雜訊共振", "帶通增益增強"],
        "振幅超出 0~5V -> ADC 0 或 1023 飽和截波",
    ),
    (
        "認知心理學「Stroop 效應測試（字義與字色衝突）」誘發的大腦特徵屬於？",
        ["高認知負荷與注意力衝突狀態", "無意識深層快速動眼睡眠", "純粹小腦肌肉疲勞反射", "周邊運動神經完全麻痺"],
        "Stroop 衝突 -> 前額認知負荷/高壓狀態",
    ),
    (
        "深呼吸慢吐氣能在考場上幫助降心率與鎮定，主要透過活化哪條神經系統？",
        ["副交感神經 / 迷走神經 (Vagus Nerve)", "交感神經戰鬥逃跑反射", "脊髓痛覺傳導束", "三叉神經咀嚼運動支"],
        "慢深呼吸 -> 迷走/副交感活化 -> HR下降",
    ),
]


class Question:
    def __init__(self, q_id, prompt, options, correct_idx, cheat_hint):
        self.id = q_id
        self.prompt = prompt
        self.options = options
        self.correct_idx = correct_idx
        self.cheat_hint = cheat_hint


DIFFICULTY_EXAM_TIME = {
    "EASY": 115.0,
    "NORMAL": 95.0,
    "HARD": 80.0,
}


class ExamManager:
    def __init__(self, difficulty="NORMAL"):
        self.difficulty = difficulty
        self.questions = []
        self.current_q_idx = 0
        self.user_answers = []
        self.used_cheat_flags = []
        self.honest_correct_count = 0
        self.cheated_count = 0
        self.honest_streak = 0

        self.exam_time = DIFFICULTY_EXAM_TIME.get(difficulty, 95.0)
        self.time_remaining = self.exam_time
        self.elapsed = 0.0
        self.finished = False

        self.neighbor_guesses = {"left": [], "right": []}
        self.reset(difficulty)

    def reset(self, difficulty=None):
        if difficulty is not None:
            self.difficulty = difficulty
        self.exam_time = DIFFICULTY_EXAM_TIME.get(self.difficulty, 95.0)
        sampled = random.sample(QUESTION_BANK, 10)
        self.questions = []
        for idx, (prompt, opts_orig, hint) in enumerate(sampled, start=1):
            correct_text = opts_orig[0]
            shuffled = list(opts_orig)
            random.shuffle(shuffled)
            correct_idx = shuffled.index(correct_text)
            self.questions.append(Question(idx, prompt, shuffled, correct_idx, hint))

        self.current_q_idx = 0
        self.user_answers = [None] * len(self.questions)
        self.used_cheat_flags = [False] * len(self.questions)
        self.honest_correct_count = 0
        self.cheated_count = 0
        self.honest_streak = 0
        self.time_remaining = self.exam_time
        self.elapsed = 0.0
        self.finished = False

        # 為左右兩位同學預先產生本局的作答草稿 (左邊阿明 42% 對；右邊小華學霸 78% 對)
        self.neighbor_guesses = {"left": [], "right": []}
        right_acc = 0.85 if self.difficulty == "EASY" else (0.78 if self.difficulty == "NORMAL" else 0.72)
        for q in self.questions:
            wrong_choices = [i for i in range(4) if i != q.correct_idx]
            if random.random() < 0.42:
                left_ans = q.correct_idx
            else:
                left_ans = random.choice(wrong_choices)
            if random.random() < right_acc:
                right_ans = q.correct_idx
            else:
                right_ans = random.choice(wrong_choices)
            self.neighbor_guesses["left"].append(chr(65 + left_ans))
            self.neighbor_guesses["right"].append(chr(65 + right_ans))

    def update(self, dt):
        if not self.finished:
            self.elapsed += dt
            self.time_remaining = max(0.0, self.time_remaining - dt)
            if self.time_remaining <= 0.0:
                self.finished = True

    def is_neighbor_ready(self, side, q_idx=None):
        """同學會隨時間推進寫考卷：開局寫到 Q3，之後每 5.5 秒多寫 1 題。"""
        if self.difficulty == "EASY":
            return True
        idx = self.current_q_idx if q_idx is None else q_idx
        pace = 5.0 if side == "right" else 4.2
        solved_limit = 3 + int(self.elapsed // pace)
        return idx < solved_limit

    def next_question(self):
        self.current_q_idx = (self.current_q_idx + 1) % len(self.questions)

    def prev_question(self):
        self.current_q_idx = (self.current_q_idx - 1) % len(self.questions)

    def select_option(self, opt_idx, cheated=False):
        """記錄作答。回傳 (is_correct, honest_bonus_triggered)。"""
        if not (0 <= opt_idx < 4):
            return False, False

        q = self.questions[self.current_q_idx]
        first_time = self.user_answers[self.current_q_idx] is None
        self.user_answers[self.current_q_idx] = opt_idx
        if cheated:
            self.used_cheat_flags[self.current_q_idx] = True

        is_correct = opt_idx == q.correct_idx
        honest_bonus = False

        if first_time:
            if cheated or self.used_cheat_flags[self.current_q_idx]:
                self.cheated_count += 1
                self.honest_streak = 0
            elif is_correct:
                self.honest_correct_count += 1
                self.honest_streak += 1
                honest_bonus = True
            else:
                self.honest_streak = 0

        return is_correct, honest_bonus

    def mark_cheated_current(self):
        self.used_cheat_flags[self.current_q_idx] = True

    def get_current_question(self):
        return self.questions[self.current_q_idx]

    def get_cheat_page_lines(self, page_idx=0):
        """
        回傳兩頁公式小抄文字清單：
          page 0: Q1 ~ Q5 重點公式提示
          page 1: Q6 ~ Q10 重點公式提示
        """
        start = 0 if page_idx == 0 else 5
        end = min(len(self.questions), start + 5)
        lines = []
        for i in range(start, end):
            lines.append(f"[{i + 1:02d}] {self.questions[i].cheat_hint}")
        return lines

    def get_neighbor_guess(self, side, q_idx=None):
        """取得鄰座 (left=阿明 / right=小華) 考卷上看到的字母與標籤。"""
        idx = self.current_q_idx if q_idx is None else q_idx
        if side not in self.neighbor_guesses or not (0 <= idx < len(self.questions)):
            return "?", ""
        letter = self.neighbor_guesses[side][idx]
        label = "阿明草稿" if side == "left" else "小華筆記"
        return letter, label

    def calculate_score(self):
        score = 0
        for q, ans in zip(self.questions, self.user_answers):
            if ans == q.correct_idx:
                score += 10
        return score

    def is_all_answered(self):
        return all(ans is not None for ans in self.user_answers)

    def get_progress_str(self):
        answered = sum(1 for a in self.user_answers if a is not None)
        return f"{answered}/{len(self.questions)}"
