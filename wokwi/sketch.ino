// PURVA SANKET: Wokwi-only demonstration. All scenarios contain synthetic inputs.
// This code controls indicator LEDs, not a physical or certified machine stop.
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <math.h>

// Replace this with the SAME unique topic configured on the laptop.
const char* TOPIC_BASE = "purva-sanket/bbc25cece3d0111e";
const char* MQTT_HOST = "test.mosquitto.org";
const uint16_t MQTT_PORT = 1883;
const int TEMP_PIN=4, SDA_PIN=21, SCL_PIN=22, VIBRATION_KNOB=34;
const int COOLING_COMMAND=13, COOLING_FEEDBACK=14, TEMP_AVAILABLE=32, GUARD_CLOSED=33;
const int NEXT_SCENE=26, MANUAL_INPUTS=25;
const int MOTOR_FEEDBACK_TEST=35; // external pull-up; LEFT normal / RIGHT injected RUN feedback
const int NORMAL_LED=16, WARNING_LED=17, FAULT_LED=18, MOTOR_LED=19, COOLING_LED=23, BUZZER=27;
WiFiClient net;
PubSubClient mqtt(net);
Adafruit_MPU6050 mpu;
OneWire oneWire(TEMP_PIN);
DallasTemperature temperatureSensor(&oneWire);
bool mpuReady=false, localStopLatched=true, desiredMotor=false, remoteWarning=false, remoteFault=true, remoteAlarm=false;
bool gotFirstControl=false, motorIndicator=false;
uint32_t lastRestartNonce=0, lastControlAt=0, lastPublish=0, lastSample=0, lastReconnect=0, sceneStarted=0;
uint32_t sequence=0;
int scene=1;
String sessionId, telemetryTopic, controlTopic, scenarioTopic;
String lastCommandId;
float measuredTemperature=35, sumA[3]={0,0,0}, sumAA[3]={0,0,0}, accelerationRms=0;
int sampleCount=0;
bool windowValid=false;

struct Inputs {float temperature, targetRms; bool temperatureValid, coolingCommand, coolingFeedback, guardClosed, worker;};

Inputs inputs() {
  float seconds=(millis()-sceneStarted)/1000.0f;
  Inputs p={35+.2f*sinf(seconds), .10f+.01f*sinf(seconds*.7f), true, true, true, true, false};
  if(scene==0) {
    p.temperature=measuredTemperature;
    p.temperatureValid=digitalRead(TEMP_AVAILABLE)==LOW && measuredTemperature!=DEVICE_DISCONNECTED_C;
    p.targetRms=1.8f*(analogRead(VIBRATION_KNOB)/4095.0f)/sqrtf(2);
    p.coolingCommand=digitalRead(COOLING_COMMAND)==LOW;
    p.coolingFeedback=digitalRead(COOLING_FEEDBACK)==LOW;
    p.guardClosed=digitalRead(GUARD_CLOSED)==LOW;
  } else if(scene==2) {
    p.temperature=39+fminf(seconds,25)*.5f;
    int phase=((int)seconds)%8;
    p.targetRms=(phase>=2 && phase<=4) ? .65f : .10f;
  } else if(scene>=3 && scene<=5) {
    p.temperature=56+.2f*sinf(seconds);
    p.targetRms=.65f;
    p.coolingFeedback=false;
    p.worker=scene==4 || scene==5;
    p.temperatureValid=scene!=5;
  } else if(scene==7) {
    p.temperature=35+fminf(seconds,9)*.12f;
    p.targetRms=.22f;
  }
  // Scene 6 returns to normal values; warning closure remains the laptop's decision.
  return p;
}

void selectScene(int requested) {
  if(requested<0 || requested>7) return;
  scene=requested;
  sceneStarted=millis();
  sampleCount=0;
  for(int n=0;n<3;n++){sumA[n]=0;sumAA[n]=0;}
  Serial.printf("Scene %d selected; scripted inputs do not clear an episode.\n",scene);
}

void callback(char* topic, byte* payload, unsigned int length) {
  JsonDocument doc;
  if(deserializeJson(doc,payload,length)) return;
  if(String(topic)==scenarioTopic) {
    selectScene(doc["scene"] | 1);
  } else if(String(topic)==controlTopic) {
    lastControlAt=millis();
    lastCommandId=String(doc["command_id"] | "");
    desiredMotor=doc["motor_on"] | false;
    remoteAlarm=doc["alarm"] | false;
    remoteWarning=doc["warning"] | false;
    remoteFault=doc["degraded"] | true;
    uint32_t nonce=doc["restart_nonce"] | 0;
    if(!gotFirstControl) {
      lastRestartNonce=nonce;
      gotFirstControl=true;
    } else if(nonce!=lastRestartNonce) {
      Inputs p=inputs();
      bool localValid=p.temperatureValid && mpuReady && p.guardClosed;
      bool localCritical=p.temperature>=60 || (p.temperature>=55 && p.coolingCommand && !p.coolingFeedback);
      if(desiredMotor && localValid && !localCritical && !remoteFault) localStopLatched=false;
      lastRestartNonce=nonce;
    }
  }
}

void reconnect() {
  if(WiFi.status()!=WL_CONNECTED || mqtt.connected() || millis()-lastReconnect<3000) return;
  lastReconnect=millis();
  String clientId="purva-wokwi-"+sessionId;
  if(mqtt.connect(clientId.c_str())) {
    mqtt.subscribe(controlTopic.c_str());
    mqtt.subscribe(scenarioTopic.c_str());
    Serial.println("MQTT connected. Laptop control heartbeat required before starting.");
  } else Serial.printf("MQTT connection failed, code %d. Will retry.\n",mqtt.state());
}

void sampleAcceleration() {
  if(!mpuReady || millis()-lastSample<10) return;
  lastSample=millis();
  sensors_event_t a,g,t;
  mpu.getEvent(&a,&g,&t);
  Inputs p=inputs();
  // Wokwi does not simulate machine vibration physics. Inject a labelled test
  // waveform alongside virtual MPU6050 readings to exercise RMS extraction.
  float wave=sqrtf(2)*p.targetRms*sinf(2*PI*10*(millis()/1000.0f));
  float values[3]={a.acceleration.x+wave,a.acceleration.y,a.acceleration.z};
  for(int n=0;n<3;n++){sumA[n]+=values[n];sumAA[n]+=values[n]*values[n];}
  sampleCount++;
}

void updateOutputs() {
  Inputs p=inputs();
  bool controlFresh=gotFirstControl && millis()-lastControlAt<6000;
  bool localCritical=p.temperatureValid && (p.temperature>=60 || (p.temperature>=55 && p.coolingCommand && !p.coolingFeedback));
  bool localFault=!p.temperatureValid || !mpuReady || !p.guardClosed || !controlFresh;
  if(localCritical || localFault || remoteFault || !desiredMotor) localStopLatched=true;
  motorIndicator=desiredMotor && !localStopLatched && !localFault && !localCritical;
  digitalWrite(MOTOR_LED,motorIndicator);
  digitalWrite(COOLING_LED,p.coolingCommand); // a command, not feedback
  digitalWrite(NORMAL_LED,controlFresh && !remoteWarning && !remoteFault && !localFault && !localCritical);
  digitalWrite(WARNING_LED,remoteWarning || localCritical);
  digitalWrite(FAULT_LED,remoteFault || localFault);
  if(!remoteAlarm && !localCritical) noTone(BUZZER);
}

void publishTelemetry() {
  measuredTemperature=temperatureSensor.getTempCByIndex(0);
  temperatureSensor.requestTemperatures(); // asynchronous conversion
  float variance=0;
  windowValid=mpuReady && sampleCount>=20;
  if(windowValid) {
    for(int n=0;n<3;n++) {
      float mean=sumA[n]/sampleCount;
      variance+=fmaxf(0,sumAA[n]/sampleCount-mean*mean);
    }
  }
  accelerationRms=sqrtf(variance);
  sampleCount=0;
  for(int n=0;n<3;n++){sumA[n]=0;sumAA[n]=0;}
  Inputs p=inputs();
  JsonDocument doc;
  doc["device_id"]="motor-01";
  doc["session_id"]=sessionId;
  doc["seq"]=sequence++;
  doc["device_ts_ms"]=millis();
  doc["scene"]=scene;
  if(p.temperatureValid) doc["temp_c"]=p.temperature; else doc["temp_c"]=nullptr;
  doc["temp_valid"]=p.temperatureValid;
  if(windowValid) doc["vibration_rms_ms2"]=accelerationRms; else doc["vibration_rms_ms2"]=nullptr;
  doc["vibration_valid"]=windowValid;
  doc["cooling_command"]=p.coolingCommand;
  doc["cooling_feedback"]=p.coolingFeedback;
  doc["guard_closed"]=p.guardClosed;
  doc["worker_simulated"]=p.worker;
  doc["run_requested"]=true;
  doc["motor_indicator"]=motorIndicator;
  bool feedbackFresh=gotFirstControl && millis()-lastControlAt<6000 && lastCommandId.length()>0;
  bool injectedRunning=digitalRead(MOTOR_FEEDBACK_TEST)==HIGH;
  doc["response_protocol"]=1;
  doc["ack_command_id"]=lastCommandId;
  doc["feedback_command_id"]=lastCommandId;
  doc["motor_feedback_valid"]=feedbackFresh;
  if(feedbackFresh) doc["motor_feedback_running"]=motorIndicator || injectedRunning;
  else doc["motor_feedback_running"]=nullptr;
  doc["motor_feedback_source"]=injectedRunning ? "Wokwi injected RUN feedback switch" : "Wokwi simulated actuator feedback";
  doc["source"]=scene==0 ? "Wokwi virtual sensor + injected waveform" : "Wokwi scripted synthetic scenario";
  String output;
  serializeJson(doc,output);
  Serial.println(output);
  if(mqtt.connected()) mqtt.publish(telemetryTopic.c_str(),output.c_str(),false);
  if(remoteAlarm || (p.temperatureValid && p.temperature>=60)) tone(BUZZER,2000,100);
}

void setup() {
  Serial.begin(115200);
  for(int pin:{COOLING_COMMAND,COOLING_FEEDBACK,TEMP_AVAILABLE,GUARD_CLOSED,NEXT_SCENE,MANUAL_INPUTS}) pinMode(pin,INPUT_PULLUP);
  pinMode(MOTOR_FEEDBACK_TEST,INPUT);
  for(int pin:{NORMAL_LED,WARNING_LED,FAULT_LED,MOTOR_LED,COOLING_LED,BUZZER}) {pinMode(pin,OUTPUT);digitalWrite(pin,LOW);}
  Wire.begin(SDA_PIN,SCL_PIN);
  mpuReady=mpu.begin();
  if(mpuReady){mpu.setAccelerometerRange(MPU6050_RANGE_4_G);mpu.setFilterBandwidth(MPU6050_BAND_44_HZ);}
  temperatureSensor.begin();
  temperatureSensor.setWaitForConversion(false);
  temperatureSensor.requestTemperatures();
  sessionId=String((uint32_t)esp_random(),HEX);
  telemetryTopic=String(TOPIC_BASE)+"/telemetry";
  controlTopic=String(TOPIC_BASE)+"/control";
  scenarioTopic=String(TOPIC_BASE)+"/scenario";
  mqtt.setServer(MQTT_HOST,MQTT_PORT);
  mqtt.setCallback(callback);
  mqtt.setBufferSize(2048);
  mqtt.setSocketTimeout(2);
  WiFi.begin("Wokwi-GUEST","",6);
  selectScene(1);
  Serial.println("Synthetic simulation. NEXT cycles scenes 1-6; MANUAL enables circuit controls.");
}

void loop() {
  static bool previousNext=HIGH,previousManual=HIGH;
  static uint32_t lastButtonAt=0;
  bool next=digitalRead(NEXT_SCENE),manual=digitalRead(MANUAL_INPUTS);
  if(millis()-lastButtonAt>150) {
    if(next==LOW && previousNext==HIGH){selectScene(scene%6+1);lastButtonAt=millis();}
    if(manual==LOW && previousManual==HIGH){selectScene(0);lastButtonAt=millis();}
  }
  previousNext=next;previousManual=manual;
  reconnect();
  mqtt.loop();
  sampleAcceleration();
  updateOutputs();
  if(millis()-lastPublish>=1000){lastPublish=millis();publishTelemetry();}
  delay(1);
}
