# PURVA SANKET — Wokwi + AI + persistent safety episodes

**Version 2.0 demo:** response confirmation, eight judge fault tests, same-input
rules/ML comparison, CSV export and an additional below-limit pattern scenario.
For your already working Windows installation, follow [UPGRADE.md](UPGRADE.md).
For presenting the new features, follow [DEMO_GUIDE.md](DEMO_GUIDE.md).

This starter demonstrates one monitored machine zone without building physical hardware. Wokwi generates virtual sensor/test signals. A laptop runs the model, explicit demo safety rules, SQLite database and web dashboard.

**Docker on Windows:** start with [DOCKER_SETUP.md](DOCKER_SETUP.md). It contains Docker checks, matching topics, live Wokwi connectivity, persistent SQLite, the optional CPU YOLO video worker and offline fallback. Native Python instructions remain below.

## What is included

- `wokwi/sketch.ino`, `diagram.json`, `libraries.txt`: ESP32 circuit and firmware, sensor interfaces, labelled synthetic scenarios, alarm LEDs and motor-state indicator.
- `backend/app.py`: FastAPI endpoints and MQTT bridge.
- `backend/engine.py`: input freshness, warning memory, risk explanations, operator actions, recovery and a latched demo stop.
- `backend/ml.py`: Isolation Forest trained on reproducible synthetic normal windows.
- `backend/responses.py`: command IDs, publication/deadline, acknowledgement and simulated feedback confirmation.
- `backend/faults.py`: faults applied before normal ingestion; delayed and repeated packets cannot refresh health.
- `backend/comparison.py`: identical-input current-evidence comparison and persistent CSV observations.
- `backend/profiles.py`: local offline replay of the six scenarios plus the extra ML pattern.
- `frontend/`: working HTML/CSS/JavaScript dashboard. A React frontend can use the same endpoints later.
- `vision.py`: optional YOLO + ByteTrack on your own recorded video or laptop webcam.
- `Dockerfile`, `compose.yaml`: backend/dashboard/sensor ML with persistent SQLite; optional headless video worker.
- `configure_topic.py`: matching Wokwi, native Python and Docker settings; preserves a valid existing topic.
- `tools/`: read-only runtime and database checks.
- `tests/test_safety.py`: checks the full sequence, persistence, duplicate/stale inputs, camera loss, maintenance rules and interrupted recovery.

## 1. Run the dashboard first — no broker required

Install Python 3.11 or 3.12. Extract this folder and open a terminal inside it.

On Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

On macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

Open http://127.0.0.1:8000. Click **Start / restart** after valid normal input arrives. The initial motor command is STOP. All inputs in this mode are explicitly labelled **LOCAL REPLAY / SYNTHETIC INPUTS**. SQLite is automatically created at `data/purva.db`. No database account or separate database server is needed.

Keep the terminal running. Ctrl+C stops the backend. Run the same command again to prove an open episode survives a process restart.

## 2. Build the Wokwi circuit

Open https://wokwi.com/projects/new/esp32 and create/save a project named **PURVA SANKET Safety Simulation**.

Use a standard ESP32 DevKitC in this simulation. The camera pipeline runs on the laptop; this starter does not simulate ESP32-CAM camera frames in Wokwi.

Before copying the files, run the topic helper:

```powershell
.\.venv\Scripts\python.exe configure_topic.py
```

Use `.venv/bin/python` instead on macOS/Linux. This writes a unique topic into `topic.txt` and updates `wokwi/sketch.ino`. Copy the **updated** sketch, `diagram.json`, and `libraries.txt` into the matching Wokwi project tabs. Add a new `libraries.txt` tab if needed, or install the named libraries using Wokwi's Library Manager. Press Play.

The circuit contains:

| Part | Pin/connection | Meaning |
|---|---|---|
| Virtual DS18B20 | DQ → GPIO4; 4.7 kΩ pull-up to 3.3 V | Adjustable temperature in manual mode |
| Virtual MPU6050 | SDA → GPIO21; SCL → GPIO22 | Read acceleration through I²C |
| Potentiometer | SIG → GPIO34 | Amplitude of injected vibration waveform |
| Cooling-command switch | Common → GPIO13; left → GND | LEFT means commanded ON |
| Airflow-feedback switch | Common → GPIO14; left → GND | LEFT means injected feedback present |
| Temperature-availability switch | Common → GPIO32; left → GND | RIGHT injects missing temperature data |
| Guard-state switch | Common → GPIO33; left → GND | LEFT means guard closed |
| NEXT SCENE button | GPIO26 to GND | Cycles the six scripted scenes; shortcut N |
| Motor feedback override | Common → GPIO35, left → GND, 10 kΩ pull-up to 3V3 | LEFT normal; RIGHT injects running feedback in any scene |
| MANUAL button | GPIO25 to GND | Enables sliders and switches; shortcut M |
| Green / amber / red LEDs | GPIO16 / 17 / 18 with individual 330 Ω resistors | Normal observation / unresolved warning / degraded monitoring |
| Blue motor LED | GPIO19 with 330 Ω resistor | Represents demo machine command/indicator state |
| Orange cooling LED | GPIO23 with 330 Ω resistor | Cooling command; independent of feedback |
| Piezo buzzer | Positive → GPIO27; negative → GND | Brief audible warning pulses |

Power sensor VCC from ESP32 3.3 V and use common GND. Temperature, cooling and guard switches operate in **MANUAL** mode. Scripted scenes override those inputs using labelled test profiles. The GPIO35 motor-feedback override remains active in every scene. Watch Serial Monitor for JSON telemetry and connection messages.

The blue LED is an output indicator. There is no simulated DC motor heating, fan aerodynamics or mechanical vibration physics. The airflow switch is injected feedback, not a flow measurement. The firmware combines virtual MPU6050 readings with a synthetic sine waveform and computes acceleration RMS after removing the window mean. The potentiometer controls waveform amplitude in manual mode. These are tests of the data/decision pipeline.

## 3. Connect Wokwi and the laptop for free

Wokwi's default public gateway can make outgoing MQTT connections to the internet. Both Wokwi and the laptop connect to the public broker, so the broker relays data and replies over those established connections. The laptop's FastAPI URL is never accessed directly from Wokwi.

```text
Broker: test.mosquitto.org
Port: 1883 (public, unauthenticated test service)
Wi-Fi SSID in Wokwi: Wokwi-GUEST
Wi-Fi password: empty
Topic base: the unique value in topic.txt
```

| Topic suffix | Sender | Receiver | Payload |
|---|---|---|---|
| `/telemetry` | Wokwi | Laptop | Readings, validity, feedback, sequence, input source |
| `/control` | Laptop | Wokwi | Command ID, motor request, alarm, risk/fault indicators, restart nonce |
| `/scenario` | Laptop | Wokwi | Selected test scene, 0–7 |

Messages are not retained. Each device boot gets a session ID and sequence numbers. Duplicate and out-of-order readings do not refresh input health. The receiver timestamps arrivals on the laptop, rather than comparing the simulator clock with wall time.

Stop the offline server with Ctrl+C. Start MQTT mode:

```powershell
.\.venv\Scripts\python.exe run.py --input mqtt
```

Start Wokwi, keep its tab running, and reload the dashboard. Confirm **Broker connected** and **WOKWI / MQTT / SIMULATED INPUTS**. The scene selected on the dashboard must appear in subsequent telemetry. After the first valid normal packets, click **Start / restart** and check that the blue motor LED turns ON. Then select scene 3 and check that it turns OFF. The dashboard separates motor command and the device-reported indicator.

Only publish synthetic demo data on the public broker. Unique topics reduce accidental collisions; they are not authentication. Internet access is required in live MQTT mode, and some networks block port 1883. If the broker/network is unavailable, use the labelled offline replay. The free public gateway is documented as less stable than the paid private gateway; this is why the fallback is included.

## 4. Run all six scenarios

| Scene | What to do | What should appear |
|---|---|---|
| 1 — Normal | Select scene 1; wait for valid readings; click Start / restart | Valid monitoring; normal readings; model warms up over 10 samples |
| 2 — Weak warnings | Select scene 2 and leave it for roughly 25 seconds | Rising temperature and repeated vibration events; one open episode remembers the evidence |
| 3 — Cooling mismatch | Select scene 3 | Cooling command ON, feedback absent, temperature around 56 °C; explicit rule latches a demo stop |
| 4 — Worker exposure | Select scene 4 | Scripted worker presence joins the same episode; equipment warning also exists without a worker |
| 5 — Sensor failure | Select scene 5 | Temperature is Unavailable, monitoring is Degraded, ML is Unavailable; prior equipment evidence stays visible |
| 6 — Recovery | Select scene 6; acknowledge; record a corrective note | The model refills its valid window; sustained valid normal recovery runs for 15 seconds; episode closes; motor stays stopped until Start / restart |

Allow around 30 seconds for scene 6 after the last bad input, because a fresh 10-sample feature window is needed before the 15-second recovery period. If the model flags a later unusual window, recovery restarts. The timer is intentionally shown on the dashboard. Click **Acknowledge** during scene 5 to prove it cannot erase an unresolved warning.

Scene 4's person is a **scripted test observation** unless you start the separate vision script. In live vision mode, scene buttons never override camera observations. A person approaching an already stopped but still hot machine can still be relevant exposure evidence.

## 5. Add the actual computer-vision demonstration

Prepare your own short video showing a person entering and leaving a marked zone, or use an existing laptop webcam. Process it separately from Wokwi.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-vision.txt
.\.venv\Scripts\python.exe vision.py --source 0
```

For a local video:

```powershell
.\.venv\Scripts\python.exe vision.py --source "factory_demo.mp4" --zone 0.15 0.15 0.85 0.95
```

YOLO's person class supplies detections, ByteTrack supplies tracking, and a bounding-box footpoint inside the selected rectangle supplies presence. Zone coordinates are fractions of image width/height. This demonstrates 2D zone occupancy, not calibrated collision prediction or physical distance. The annotated video opens in a separate window. Presence results are posted to `/api/vision`, and the dashboard labels the source **YOLO / video or webcam**.

The first run downloads model weights and may install sizeable ML dependencies. Prepare it before presenting. Press Q to stop. A stopped/ended camera source is reported invalid, which degrades monitoring. Click **Use scripted presence** only when deliberately returning to a clearly labelled simulated presence demonstration.

## 6. Explain the AI and safety decisions

The Isolation Forest consumes a 10-sample valid window:

1. Mean temperature in °C.
2. Temperature slope in °C per second of observed arrivals.
3. Mean acceleration RMS in m/s².
4. Maximum acceleration RMS in m/s².

The starter trains separate models for operator-selected Production, Cleaning and Maintenance context on generated normal windows. This is working ML on synthetic data. It is not a factory-trained or factory-validated model, and its score is not a probability of an accident or a diagnosis.

Explicit demo rules remain active during model warm-up and mode changes:

| Condition | Demo behaviour |
|---|---|
| Temperature ≥45 °C | Equipment warning |
| Temperature ≥60 °C | Latched demo stop |
| Cooling commanded ON with feedback absent | Explain mismatch; raise warning |
| Temperature ≥55 °C plus that mismatch | Latched demo stop |
| Vibration ≥0.45 m/s²; below 0.30 re-arms | Record event crossing; three events in 60 seconds add recurrence evidence |
| Guard feedback open | Latched demo stop |
| Cleaning/Maintenance mode with run requested | Keep demo machine stopped; mode does not disable thermal rules |
| Required input invalid/missing, or no fresh observation for >6 seconds | Degraded monitoring; keep episode evidence and hold the demo output stopped |
| ML anomaly | Add unusual-pattern evidence; ML alone does not authorize a critical stop |
| Worker presence with equipment warning | Add exposure evidence; presence alone does not establish an equipment fault |

All numeric thresholds are illustrative test settings. Recovery additionally requires no current warning, valid normal ML, guard closed, valid cooling feedback where commanded, worker outside, acknowledgement and a recorded corrective action. No real equipment should be connected to this demo.

## 7. Database and endpoints

| SQLite table | What it preserves |
|---|---|
| `samples` | Input JSON, receiving timestamp, device/session/sequence identity |
| `assessments` | Risk, monitoring health, model result and current reasons against each sample |
| `episodes` | Machine/zone, opening/closure, severity, unresolved evidence, acknowledgement and corrective note |
| `events` | Evidence additions, recovery transitions, closure and operator actions |
| `actions` | Who acknowledged, recorded a correction, stopped or requested restart |
| `vision_observations` | Presence source, timestamp, confidence and validity |
| `settings` | Operator-selected context |
| `response_commands` | Command IDs, acknowledgement, feedback confirmation and demo deadlines |
| `comparison_runs` | Same-input comparison runs, first warnings and warning counts |
| `comparison_samples` | Per-input results for both paths, reasons and injected-fault labels |

Camera images are not written into SQLite by this starter. The app records observations. Episode history survives restarting Wokwi or restarting the backend. Freshness and feature windows are re-established after restart; the motor defaults to STOP.

Open http://127.0.0.1:8000/docs for FastAPI's interactive API page.

| Endpoint | Use |
|---|---|
| `GET /api/state` | Dashboard state and explanations |
| `GET /api/health` | Application/database reachability, separate from sensor health |
| `GET /api/history` | Episodes, events, actions and recent input records |
| `POST /api/vision` | Camera/presence observations |
| `POST /api/scene` | Request a scripted scenario |
| `POST /api/mode` | Select operating context |
| `POST /api/action` | Acknowledge, correction, stop or restart |
| `POST /api/fault` | Enable or disable a named judge fault test |
| `POST /api/faults/clear` | Clear session fault toggles without erasing warning history |
| `GET /api/comparison/export` | Download recorded comparison observations as CSV |

## 8. Presentation explanation

“We built a software prototype with Wokwi-generated IoT signals and a laptop decision pipeline. It combines task context, sensor trends, protective feedback and worker exposure. SQLite retains an unresolved warning episode even when monitoring becomes degraded. Explicit demo rules constrain the response, while AI adds pattern and presence evidence. We demonstrate the six scenarios and record acknowledgement, corrective action and valid recovery.”

If using offline replay or scripted person presence, identify those inputs on screen. Demonstrate live MQTT connectivity and actual video inference only after verifying them on your own machine. This simulation supports a design demonstration; it does not establish real factory performance or certified industrial protection.

## Primary technical references

- Wokwi Wi-Fi/gateway and MQTT: https://docs.wokwi.com/guides/esp32-wifi
- Wokwi supported components: https://docs.wokwi.com/getting-started/supported-hardware
- Virtual MPU6050: https://docs.wokwi.com/parts/wokwi-mpu6050
- Virtual DS18B20: https://docs.wokwi.com/parts/wokwi-ds18b20
- MQTT test broker: https://test.mosquitto.org/
- Paho MQTT client: https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html
- Isolation Forest: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html
- YOLO + ByteTrack: https://docs.ultralytics.com/modes/track/
- FastAPI: https://fastapi.tiangolo.com/tutorial/first-steps/

## Verification

See [TEST_RESULTS.md](TEST_RESULTS.md) for verification of this version. The test
suite covers the original scenes plus acknowledgement/feedback separation,
wrong command IDs, injected faults, the ML comparison, preservation of an old
database and a real local MQTT handshake. Actual Wokwi timing and optional video
inference also require checks on your presenting laptop.

Docker is unavailable in this execution environment, so the Docker images have not been built or started here. The local MQTT test does not verify Wokwi's public gateway or the user's Windows network. Actual YOLO inference has not been run on a user video. Complete the Docker, live Wokwi and video checks in DOCKER_SETUP.md on the presenting PC.

Run the backend checks with `python -m pip install -r requirements-dev.txt`, then `python -m pytest -q tests`. The MQTT test starts its own local broker and does not contact the public test service. Optional firmware compilation is configured in `platformio.ini`; install PlatformIO and run `pio run`. Actual Wokwi gateway/broker timing and your webcam/video still require the end-to-end checks on your presenting laptop.
