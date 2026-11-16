// PURVA SANKET: Physical ESP32 Hardware Implementation
// Sensors: LM35DZ (Temperature on GPIO 34) + MPU-6050 (Vibration via I2C on GPIO 21/22)
// Actuators: Red LED (GPIO 26), Green LED (GPIO 27), Active Buzzer (GPIO 25), Motor LED (GPIO 2)
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <math.h>

// ======================== CONFIGURATION ========================
// 1. Enter your Wi-Fi credentials:
const char* WIFI_SSID     = "YOUR_WIFI_SSID";       // Set your Wi-Fi SSID
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";   // Set your Wi-Fi Password

// 2. MQTT Broker:
const char* MQTT_HOST     = "test.mosquitto.org";   // Public broker or laptop LAN IP
const uint16_t MQTT_PORT  = 1883;

// 3. Project Topic (Matches topic.txt and .env configuration):
const char* TOPIC_BASE    = "purva-sanket/bbc25cece3d0111e";

// 4. Pin Assignments:
// Sensors
const int LM35_PIN        = 34;   // LM35DZ Pin 2 (VOUT) -> ESP32 GPIO 34 (ADC1)
const int SDA_PIN         = 21;   // MPU-6050 SDA       -> ESP32 GPIO 21
const int SCL_PIN         = 22;   // MPU-6050 SCL       -> ESP32 GPIO 22

// Actuators & Indicators (Section 6.3 of Hardware Guide)
const int RED_LED         = 26;   // Red LED (Warning / Fault) with 220-330 ohm resistor
const int GREEN_LED       = 27;   // Green LED (Normal Running) with 220-330 ohm resistor
const int BUZZER_PIN      = 25;   // Active Buzzer module signal pin
const int MOTOR_LED       = 2;    // Built-in Blue LED on ESP32 DevKit
// ===============================================================

WiFiClient net;
PubSubClient mqtt(net);
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
String telemetryTopic;
String controlTopic;
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
  bool controlFresh = gotFirstControl && (millis() - lastControlAt < 6000);
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
// MQTT Control Callback (Receives commands from laptop dashboard)
// ---------------------------------------------------------------
void callback(char* topic, byte* payload, unsigned int length) {
  JsonDocument doc;
  if (deserializeJson(doc, payload, length)) return;

  if (String(topic) == controlTopic) {
    lastControlAt = millis();
    lastCommandId = String(doc["command_id"] | "");
    desiredMotor = doc["motor_on"] | false;
    remoteAlarm = doc["alarm"] | false;
    remoteWarning = doc["warning"] | false;
    remoteDegraded = doc["degraded"] | false;
    uint32_t nonce = doc["restart_nonce"] | 0;

    if (!gotFirstControl) {
      lastRestartNonce = nonce;
      gotFirstControl = true;
    } else if (nonce != lastRestartNonce) {
      lastRestartNonce = nonce;
    }

    updateActuators();
  }
}

// ---------------------------------------------------------------
// MQTT Reconnection
// ---------------------------------------------------------------
void reconnect() {
  if (WiFi.status() != WL_CONNECTED || mqtt.connected()) return;

  String clientId = "purva-esp32-" + sessionId;
  Serial.print("[MQTT] Connecting...");
  if (mqtt.connect(clientId.c_str())) {
    Serial.println(" Connected!");
    mqtt.subscribe(controlTopic.c_str());
  } else {
    Serial.printf(" Failed (state %d). Will retry.\n", mqtt.state());
  }
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
// Publish Telemetry Packet to Laptop Backend
// ---------------------------------------------------------------
void publishTelemetry() {
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

  // Update hardware outputs
  updateActuators();

  // 3. Build JSON payload matching backend/engine.py schema
  JsonDocument doc;
  doc["device_id"] = "motor-01";
  doc["session_id"] = sessionId;
  doc["seq"] = sequence++;
  doc["device_ts_ms"] = millis();
  doc["scene"] = 0; // 0 = Physical hardware mode

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
  bool feedbackFresh = gotFirstControl && (millis() - lastControlAt < 6000) && (lastCommandId.length() > 0);
  doc["response_protocol"] = 1;
  doc["ack_command_id"] = lastCommandId;
  doc["feedback_command_id"] = lastCommandId;
  doc["motor_feedback_valid"] = feedbackFresh;
  doc["motor_feedback_running"] = motorRunning;
  doc["motor_feedback_source"] = "ESP32 Physical Actuator Feedback";
  doc["source"] = "ESP32 physical hardware (LM35DZ + MPU6050)";

  String output;
  serializeJson(doc, output);

  Serial.printf("[Telemetry] LM35: %.1f C | Vib RMS: %.3f m/s2 | Motor: %s\n",
                measuredTemperature, accelerationRms, motorRunning ? "RUN" : "STOP");

  if (mqtt.connected()) {
    mqtt.publish(telemetryTopic.c_str(), output.c_str(), false);
  }
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
  telemetryTopic = String(TOPIC_BASE) + "/telemetry";
  controlTopic   = String(TOPIC_BASE) + "/control";

  // Connect to Wi-Fi
  Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\n[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());

  // Setup MQTT client
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(callback);
  mqtt.setBufferSize(2048);
  mqtt.setSocketTimeout(3);
}

// ---------------------------------------------------------------
// Main Loop
// ---------------------------------------------------------------
void loop() {
  if (WiFi.status() == WL_CONNECTED && !mqtt.connected()) {
    reconnect();
  }
  mqtt.loop();

  // Continuously sample vibration (100 Hz)
  sampleVibration();

  // Transmit telemetry once every 1 second
  if (millis() - lastPublish >= 1000) {
    lastPublish = millis();
    publishTelemetry();
  }
  delay(1);
}
