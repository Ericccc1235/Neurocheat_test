"""
NeuroCheat 考卷與題庫系統
包含 10 道符合電資學院與生醫工程主題的期末考題與小抄對應表
"""

class Question:
    def __init__(self, q_id, prompt, options, answer_idx, cheat_hint):
        self.q_id = q_id
        self.prompt = prompt
        self.options = options
        self.answer_idx = answer_idx  # 0: A, 1: B, 2: C, 3: D
        self.cheat_hint = cheat_hint
        self.user_answer = None

class ExamManager:
    def __init__(self):
        self.questions = self._load_questions()
        self.current_idx = 0
        self.exam_time = 120.0  # 考試時間 120 秒
        self.time_left = self.exam_time

    def _load_questions(self):
        qs = [
            Question(
                1,
                "Q1. 傅立葉轉換 (Fourier Transform) 主要將時域訊號轉換至哪一個領域？",
                ["A. 頻率域 (Frequency)", "B. 空間域 (Spatial)", "C. 復數拉氏域 (s-domain)", "D. 離散小波域 (Wavelet)"],
                0,
                "Q1 答案選 [A]。FT 本質是分解成正弦波頻率分量 (時域 -> 頻域)。"
            ),
            Question(
                2,
                "Q2. 在典型心電圖 (ECG) 中，代表心室去極化 (Ventricular Depolarization) 的波形為？",
                ["A. P 波", "B. QRS 複合波", "C. T 波", "D. U 波"],
                1,
                "Q2 答案選 [B]。P波是心房去極化，QRS是心室去極化，T波是心室再極化。"
            ),
            Question(
                3,
                "Q3. 腦電圖 (EEG) 中，受試者清醒放鬆、閉目養神時最顯著的腦波波段是？",
                ["A. Delta 波 (0.5-4 Hz)", "B. Theta 波 (4-8 Hz)", "C. Alpha 波 (8-13 Hz)", "D. Beta 波 (13-30 Hz)"],
                2,
                "Q3 答案選 [C]。Alpha 波 (8-13Hz) 枕葉最明顯，閉眼放鬆時最大。"
            ),
            Question(
                4,
                "Q4. 表面肌電圖 (sEMG) 量測時，偵測到的電位主要是什麼的總和？",
                ["A. 動作電位總和 (MUAP)", "B. 靜止膜電位 (RMP)", "C. 突觸後電位 (EPSP)", "D. 鈣離子震盪電位"],
                0,
                "Q4 答案選 [A]。EMG 量測肌肉運動單元動作電位 (MUAP) 空間與時間疊加。"
            ),
            Question(
                5,
                "Q5. 理想運算放大器 (Ideal Op-Amp) 的輸入阻抗與開迴路增益分別為？",
                ["A. 0 / 0", "B. 無窮大 / 無窮大", "C. 50 歐姆 / 1", "D. 1k 歐姆 / 100"],
                1,
                "Q5 答案選 [B]。黃金法則：輸入阻抗無窮大 (虛斷)，增益無窮大 (虛短)。"
            ),
            Question(
                6,
                "Q6. 根據奈奎斯特採樣定理 (Nyquist Sampling Theorem)，採樣頻率 fs 與訊號最高頻率 fmax 的關係為？",
                ["A. fs >= fmax", "B. fs >= 2 * fmax", "C. fs <= 0.5 * fmax", "D. fs == fmax / 2"],
                1,
                "Q6 答案選 [B]。避免頻譜混疊 (Aliasing)，取樣率必須至少大於最高頻率 2 倍！"
            ),
            Question(
                7,
                "Q7. 生醫訊號採集時，為消除人體從市電天線效應感應到的 60Hz 雜訊，常使用？",
                ["A. 低通濾波器", "B. 高通濾波器", "C. 60Hz 帶陷陷波器 (Notch Filter)", "D. 放大器開迴路"],
                2,
                "Q7 答案選 [C]。市電干擾是 60Hz 窄頻雜訊，必須用 Notch 陷波器濾除。"
            ),
            Question(
                8,
                "Q8. 為了防止心電訊號量測時電擊受試者，前端電路設計必須具備哪種安全特性？",
                ["A. 電氣隔離 (Galvanic Isolation)", "B. 直接接地到高壓端", "C. 移除所有防突波二極體", "D. 採用超大偏壓電流"],
                0,
                "Q8 答案選 [A]。生醫儀器標準 (如IEC 60601) 嚴格要求電氣隔離保護人體。"
            ),
            Question(
                9,
                "Q9. 在卷積神經網路 (CNN) 中，主要負責特徵降維與平移不變性的層是？",
                ["A. 全連接層 (Dense Layer)", "B. 池化層 (Pooling Layer)", "C. 激勵函數層 (ReLU)", "D. 批次標準化 (BN)"],
                1,
                "Q9 答案選 [B]。MaxPooling / AvgPooling 用於降取樣與降低維度。"
            ),
            Question(
                10,
                "Q10. 【期末求生題】這學期生醫工程期末專題的最終過關策略是？",
                ["A. 專心做好 NeuroCheat 軟硬體整合拿高分", "B. 考場直接開小抄被老師抓包", "C. 默默去教務處辦停修", "D. 跟老師說心率太高需要急救"],
                0,
                "Q10 答案選 [A]！好好完成專題拿 A+，絕對不要被抓包，順利過關！"
            )
        ]
        return qs

    def current_question(self):
        return self.questions[self.current_idx]

    def select_answer(self, option_idx):
        self.questions[self.current_idx].user_answer = option_idx

    def next_question(self):
        if self.current_idx < len(self.questions) - 1:
            self.current_idx += 1
            return True
        return False

    def prev_question(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            return True
        return False

    def jump_to(self, idx):
        if 0 <= idx < len(self.questions):
            self.current_idx = idx

    def calculate_score(self):
        correct = 0
        for q in self.questions:
            if q.user_answer is not None and q.user_answer == q.answer_idx:
                correct += 1
        return correct * 10  # 10 題，每題 10 分，滿分 100

    def answered_count(self):
        return sum(1 for q in self.questions if q.user_answer is not None)

    def is_passed(self):
        return self.calculate_score() >= 90
