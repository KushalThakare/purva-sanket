# PURVA SANKET — Physical Hardware Integration & Setup Guide

This guide details how to set up, wire, flash, and operate the **PURVA SANKET** predictive maintenance and machine safety monitoring system using physical sensors and an ESP32 microcontroller, streaming telemetry via MQTT to the local FastAPI backend and web dashboard.

---

## 1. Hardware Requirements & Checklist

- **Microcontroller**: ESP32 DevKit V1 (30-pin or 38-pin DevKitC / WROOM board)
- **Temperature Sensor**: LM35DZ precision centigrade temperature sensor (TO-92 package)
- **Vibration Sensor**: MPU-6050 (GY-521 3-axis accelerometer / gyroscope breakout)
- **Indicators / Actuators**:
  - 1x Red LED (Warning / Fault indicator)
  - 1x Green LED (Normal Running indicator)
  - 2x 220–330 Ω current-limiting resistors
  - 1x Active 3.3V / 5V Buzzer module (Emergency alarm)
  - Built-in ESP32 LED (GPIO 2) used for Motor state indication
- **Prototyping**: Solderless breadboard and jumper wires
- **Power & Data**: Micro-USB data cable connected to laptop

---

## 2. Complete Wiring Diagram & Pin Connections

### Sensors (Inputs)
| Component | Pin / Lead | ESP32 DevKit Pin | Function / Notes |
| :--- | :--- | :--- | :--- |
| **LM35DZ** | **Pin 1 (Left)** | **VIN / 5V** | 5V USB power *(flat face with text facing you)* |
| | **Pin 2 (Center)** | **GPIO 34** | Analog output (10 mV/°C) to ADC1 pin |
| | **Pin 3 (Right)** | **GND** | Sensor Ground |
| **MPU-6050** | **VCC** | **3V3** (or 5V) | Module power |
| | **GND** | **GND** | Module Ground |
| | **SDA** | **GPIO 21** | I2C Data line |
| | **SCL** | **GPIO 22** | I2C Clock line |

### Actuators (Outputs)
| Component | ESP32 Pin | Resistor | Function |
| :--- | :--- | :--- | :--- |
| **Red LED** | **GPIO 26** | 220–330 Ω to GND | Lights up on Warning, Degraded Health, or Local Critical Temp |
| **Green LED** | **GPIO 27** | 220–330 Ω to GND | Lights up when Motor is Running normally without active warnings |
| **Active Buzzer** | **GPIO 25** | Direct to GND | Sounds on Remote Alarm or Local Critical Temperature ($\ge 60^\circ\text{C}$) |
| **Motor Indicator** | **GPIO 2** | Built-in LED | Illuminates when Motor RUN command is active |

---

## 3. Step-by-Step Setup Guide

### Step 1: Python Environment Setup on Computer
1. Open PowerShell in the project directory:
   ```powershell
   cd purva-wokwi-starter
   ```
2. Create and activate a Python virtual environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Install required packages:
   ```powershell
   pip install -r requirements.txt
   ```

### Step 2: Install ESP32 Arduino Libraries
In **Arduino IDE** (or PlatformIO), install:
- `PubSubClient` by *Nick O'Leary*
- `ArduinoJson` by *Benoit Blanchon* (Version 7)
- `Adafruit MPU6050` by *Adafruit*
- `Adafruit Unified Sensor` by *Adafruit*

### Step 3: Configure and Flash Firmware
1. Open `wokwi/sketch.ino`.
2. Update your Wi-Fi credentials around line 13:
   ```cpp
   const char* WIFI_SSID     = "YOUR_WIFI_NAME";
   const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
   ```
3. Confirm the MQTT topic matches `topic.txt` and `.env` (`purva-sanket/bbc25cece3d0111e`).
4. Select board **ESP32 Dev Module** and the active **COM Port**.
5. Upload the sketch.
6. Open **Serial Monitor** at **115200 baud** to verify:
   ```text
   [MPU-6050] Initialized successfully.
   [WiFi] Connected! IP: 192.168.x.x
   [MQTT] Connecting... Connected!
   [Telemetry] LM35: 26.5 C | Vib RMS: 0.081 m/s2 | Motor: STOP
   ```

### Step 4: Run the Backend & Dashboard
Start the local server with MQTT mode enabled:
```powershell
python run.py --input mqtt
```

Open your browser at:
```
http://127.0.0.1:8000
```

---

## 4. Live Operational Features

- **Live Physical Telemetry**: Live temperature readings from the LM35DZ and 100 Hz 3-axis dynamic vibration RMS ($m/s^2$) from the MPU-6050 update continuously on the dashboard.
- **Fail-Safe Motor Control**: Click **Start / restart** on the dashboard. The backend validates safety conditions and transmits a confirmed RUN command over MQTT, turning the Green LED and ESP32 Motor LED ON.
- **Local Fallback Protection**: If the LM35DZ temperature reaches $\ge 60^\circ\text{C}$, the firmware triggers an emergency stop, sounds the Buzzer, and latches the Red LED immediately even if network connection is lost.
