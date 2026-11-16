// PURVA SANKET: Physical ESP32 Hardware Firmware (Direct HTTP REST — No Broker)
// Sensors: LM35DZ (Temperature on GPIO 34) + MPU-6050 (Vibration via I2C on GPIO 21/22)
// Actuators: Red LED (GPIO 26), Green LED (GPIO 27), Active Buzzer (GPIO 25), Motor LED (GPIO 2)
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <math.h>

// ======================== CONFIGURATION ========================
// 1. Enter your Wi-Fi credentials (or mobile hotspot):
const char* WIFI_SSID     = "YOUR_WIFI_SSID";       // Set your Wi-Fi SSID
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";   // Set your Wi-Fi Password

// 2. Direct Backend URL (Replace with your laptop's local LAN IP):
// On Windows, run 'ipconfig' in command prompt to find your IPv4 address (e.g., 192.168.1.50)
const char* BACKEND_URL   = "http://192.168.1.100:8000/api/telemetry";

// 3. Pin Assignments:
// Sensors
const int LM35_PIN        = 34;   // LM35DZ Pin 2 (VOUT) -> ESP32 GPIO 34 (ADC1)
const int SDA_PIN         = 21;   // MPU-6050 SDA       -> ESP32 GPIO 21
const int SCL_PIN         = 22;   // MPU-6050 SCL       -> ESP32 GPIO 22

// Actuators & Indicators
const int RED_LED         = 26;   // Red LED (Warning / Fault) with 220-330 ohm resistor
const int GREEN_LED       = 27;   // Green LED (Normal Running) with 220-330 ohm resistor
const int BUZZER_PIN      = 25;   // Active Buzzer module signal pin
const int MOTOR_LED       = 2;    // Built-in Blue LED on ESP32 DevKit
// ===============================================================

Adafruit_MPU6050 mpu;

// State tracking variables
bool mpuReady = false;
bool motorRunning = false;
bool desiredMotor = false;
bool remoteAlarm = false;
bool remoteWarning = false;
bool remoteDegraded = false;
bool gotFirstControl = false;

uint32_t lastRestartNonce = 0;
uint32_t lastControlAt = 0;
uint32_t lastPublish = 0;
uint32_t lastSample = 0;
uint32_t sequence = 0;

String sessionId;
String lastCommandId = "";

// Vibration buffers (100 Hz sampling, evaluated every 1000 ms)
float sumA[3] = {0, 0, 0};
float sumAA[3] = {0, 0, 0};
int sampleCount = 0;
float accelerationRms = 0.0;
bool windowValid = false;

// Temperature variables
float measuredTemperature = 0.0;
bool tempValid = false;

// ---------------------------------------------------------------
// Read LM35DZ using ESP32 calibrated ADC with multi-sample averaging
// ---------------------------------------------------------------
float readLM35Temperature() {
  const int SAMPLES = 25;
  uint32_t totalMilliVolts = 0;

  for (int i = 0; i < SAMPLES; i++) {
    totalMilliVolts += analogReadMilliVolts(LM35_PIN);
    delayMicroseconds(400);
  }

  float avgMilliVolts = (float)totalMilliVolts / SAMPLES;

  // LM35 scale: 10 mV = 1.0 deg C (Temp = Millivolts / 10.0)
  float tempC = avgMilliVolts / 10.0f;
  return tempC;
}

// ---------------------------------------------------------------
// Update Actuator Outputs (LEDs and Buzzer) with Local Fallbacks
// ---------------------------------------------------------------
void updateActuators() {
  bool controlFresh = gotFirstControl && (millis() - lastControlAt < 8000);
  bool localCritical = tempValid && (measuredTemperature >= 60.0);
  bool isWarning = remoteWarning || localCritical;
  bool isDegraded = remoteDegraded || !controlFresh || !tempValid || !mpuReady;

  // Motor runs only when commanded, control is fresh, and sensors report safe
  motorRunning = desiredMotor && controlFresh && tempValid && mpuReady && !localCritical && !remoteDegraded;

  digitalWrite(MOTOR_LED, motorRunning ? HIGH : LOW);
  digitalWrite(GREEN_LED, (motorRunning && !isWarning) ? HIGH : LOW);
  digitalWrite(RED_LED, (isWarning || isDegraded) ? HIGH : LOW);
  digitalWrite(BUZZER_PIN, (remoteAlarm || localCritical) ? HIGH : LOW);
}

// ---------------------------------------------------------------
// 100 Hz Vibration Sampling (Every 10ms)
// ---------------------------------------------------------------
void sampleVibration() {
  if (!mpuReady || millis() - lastSample < 10) return;
  lastSample = millis();

  sensors_event_t a, g, t;
  mpu.getEvent(&a, &g, &t);

  // Accumulate raw 3-axis acceleration values
  float vals[3] = {a.acceleration.x, a.acceleration.y, a.acceleration.z};
  for (int i = 0; i < 3; i++) {
    sumA[i] += vals[i];
    sumAA[i] += vals[i] * vals[i];
  }
  sampleCount++;
}

// ---------------------------------------------------------------
// Send Telemetry Direct via HTTP POST and Receive Control Command
// ---------------------------------------------------------------
void sendTelemetryDirect() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Disconnected. Reconnecting...");
    WiFi.reconnect();
    return;
  }

  // 1. Read LM35 Temperature
  measuredTemperature = readLM35Temperature();
  tempValid = (measuredTemperature >= 0.0 && measuredTemperature <= 110.0);

  // 2. Calculate dynamic RMS vibration (m/s^2) excluding 1g static gravity
  float variance = 0.0;
  windowValid = (mpuReady && sampleCount >= 20);
  if (windowValid) {
    for (int i = 0; i < 3; i++) {
      float mean = sumA[i] / sampleCount;
      variance += fmaxf(0.0f, (sumAA[i] / sampleCount) - (mean * mean));
    }
    accelerationRms = sqrtf(variance);
  }

  // Reset accumulation buffers for next 1-second window
  sampleCount = 0;
  for (int i = 0; i < 3; i++) {
    sumA[i] = 0;
    sumAA[i] = 0;
  }

  // Update physical actuators
  updateActuators();

  // 3. Build JSON payload
  JsonDocument doc;
  doc["device_id"] = "esp32-01";
  doc["session_id"] = sessionId;
  doc["seq"] = sequence++;
  doc["device_ts_ms"] = millis();
  doc["scene"] = 0; // Physical hardware mode

  if (tempValid) doc["temp_c"] = measuredTemperature;
  else doc["temp_c"] = nullptr;
  doc["temp_valid"] = tempValid;

  if (windowValid) doc["vibration_rms_ms2"] = accelerationRms;
  else doc["vibration_rms_ms2"] = nullptr;
  doc["vibration_valid"] = windowValid;

  // Interlock healthy flags
  doc["cooling_command"] = true;
  doc["cooling_feedback"] = true;
  doc["guard_closed"] = true;
  doc["worker_simulated"] = false;
  doc["run_requested"] = true;
  doc["motor_indicator"] = motorRunning;

  // Handshake and confirmation protocol
  bool feedbackFresh = gotFirstControl && (millis() - lastControlAt < 8000) && (lastCommandId.length() > 0);
  doc["response_protocol"] = 1;
  doc["ack_command_id"] = lastCommandId;
  doc["feedback_command_id"] = lastCommandId;
  doc["motor_feedback_valid"] = feedbackFresh;
  doc["motor_feedback_running"] = motorRunning;
  doc["motor_feedback_source"] = "ESP32 Physical Actuator Feedback";
  doc["source"] = "ESP32 physical hardware (LM35DZ + MPU6050)";

  String payload;
  serializeJson(doc, payload);

  // 4. Direct HTTP POST to Laptop Backend
  WiFiClient client;
  HTTPClient http;
  http.begin(client, BACKEND_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(2500);

  int httpCode = http.POST(payload);

  if (httpCode == HTTP_CODE_OK || httpCode == 200) {
    String response = http.getString();
    JsonDocument resDoc;
    if (!deserializeJson(resDoc, response)) {
      JsonObject control = resDoc["control"];
      if (!control.isNull()) {
        desiredMotor = control["motor_on"] | false;
        remoteAlarm = control["alarm"] | false;
        remoteWarning = control["warning"] | false;
        remoteDegraded = control["degraded"] | false;
        lastCommandId = String(control["command_id"] | "");
        lastControlAt = millis();
        gotFirstControl = true;
      }
    }
    Serial.printf("[HTTP 200] LM35: %.1f C | Vib: %.3f m/s2 | Motor: %s\n",
                  measuredTemperature, accelerationRms, motorRunning ? "RUN" : "STOP");
  } else {
    Serial.printf("[HTTP ERROR %d] Failed to reach backend: %s\n", httpCode, BACKEND_URL);
  }

  http.end();
  updateActuators();
}

// ---------------------------------------------------------------
// Setup
// ---------------------------------------------------------------
void setup() {
  Serial.begin(115200);

  // Initialize output pins
  pinMode(MOTOR_LED, OUTPUT);
  pinMode(RED_LED, OUTPUT);
  pinMode(GREEN_LED, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  digitalWrite(MOTOR_LED, LOW);
  digitalWrite(RED_LED, LOW);
  digitalWrite(GREEN_LED, LOW);
  digitalWrite(BUZZER_PIN, LOW);

  // Set up ADC for LM35DZ (ADC1 Pin 34)
  analogReadResolution(12);
  analogSetPinAttenuation(LM35_PIN, ADC_11db); // 0 to 3.3V range

  // Initialize I2C and MPU-6050
  Wire.begin(SDA_PIN, SCL_PIN);
  if (mpu.begin()) {
    mpuReady = true;
    mpu.setAccelerometerRange(MPU6050_RANGE_4_G);
    mpu.setFilterBandwidth(MPU6050_BAND_44_HZ);
    Serial.println("[MPU-6050] Initialized successfully.");
  } else {
    Serial.println("[WARNING] MPU-6050 not detected! Check SDA (D21) / SCL (D22) wiring.");
  }

  // Create unique session ID
  sessionId = String((uint32_t)esp_random(), HEX);

  // Connect to Wi-Fi
  Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\n[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
  Serial.printf("[Backend Target] %s\n", BACKEND_URL);
}

// ---------------------------------------------------------------
// Main Loop
// ---------------------------------------------------------------
void loop() {
  // Continuously sample vibration (100 Hz)
  sampleVibration();

  // Send telemetry directly via HTTP POST once every 1 second
  if (millis() - lastPublish >= 1000) {
    lastPublish = millis();
    sendTelemetryDirect();
  }
  delay(1);
}
