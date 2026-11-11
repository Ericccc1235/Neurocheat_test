"""
NeuroCheat 音效生成器
使用 numpy 和 pygame.mixer 合成程序化音效，無需外部音訊檔案
"""

import math
import numpy as np
import pygame

class SoundManager:
    def __init__(self):
        self.enabled = False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            self.enabled = True
            self._generate_sounds()
        except Exception as e:
            print(f"[SoundManager] Warning: Audio init failed ({e}), continuing silently.")

    def _generate_sounds(self):
        sample_rate = 44100
        
        # 1. 蜂鳴器警報聲 (Buzzer Alert) - 模擬兩段短促急促警示聲
        buzzer_samples = []
        for _ in range(2):
            t = np.linspace(0, 0.12, int(sample_rate * 0.12), False)
            tone = 0.5 * np.sin(2 * np.pi * 1050 * t) + 0.3 * np.sin(2 * np.pi * 2100 * t)
            # 加 envelope 避免爆音
            envelope = np.ones_like(tone)
            fade = int(sample_rate * 0.01)
            envelope[:fade] = np.linspace(0, 1, fade)
            envelope[-fade:] = np.linspace(1, 0, fade)
            buzzer_samples.append(tone * envelope)
            # 間隔靜音
            buzzer_samples.append(np.zeros(int(sample_rate * 0.05)))
        
        raw_buzzer = np.concatenate(buzzer_samples)
        self.snd_buzzer = self._create_sound(raw_buzzer, sample_rate)

        # 2. 心跳低頻咚聲 (Heartbeat Lub)
        t = np.linspace(0, 0.15, int(sample_rate * 0.15), False)
        decay = np.exp(-t * 28)
        heart_tone = np.sin(2 * np.pi * 65 * t) * decay * 0.8
        self.snd_heartbeat = self._create_sound(heart_tone, sample_rate)

        # 3. 紙張滑出/小抄聲 (Paper slide)
        t = np.linspace(0, 0.18, int(sample_rate * 0.18), False)
        noise = np.random.uniform(-0.15, 0.15, len(t))
        envelope = np.sin(np.pi * np.linspace(0, 1, len(t)))
        self.snd_paper = self._create_sound(noise * envelope, sample_rate)

        # 4. 按鈕點擊/作答聲 (Click)
        t = np.linspace(0, 0.06, int(sample_rate * 0.06), False)
        click_tone = np.sin(2 * np.pi * 1200 * t) * np.exp(-t * 80) * 0.4
        self.snd_click = self._create_sound(click_tone, sample_rate)

        # 5. 抓包音效 (Busted!) - 低沈驚嚇音
        t = np.linspace(0, 0.6, int(sample_rate * 0.6), False)
        freq = np.linspace(400, 80, len(t))
        busted_tone = (np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * freq * 0.5 * t)) * np.exp(-t * 4) * 0.8
        self.snd_busted = self._create_sound(busted_tone, sample_rate)

        # 6. 通關勝利 (Victory Fanfare)
        vic_samples = []
        pitches = [523.25, 659.25, 783.99, 1046.50]  # C5, E5, G5, C6
        for p in pitches:
            t = np.linspace(0, 0.16, int(sample_rate * 0.16), False)
            tone = np.sin(2 * np.pi * p * t) * np.exp(-t * 8) * 0.5
            vic_samples.append(tone)
        vic_raw = np.concatenate(vic_samples)
        self.snd_victory = self._create_sound(vic_raw, sample_rate)

    def _create_sound(self, array, sample_rate):
        stereo = np.column_stack((array, array))
        clamped = np.clip(stereo * 32767, -32768, 32767).astype(np.int16)
        return pygame.sndarray.make_sound(clamped)

    def play_buzzer(self):
        if self.enabled:
            self.snd_buzzer.play()

    def play_heartbeat(self):
        if self.enabled:
            self.snd_heartbeat.play()

    def play_paper(self):
        if self.enabled:
            self.snd_paper.play()

    def play_click(self):
        if self.enabled:
            self.snd_click.play()

    def play_busted(self):
        if self.enabled:
            self.snd_busted.play()

    def play_victory(self):
        if self.enabled:
            self.snd_victory.play()
