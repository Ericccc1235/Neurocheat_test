"""
sound_generator.py - 程式即時合成音效系統
=============================================
免去外部 MP3/WAV 相依，透過 NumPy 即時合成所有遊戲音效，
並在無音效裝置環境下自動安全降級為靜音模式。
"""

import numpy as np
import pygame


class SoundManager:
    """合成並播放遊戲中的所有警戒、作弊與教室環境音效。"""

    def __init__(self, sample_rate=22050):
        self.sr = sample_rate
        self.enabled = False
        self.sounds = {}

        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=self.sr, size=-16, channels=1, buffer=512)
            self._build_all_sounds()
            self.enabled = True
        except Exception:
            self.enabled = False

    def _to_sound(self, wave):
        wave = np.clip(wave, -1.0, 1.0)
        pcm = (wave * 32767.0).astype(np.int16)
        return pygame.sndarray.make_sound(pcm)

    def _tone(self, freq, dur, vol=0.4, attack=0.01, decay=0.05):
        n = max(1, int(self.sr * dur))
        t = np.linspace(0.0, dur, n, endpoint=False)
        sig = np.sin(2.0 * np.pi * freq * t)
        env = np.ones(n, dtype=np.float64)
        a_n = min(n, max(1, int(self.sr * attack)))
        d_n = min(n, max(1, int(self.sr * decay)))
        env[:a_n] = np.linspace(0.0, 1.0, a_n)
        env[-d_n:] = np.linspace(1.0, 0.0, d_n)
        return sig * env * vol

    def _noise(self, dur, vol=0.25):
        n = max(1, int(self.sr * dur))
        rng = np.random.default_rng(42)
        raw = rng.uniform(-1.0, 1.0, n)
        # 簡單移動平均柔化刺耳雜訊
        kernel = np.ones(6, dtype=np.float64) / 6.0
        smooth = np.convolve(raw, kernel, mode="same")
        env = np.exp(-np.linspace(0.0, 4.5, n))
        return smooth * env * vol

    def _build_all_sounds(self):
        # 1. 硬體/講台蜂鳴器警告 (兩段高頻方波逼逼聲)
        t_beep = np.linspace(0.0, 0.12, int(self.sr * 0.12), endpoint=False)
        sq = np.sign(np.sin(2.0 * np.pi * 1750.0 * t_beep)) * 0.25
        sq[-200:] *= np.linspace(1.0, 0.0, 200)
        gap = np.zeros(int(self.sr * 0.06))
        self.sounds["buzzer"] = self._to_sound(np.concatenate([sq, gap, sq]))

        # 2. 低沉緊張心跳聲 (lub-dub)
        lub = self._tone(78.0, 0.09, vol=0.55, attack=0.008, decay=0.06)
        dub = self._tone(64.0, 0.11, vol=0.40, attack=0.008, decay=0.08)
        self.sounds["heartbeat"] = self._to_sound(
            np.concatenate([lub, np.zeros(int(self.sr * 0.06)), dub])
        )

        # 3. 抽屜翻動/紙張沙沙聲
        self.sounds["paper"] = self._to_sound(self._noise(0.14, vol=0.30))

        # 4. 翻頁聲 (較清脆的雙節奏紙響)
        flip1 = self._noise(0.07, vol=0.28)
        flip2 = self._tone(920.0, 0.05, vol=0.12, attack=0.005, decay=0.04)
        self.sounds["page_flip"] = self._to_sound(np.concatenate([flip1, flip2]))

        # 5. 作答點擊聲
        self.sounds["click"] = self._to_sound(
            self._tone(1050.0, 0.045, vol=0.25, attack=0.003, decay=0.03)
        )

        # 6. 被當場抓包警報 (急促下行失真警報)
        b1 = self._tone(620.0, 0.16, vol=0.45, attack=0.01, decay=0.05)
        b2 = self._tone(420.0, 0.18, vol=0.48, attack=0.01, decay=0.06)
        b3 = self._tone(260.0, 0.35, vol=0.50, attack=0.01, decay=0.20)
        self.sounds["busted"] = self._to_sound(np.concatenate([b1, b2, b3]))

        # 7. 考試過關音效 (上行三和弦)
        v1 = self._tone(523.25, 0.11, vol=0.35)
        v2 = self._tone(659.25, 0.11, vol=0.35)
        v3 = self._tone(783.99, 0.14, vol=0.38)
        v4 = self._tone(1046.50, 0.28, vol=0.42, decay=0.18)
        self.sounds["victory"] = self._to_sound(np.concatenate([v1, v2, v3, v4]))

        # 8. 老師無聲偷看前兆 (輕微清喉嚨/腳步微響，不會有明顯嗶聲)
        cough_low = self._tone(145.0, 0.12, vol=0.22, attack=0.01, decay=0.08)
        cough_air = self._noise(0.12, vol=0.22)
        self.sounds["cough"] = self._to_sound(cough_low + cough_air)

        # 9. EMG 肌肉疲勞抽筋撞擊抽屜巨響
        thump = self._tone(110.0, 0.18, vol=0.62, attack=0.002, decay=0.15)
        crack = self._noise(0.10, vol=0.48)
        pad_crack = np.pad(crack, (0, max(0, len(thump) - len(crack))))[: len(thump)]
        self.sounds["slam"] = self._to_sound(thump + pad_crack)

        # 10. 教室突發干擾 (同學掉筆/打噴嚏)
        clatter1 = self._tone(1480.0, 0.05, vol=0.25, attack=0.002, decay=0.04)
        clatter2 = self._tone(1180.0, 0.06, vol=0.20, attack=0.002, decay=0.05)
        self.sounds["distraction"] = self._to_sound(
            np.concatenate([clatter1, np.zeros(int(self.sr * 0.04)), clatter2])
        )

        # 11. 偷看鄰座成功提示音
        p1 = self._tone(740.0, 0.06, vol=0.22)
        p2 = self._tone(987.77, 0.09, vol=0.24)
        self.sounds["peek"] = self._to_sound(np.concatenate([p1, p2]))

        # 12. 老師走下走道巡堂腳步聲 (沉重木地板悶響)
        step_low = self._tone(72.0, 0.11, vol=0.38, attack=0.004, decay=0.085)
        step_tap = self._noise(0.05, vol=0.18)
        pad_tap = np.pad(step_tap, (0, max(0, len(step_low) - len(step_tap))))[: len(step_low)]
        self.sounds["footstep"] = self._to_sound(step_low + pad_tap)

    def _play(self, name):
        if self.enabled and name in self.sounds:
            try:
                self.sounds[name].play()
            except Exception:
                pass

    def play_buzzer(self):
        self._play("buzzer")

    def play_heartbeat(self):
        self._play("heartbeat")

    def play_paper(self):
        self._play("paper")

    def play_page_flip(self):
        self._play("page_flip")

    def play_click(self):
        self._play("click")

    def play_busted(self):
        self._play("busted")

    def play_victory(self):
        self._play("victory")

    def play_cough(self):
        self._play("cough")

    def play_slam(self):
        self._play("slam")

    def play_distraction(self):
        self._play("distraction")

    def play_peek(self):
        self._play("peek")

    def play_footstep(self):
        self._play("footstep")
