# PURVA SANKET — Complete Dashboard & System User Guide

> **AI + IoT / Industrial Early Warning & Machine Protection System**  
> *"One machine. Connected evidence. A defined response."*

---

## Table of Contents
1. [Overview & Architecture](#1-overview--architecture)
2. [Header & Connection Indicators](#2-header--connection-indicators)
3. [Top Metrics Cards](#3-top-metrics-cards)
4. [Real-World Factory Machine Zone Visualizer](#4-real-world-factory-machine-zone-visualizer)
5. [Scenario Demonstration Engine](#5-scenario-demonstration-engine)
6. [Context & Protective Feedback](#6-context--protective-feedback)
7. [Warning Explanation & Retained Evidence](#7-warning-explanation--retained-evidence)
8. [Sensor ML & Trend Analysis](#8-sensor-ml--trend-analysis)
9. [Response Verification (Two-Way Handshake)](#9-response-verification-two-way-handshake)
10. [Judge Fault Injection Panel](#10-judge-fault-injection-panel)
11. [Rules vs. Rules + ML Comparison Engine](#11-rules-vs-rules--ml-comparison-engine)
12. [Operator Response & 3-Step Recovery Workflow](#12-operator-response--3-step-recovery-workflow)
13. [Persistent Episode History & Audit Trail](#13-persistent-episode-history--audit-trail)

---

## 1. Overview & Architecture

**PURVA SANKET** is a hybrid predictive maintenance and safety orchestration platform combining:
* **IoT Edge Telemetry** (ESP32 / Wokwi virtual hardware running Dallas DS18B20 temperature sensor, MPU6050 accelerometer, airflow feedback, and safety interlocks).
* **Machine Learning Engine** (Isolation Forest anomaly detection on multi-dimensional rolling sensor windows).
* **Deterministic Safety Rules** (Critical threshold enforcement, cooling mismatch detection, and interlock stops).
* **Computer Vision Safety Zone Integration** (YOLOv8 + ByteTrack worker intrusion monitoring).
* **Closed-Loop Actuator Verification** (Guaranteed command acknowledgement and physical feedback confirmation).

---

## 2. Header & Connection Indicators

Located at the very top right of the dashboard:

| Element | Example Value | Description |
|---|---|---|
| **Source Badge** | `WOKWI / MQTT · SIMULATED INPUTS` or `LOCAL REPLAY` | Indicates where sensor telemetry is originating. Displays whether you are connected to the live MQTT broker (`test.mosquitto.org`) or offline synthetic replay. |
| **Connection Status** | `Broker connected` / `Connected` | Real-time WebSocket / polling link between browser and backend server. |

---

## 3. Top Metrics Cards

The four primary diagnostic telemetry cards at the top of the screen:

### 1. Equipment Risk
* **States**: `NORMAL` (Green), `WATCH` (Yellow), `WARNING` (Orange), `HIGH` (Red).
* **Episode Subtitle**: Shows the active safety incident ID (e.g. `OPEN · 00ccd72b` or `RECOVERING`).
* **Latching Logic**: Peak severity is preserved throughout an open episode until an operator acknowledges, records corrective actions, and verifies stability.

### 2. Monitoring Health
* **States**: `AVAILABLE` (Green) or `DEGRADED` (Red).
* **Telemetry Age**: Real-time counter (e.g., `Last telemetry 0.8 s ago`).
* **Stale Limit**: Telemetry older than **6.0 seconds** or packets with invalid/missing sensor flags immediately transition the system into **DEGRADED** health.

### 3. Temperature
* **Normal Range**: **32.0 °C – 44.9 °C** (Nominal: **~35.0 °C**).
* **Warning Threshold**: **≥ 45.0 °C** (`warm`).
* **Cooling Stop**: **≥ 55.0 °C** with absent cooling feedback.
* **Emergency Stop**: **≥ 60.0 °C** (`hot`).
* **Unavailable / Null**: Displayed when the sensor is disconnected or invalid.

### 4. Vibration RMS
* **Normal Range**: **0.06 – 0.29 m/s²** (Nominal: **~0.10 m/s²**).
* **Recurrence Warning**: **≥ 0.30 m/s²** with **≥ 3 crossing events within 60s**.
* **High RMS Warning**: **≥ 0.45 m/s²** (`vibration`).

---

## 4. Real-World Factory Machine Zone Visualizer

An interactive 2D animated canvas providing a real-time digital twin of the factory floor:

* ⚙️ **Motor & Rotor**: Spins dynamically based on motor command and telemetry. Speed changes with operating mode; stops with emergency brake indicators when stopped.
* 🌡️ **Thermal Heat Map**: Surrounds the motor with a dynamic thermal aura (Green `<45°C`, Orange `45–59°C`, Red `≥60°C`).
* 〰️ **Vibration Waves**: Generates oscillating wave rings reflecting measured RMS acceleration.
* 🌀 **Airflow Duct**: Animated cooling particle stream indicating active airflow cooling.
* 🚶 **YOLO Hazard Perimeter Zone**: A high-visibility safety boundary around the machine. Turns **Red** with flashing warning banners if a human enters while machine risks exist (`Worker Exposure Alarm`).

---

## 5. Scenario Demonstration Engine

Allows single-click cycling through 7 pre-programmed industrial scenarios:

1. **Scene 1: Normal monitoring**: Baseline operation (~35°C, ~0.10 m/s², valid cooling and guard).
2. **Scene 2: Weak warnings**: Gradual thermal rise and intermittent vibration spikes accumulating over ~25s.
3. **Scene 3: Cooling mismatch**: Fan commanded ON, but airflow feedback missing; temperature climbs toward stop threshold.
4. **Scene 4: Worker exposure**: Worker detected in monitored zone while equipment warnings exist (escalates to high risk).
5. **Scene 5: Sensor failure**: Temperature sensor fails (`temp_valid = false`), triggering `DEGRADED` health.
6. **Scene 6: Corrective action & recovery**: Restores healthy baseline; enables 15s recovery countdown.
7. **ML Pattern below fixed limits**: Temperature stays under 37°C and vibration under 0.22 m/s² (below rule limits), proving that the **Isolation Forest ML model** catches subtle anomalous patterns before rigid threshold limits trigger.
* **"Use manual Wokwi controls" (Scene 0)**: Switches from scripted profiles to direct manual potentiometer sliders in Wokwi.

---

## 6. Context & Protective Feedback

Displays operational context and interlock signals:

* **Operator-selected mode**: 
  * `PRODUCTION`: Machine expected to run.
  * `CLEANING` / `MAINTENANCE`: Machine required to remain safely stopped.
* **Cooling Command vs. Injected Airflow Feedback**: Verifies fan control output matches physical airflow confirmation.
* **Guard Feedback**: Safety enclosure micro-switch (`CLOSED` vs `OPEN`).
* **Person in Monitored Zone**: Live status from YOLO / external camera or simulation.
* **Presence Source**: `simulated` or `external YOLOv8 video stream`.
* **Motor Command / Wokwi Indicator**: Target command (`RUN` / `STOP`) vs. confirmed actuator status.

---

## 7. Warning Explanation & Retained Evidence

Explains the exact reasoning behind every alert:

* **Current Evidence**: Live triggers currently active on incoming telemetry (e.g. *"Temperature at or above 45 C"*, *"Isolation Forest flags unusual window"*).
* **Monitoring Faults**: Issues degrading system confidence (e.g. *"Temperature input missing"*, *"Telemetry delayed"*).
* **Evidence Retained in Open Episode**: Chronological audit memory of all issues that contributed to the current incident.

---

## 8. Sensor ML & Trend Analysis

Evaluates dynamic multi-variable relationships rather than single-point thresholds:

* **ML Status**: `NORMAL` (Green), `ANOMALY` (Red), `WARMUP` (Collecting initial 10-sample window), `UNAVAILABLE`.
* **Decision Score**: Anomaly distance score from the trained Isolation Forest boundary (`score < 0` = Anomaly).
* **Live Dual-Axis Rolling Chart**:
  * 🟠 **Orange Line**: Temperature (30–65 °C).
  * 🔵 **Blue Line**: Vibration RMS (0–1.0 m/s²).
* **Feature Vector**: Displays rolling mean temperature, temperature slope (°C/s), mean vibration, and max vibration.

---

## 9. Response Verification (Two-Way Handshake)

Industrial-grade closed-loop safety handshake:

```
[Dashboard Safety Engine] ──(Command ID)──► [Edge ESP32 Controller]
                                                  │
                                          (Execution & ACK)
                                                  │
[Dashboard Engine] ◄──(Feedback Confirmed)────────┘
```

* **Target State**: Commanded `RUN` or `STOP`.
* **Command ID**: Unique UUID / Nonce assigned to every state change.
* **Device Acknowledgement**: Confirms the edge controller received the command.
* **Actuator Feedback**: Reads independent physical feedback (not just software state).
* **Demo Deadline**: **8.0-second timeout**. If feedback fails to arrive within 8s, a **`Demo response unconfirmed`** critical alarm is raised.

---

## 10. Judge Fault Injection Panel

Test buttons that inject pipeline failures to demonstrate system resilience:

| Fault Button | Pipeline Behavior | Expected Observation |
|---|---|---|
| **Temperature missing** | Drops temperature reading before processing | ML unavailable; `DEGRADED` health |
| **Camera unavailable** | Invalidates worker vision stream | Exposure state unknown; recovery blocked |
| **Cooling feedback absent** | Drops airflow sensor feedback | Cooling mismatch warning; triggers stop at ≥55°C |
| **Telemetry delayed** | Holds packets in 8s buffer | Stale timeout triggers `DEGRADED` health |
| **Repeat last packet** | Replays duplicate sequence numbers | Duplicate packets rejected |
| **Acknowledgement missing** | Suppresses command ACK | Response marked `UNCONFIRMED` after 8s deadline |
| **Motor feedback unavailable** | Removes actuator confirmation | Verification fails; stop latched |
| **Feedback reports running** | Injects false running signal during stop | Unconfirmed stop safety alarm |
| **Clear Test Faults** | Restores clean pipeline input | Resets all test injection overrides |

---

## 11. Rules vs. Rules + ML Comparison Engine

A side-by-side verification matrix showing the value of hybrid AI:

* **Card 1: Explicit Rules**: Evaluates telemetry strictly against hardcoded thresholds (45°C, 60°C, 0.45 m/s²).
* **Card 2: Same Rules + ML Evidence**: Evaluates identical telemetry with the addition of the **Isolation Forest** anomaly model.
* **Download Comparison CSV**: Exports up to 10,000 historical samples with rule vs ML assessment metrics for evaluation reports.

---

## 12. Operator Response & 3-Step Recovery Workflow

To clear a latched `HIGH` risk and return to `NORMAL`:

```
Step 1: RESTORE NORMAL READINGS
  └─ Select Scene 1 / Normal Inputs (Temp < 45°C, Vibration < 0.30 m/s², Health AVAILABLE)
      │
Step 2: OPERATOR ACKNOWLEDGEMENT
  └─ Type corrective note (e.g., "Inspected and restored cooling") ➔ Click [Record action] ➔ Click [Acknowledge]
      │
Step 3: 15-SECOND SUSTAINED STABILITY
  └─ Status changes to RECOVERING ➔ 15s Countdown ➔ Episode becomes CLOSED (Risk returns to NORMAL)
      │
Step 4: RESTART
  └─ Click [Start / restart] to release motor latch and resume operation.
```

---

## 13. Persistent Episode History & Audit Trail

Located at the bottom of the dashboard:
* **SQLite Database Table**: Logs every incident episode with start time, peak risk level, corrective operator notes, response confirmation, and resolution timestamp.
* **Latest Recorded Events**: Expandable audit log detailing state transitions, threshold crossings, and operator interventions.
