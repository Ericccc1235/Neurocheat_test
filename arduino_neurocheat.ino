/*
  NeuroCheat - 生醫工程期末專題 (Group 6)
  Arduino / ESP32 硬體韌體範例
  
  組員：黃建澄 (B13502162)、王家佑 (B13901094)、張嘉宸 (B13901135)
  
  功能：
  1. 實體按鈕 (Pin 2)：代替 EMG 握拳用力 (按住 = 1, 放開 = 0)
  2. 心率感測器 / 電位計 (Pin A0)：模擬或真實量測 ECG 心率 BPM (60 ~ 140)
  3. 腦波專注度 / 電位計 (Pin A1)：模擬或真實量測 EEG 專注度 (0 ~ 100%)
  4. 輸出格式 (Serial 115200 bps): "EMG:1,ECG:78.5,EEG:82.0\n"
*/

const int PIN_EMG_BUTTON = 2; // 連接按鈕開關 (按下接地，使用內建上拉電阻)
const int PIN_ECG_ANALOG = A0;// 連接心率感測模組 (如 Pulse Sensor 或電位計)
const int PIN_EEG_ANALOG = A1;// 連接腦波模組訊號或專注度電位計

unsigned long lastSendTime = 0;
const unsigned long SEND_INTERVAL = 50; // 每 50ms 發送一筆數據 (20 Hz)

void setup() {
  Serial.begin(115200);
  
  // 設定按鈕為輸入，啟用內部上拉電阻 (按下時讀取為 LOW)
  pinMode(PIN_EMG_BUTTON, INPUT_PULLUP);
}

void loop() {
  unsigned long now = millis();
  
  if (now - lastSendTime >= SEND_INTERVAL) {
    lastSendTime = now;
    
    // 1. 讀取 EMG 按鈕 (按下 = 1, 放開 = 0)
    int buttonReading = digitalRead(PIN_EMG_BUTTON);
    int emgState = (buttonReading == LOW) ? 1 : 0;
    
    // 2. 讀取 ECG 心率 (A0 轉換為 55 ~ 145 BPM)
    int rawECG = analogRead(PIN_ECG_ANALOG);
    float ecgBPM = map(rawECG, 0, 1023, 60, 140);
    
    // 3. 讀取 EEG 專注度 (A1 轉換為 0 ~ 100%)
    int rawEEG = analogRead(PIN_EEG_ANALOG);
    float eegFocus = map(rawEEG, 0, 1023, 10, 100);
    
    // 4. 透過 Serial 發送標準通訊協定字串給 Python 遊戲
    Serial.print("EMG:");
    Serial.print(emgState);
    Serial.print(",ECG:");
    Serial.print(ecgBPM, 1);
    Serial.print(",EEG:");
    Serial.print(eegFocus, 1);
    Serial.println();
  }
}
