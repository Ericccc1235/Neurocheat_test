/*
  NeuroCheat Exp 2 雙通道生醫前端韌體 (Arduino UNO + HM-10 BLE / HC-05 / USB)
  =========================================================================
  由實驗二原版 arduino_ecg_bluetooth.ino 升級，完整對接期末專題遊戲：
  - Pin A0 : Exp 2 ECG 類比前端輸出 (0~5V，直流偏壓約 2.4~2.5V，取樣率 160Hz，保留完整 10-bit 解析度)
  - Pin A1 : Exp 2 EMG 類比前端輸出 (0~5V，於 Arduino 內以 1kHz 取樣計算整流+EMA 包絡線，完全解決 200Hz aliasing)
  - Pin 4  : 選配實體測試按鈕 (INPUT_PULLUP，按下接地可視為強制最大握拳測試)
  - Pin 8  : 有源蜂鳴器 / 震動馬達輸出 (接收遊戲傳回指令，模擬奶娃警告預備／抓包提示)
  - Pin 2/3: HM-10 (BLE 4.0) 或 HC-05 藍牙模組 (SoftwareSerial RX=2, TX=3, 9600 baud)
             * 若使用 HM-10 裸模組 (3.3V 邏輯)，建議 Arduino Pin 3 (TX) 經 1kΩ+2kΩ 分壓後再進 HM-10 RXD！

  免失步自我同步 3-Byte 二進位封包格式 (每筆 160Hz = 480 bytes/s，BLE 與 9600 baud 皆穩定不卡頓):
    Byte 0: 1 | status(2 bits: bit6=test_mode, bit5=btn_pressed) | ecg10[9:5]  (永遠 >= 0x80)
    Byte 1: 0 | ecg10[4:0]     | emg8[7:6]                                    (永遠 < 0x80)
    Byte 2: 0 | 0              | emg8[5:0]                                    (永遠 < 0x40)

  PC/遊戲端可傳入單字元指令：
    'S' = 開始/恢復串流 (Start)
    'P' = 暫停串流 (Pause)
    'B' = 蜂鳴器短鳴 2 聲 (奶娃預警警告)
    'C' = 蜂鳴器長鳴 1 聲 (被抓包警示)
    'T' = 切換假訊號測試波形模式 (免接電極測試全系統)
*/

#include <SoftwareSerial.h>
#include <math.h>

SoftwareSerial BTSerial(2, 3); // Arduino Pin 2 = RX (接 HM-10/HC-05 TXD), Pin 3 = TX (接 RXD)

// 腳位定義
const int PIN_ECG = A0;
const int PIN_EMG = A1;
const int PIN_EMG_BTN = 4;     // 選配按鈕：不接電極時可用實體按鈕測試 EMG
const int PIN_BUZZER = 8;      // 蜂鳴器或震動模組 (+極接 Pin 8，-極接 GND)

// 同時支援藍牙 UART (Pin 2/3 @ 9600: HM-10 / HC-05) 與 USB (115200)
const bool USE_BT_UART = true;
const bool USE_USB_SERIAL = true;
const long BT_BAUD = 9600;     // 多數 HM-10 與 HC-05 出廠預設皆為 9600 baud
const long USB_BAUD = 115200;

// 取樣週期設定：
// EMG 在 MCU 內以 1000Hz (1000 us) 取樣求包絡線，徹底避免 20~500Hz 混疊 (aliasing)
const unsigned long EMG_INTERVAL_US = 1000;
// 對外傳送頻率：160Hz (6250 us) -> 3 bytes * 160 = 480 bytes/s (9600 baud 下完全不阻塞)
const unsigned long FRAME_INTERVAL_US = 6250;

// 狀態旗標
bool streaming = true;         // 預設開機即準備串流 (也可接收 'S'/'P' 控制)
bool testWaveMode = false;     // true 會輸出模擬心電 R 波與定期握拳測試包絡線

unsigned long lastEmgUs = 0;
unsigned long lastFrameUs = 0;

// EMG DC 偏壓追蹤與包絡線
float emgDcBaseline = 512.0f;  // Exp2 Level Shifter 靜止約 2.5V (~512)
float emgEnvelope = 0.0f;

// 蜂鳴器非阻塞計時
unsigned long buzzerOffMs = 0;
int buzzerBeepRemaining = 0;
unsigned long nextBeepToggleMs = 0;
bool buzzerOn = false;

// 測試模式與 HM-10 連線提示字元濾除狀態
float simPhase = 0.0f;
byte okNoticeState = 0;  // 0=normal, 1=saw 'O', 2=saw "OK", 3=skipping "OK+..." notice bytes
byte okNoticeSkipLeft = 0;
unsigned long lastNoticeByteMs = 0;

void triggerBuzzerPattern(int count, unsigned long durationMs) {
  buzzerBeepRemaining = count * 2 - 1;
  buzzerOn = true;
  digitalWrite(PIN_BUZZER, HIGH);
  nextBeepToggleMs = millis() + durationMs;
}

void handleCommand(char cmd) {
  unsigned long nowMs = millis();
  if (okNoticeState != 0 && (nowMs - lastNoticeByteMs) > 25UL) {
    okNoticeState = 0;
    okNoticeSkipLeft = 0;
  }
  lastNoticeByteMs = nowMs;

  // 過濾 HM-10 的 "OK+CONN" / "OK+LOST" 等系統通知，避免裡面的 'C'/'T'/'S' 誤觸發動作
  if (okNoticeState == 3) {
    if (okNoticeSkipLeft > 0) okNoticeSkipLeft--;
    if (cmd == '\n' || cmd == '\r' || okNoticeSkipLeft == 0) {
      okNoticeState = 0;
    }
    return;
  }
  if (okNoticeState == 0 && cmd == 'O') { okNoticeState = 1; return; }
  if (okNoticeState == 1) {
    if (cmd == 'K') { okNoticeState = 2; return; }
    okNoticeState = 0;
  } else if (okNoticeState == 2) {
    if (cmd == '+') { okNoticeState = 3; okNoticeSkipLeft = 4; return; }
    okNoticeState = 0;
  }

  if (cmd == 'S' || cmd == 's') {
    streaming = true;
  } else if (cmd == 'P' || cmd == 'p') {
    streaming = false;
  } else if (cmd == 'T' || cmd == 't') {
    testWaveMode = !testWaveMode;
  } else if (cmd == 'B' || cmd == 'b') {
    // 奶娃預警：兩短聲 (100ms 亮 / 80ms 滅 / 100ms 亮)
    triggerBuzzerPattern(2, 100);
  } else if (cmd == 'C' || cmd == 'c') {
    // 抓包警報：長鳴 450ms
    triggerBuzzerPattern(1, 450);
  }
}

void updateBuzzer() {
  if (!buzzerOn && buzzerBeepRemaining <= 0) return;
  unsigned long nowMs = millis();
  if (nowMs >= nextBeepToggleMs) {
    if (buzzerBeepRemaining > 0) {
      buzzerBeepRemaining--;
      buzzerOn = !buzzerOn;
      digitalWrite(PIN_BUZZER, buzzerOn ? HIGH : LOW);
      nextBeepToggleMs = nowMs + (buzzerOn ? 100 : 80);
    } else {
      buzzerOn = false;
      digitalWrite(PIN_BUZZER, LOW);
    }
  }
}

void setup() {
  if (USE_USB_SERIAL) {
    Serial.begin(USB_BAUD);
  }
  if (USE_BT_UART) {
    BTSerial.begin(BT_BAUD);
  }
  pinMode(PIN_ECG, INPUT);
  pinMode(PIN_EMG, INPUT);
  pinMode(PIN_EMG_BTN, INPUT_PULLUP);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);

  // 開機暖機估算 A1 靜止偏壓中心
  long sum = 0;
  for (int i = 0; i < 64; i++) {
    sum += analogRead(PIN_EMG);
    delay(2);
  }
  emgDcBaseline = sum / 64.0f;
}

void loop() {
  // 1. 接收來自 PC / 遊戲的指令 (HM-10/HC-05 與 USB 皆可收)
  while (USE_BT_UART && BTSerial.available() > 0) {
    handleCommand((char)BTSerial.read());
  }
  while (USE_USB_SERIAL && Serial.available() > 0) {
    handleCommand((char)Serial.read());
  }

  updateBuzzer();

  unsigned long nowUs = micros();

  // 2. 1kHz EMG 取樣與包絡線計算 (抗混疊 + 免傳高頻原始波形)
  if (nowUs - lastEmgUs >= EMG_INTERVAL_US) {
    lastEmgUs += EMG_INTERVAL_US;
    // 若中斷過久避免追趕暴衝
    if (nowUs - lastEmgUs > 10000UL) lastEmgUs = nowUs;

    int rawEmg = analogRead(PIN_EMG);
    // 慢速追蹤 Level Shifter 中心電壓飄移
    emgDcBaseline = 0.998f * emgDcBaseline + 0.002f * (float)rawEmg;
    float rectified = fabsf((float)rawEmg - emgDcBaseline);
    // 非對稱 EMA 包絡線 (用力上升快、放開平滑下降)
    float alpha = (rectified > emgEnvelope) ? 0.06f : 0.025f;
    emgEnvelope = (1.0f - alpha) * emgEnvelope + alpha * rectified;
  }

  // 3. 160Hz 打包傳送 ECG (10-bit) + EMG 包絡線 (8-bit)
  if (streaming && (nowUs - lastFrameUs >= FRAME_INTERVAL_US)) {
    lastFrameUs += FRAME_INTERVAL_US;
    if (nowUs - lastFrameUs > 25000UL) lastFrameUs = nowUs;

    bool btnPressed = (digitalRead(PIN_EMG_BTN) == LOW);
    int ecg10 = 512;
    int emg8 = 0;

    if (testWaveMode) {
      // 合成 ECG R-peak (約 75 BPM) 與週期性 EMG 握拳
      simPhase += 0.00625f * 1.25f; // ~1.25 Hz = 75 BPM
      if (simPhase >= 1.0f) simPhase -= 1.0f;
      float w = 0.0f;
      if (simPhase > 0.35f && simPhase < 0.40f) {
        w = 240.0f * sinf((simPhase - 0.35f) / 0.05f * PI);
      } else if (simPhase > 0.40f && simPhase < 0.44f) {
        w = -80.0f * sinf((simPhase - 0.40f) / 0.04f * PI);
      } else if (simPhase > 0.56f && simPhase < 0.70f) {
        w = 60.0f * sinf((simPhase - 0.56f) / 0.14f * PI);
      }
      ecg10 = constrain((int)(512.0f + w), 0, 1023);
      emg8 = btnPressed ? 220 : ((millis() / 4000) % 2 == 0 ? 160 : 12);
    } else {
      ecg10 = constrain(analogRead(PIN_ECG), 0, 1023);
      // 單極整流後偏離中心最大約 511，對應 0~255 (保留適當靈敏度)
      int scaled = (int)(emgEnvelope * 1.2f);
      if (btnPressed && scaled < 220) scaled = 220;
      emg8 = constrain(scaled, 0, 255);
    }

    byte statusBits = ((testWaveMode ? 1 : 0) << 1) | (btnPressed ? 1 : 0);
    byte frame[3];
    frame[0] = 0x80 | ((statusBits & 0x03) << 5) | ((ecg10 >> 5) & 0x1F);
    frame[1] = ((ecg10 & 0x1F) << 2) | ((emg8 >> 6) & 0x03);
    frame[2] = emg8 & 0x3F;

    if (USE_BT_UART) {
      BTSerial.write(frame, 3);
    }
    if (USE_USB_SERIAL) {
      Serial.write(frame, 3);
    }
  }
}
