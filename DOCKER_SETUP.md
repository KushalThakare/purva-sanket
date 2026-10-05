# PURVA SANKET — Windows + Docker setup

Already running the previous starter? Follow **UPGRADE.md** first to copy your
settings and history, replace both Wokwi files and build version 2.0.
See **DEMO_GUIDE.md** for the new panels and the additional ML pattern.

The backend container runs the dashboard, FastAPI, Isolation Forest, safety rules
and SQLite. An optional second container runs YOLO + ByteTrack on a recorded video.

## Connection design

~~~mermaid
flowchart TD
    W["Wokwi ESP32"] <-->|"Telemetry and controls"| B["Public MQTT broker"]
    B <-->|"Outgoing MQTT connection"| A["Docker backend"]
    V["YOLO and ByteTrack video worker"] -->|"Zone observations"| A
    A --> M["Sensor ML and safety rules"]
    M --> E["Warning episodes and response"]
    E --> D["SQLite"]
    A <--> U["Browser dashboard"]
    E -->|"Alarm and motor request"| A
~~~

Both Wokwi and Docker connect outward to the same public broker. This works with
Wokwi's free public gateway. A broker running only on your laptop is not accessible
through that gateway. Your dashboard and database stay on your PC.

## 1. Check Docker

Start Docker Desktop and wait for its engine, then open Windows PowerShell:

~~~powershell
docker version
docker compose version
docker info --format '{{.OSType}}'
~~~

Expected: Client AND Server sections, a Compose version, and **linux**.
If the daemon is unavailable, start Docker Desktop. If the final command prints
windows, switch Docker Desktop to Linux containers. If Docker reports a WSL
problem, inspect its message and run **wsl --version**.

These commands check your PC. The assistant's execution environment is separate.

## 2. Open the updated project

Extract **Purva_Sanket_Wokwi_AI_Starter.zip** into a new directory. Open its inner
**purva-wokwi-starter** folder containing **compose.yaml**. In File Explorer's
address bar, type **powershell** and press Enter.

If the older starter already has useful readings, keep a backup of its **data**
folder and copy that folder into the new project before starting.

## 3. Match Wokwi and Docker settings

No Windows Python installation is needed. From the project folder, run:

~~~powershell
docker run --rm -v "$($PWD.Path):/workspace" -w /workspace python:3.12-slim-bookworm python configure_topic.py
~~~

The command downloads the official Python image if necessary, then runs the
bundled helper. It creates **.env** and **topic.txt**, updates **wokwi/sketch.ino**
and prints the exact **TOPIC_BASE** line to copy into Wokwi.

Replace the existing TOPIC_BASE line in your Wokwi sketch with that generated
line. Keep the diagram and installed libraries. Save and restart Wokwi.

Repeated helper runs keep a valid existing topic. Add **--new** only when you
intend to rotate it; update Wokwi again afterward.

| Setting | Wokwi | Docker .env |
|---|---|---|
| Broker | MQTT_HOST: test.mosquitto.org | PURVA_MQTT_HOST=test.mosquitto.org |
| Port | MQTT_PORT: 1883 | PURVA_MQTT_PORT=1883 |
| Topic | Generated TOPIC_BASE | Same generated PURVA_TOPIC |
| Wi-Fi | Wokwi-GUEST, empty password | Not applicable |

If you change broker or port, update both sides. This firmware uses plain MQTT;
changing its port alone does not enable TLS. A random topic is an identifier,
not authentication. Use simulated demo data on the public test service.

## 4. Start the dashboard, ML and database

~~~powershell
docker compose config
docker compose up -d --build backend
docker compose ps
docker compose logs --tail 50 backend
~~~

The first build downloads dependencies. Open:

- Dashboard: http://127.0.0.1:8000
- API documentation: http://127.0.0.1:8000/docs
- Application/database health: http://127.0.0.1:8000/api/health

SQLite is created automatically. No database account or separate database
container is required. Application health is separate from sensor health and risk.

## 5. Verify the connection in both directions

Keep Wokwi running in scene 1:

1. Serial Monitor prints **MQTT connected**.
2. The dashboard shows **WOKWI / MQTT** and **Broker connected**.
3. Last telemetry stays below **6 seconds** and readings change.
4. Wait for the 10-sample ML window and valid normal monitoring.
5. Click **Start / restart**. The dashboard shows RUN / ON and the blue Wokwi LED lights.
6. Select scene 3 on the dashboard. Wokwi prints Scene 3 selected. The backend
   explains cooling mismatch, opens an episode and sends STOP. The blue LED
   turns off; firmware local demo rules also constrain the output.

Broker connected alone does not prove telemetry delivery. A motor command and
the device-reported indicator are also separate fields.

After normal inputs arrive, run this read-only check:

~~~powershell
docker compose exec backend python tools/check_runtime.py
~~~

Expected: app reachable, broker connected, fresh telemetry and AVAILABLE health.
The diagnostic deliberately reports faults during scene 5 or a disconnect.

| MQTT suffix | Direction | Purpose |
|---|---|---|
| /telemetry | Wokwi to backend | Readings, validity, feedback, session and sequence |
| /control | Backend to Wokwi | Alarm, input health, motor request and command ID |
| /scenario | Dashboard/backend to Wokwi | Scene 0 through 7 |

## 6. Working AI and safety behavior

**Sensor ML:** a rolling window of 10 valid samples supplies temperature mean,
temperature slope, vibration RMS mean and maximum. Isolation Forest compares
these features with generated normal examples for Production, Cleaning or
Maintenance. The dashboard shows WARMUP, NORMAL, ANOMALY or UNAVAILABLE.

**Vision ML:** YOLO detects people, ByteTrack tracks them and bounding-box
footpoints supply occupancy in a defined 2D zone. The worker posts presence,
validity, source and confidence to the backend's **/api/vision** endpoint.

**Safety rules:** temperature, cooling mismatch, guard and input-health rules
remain active alongside AI. Equipment warnings and worker exposure join the same
episode. Missing readings remain unavailable rather than becoming normal zeros.

**Warning memory:** SQLite retains evidence. Acknowledgement records a response
without erasing warnings. Corrective action and sustained valid recovery can
close an episode; restart is a separate operator action.

Sensor models use synthetic training examples. This prototype does not establish
factory accuracy. An anomaly score or vision confidence is not an accident
probability. Motor response is an indicator-only simulation.

## 7. Database and persistence

The project's **data\purva.db** on Windows is mounted as **/app/data/purva.db**
inside Docker. The complete directory is shared, including SQLite WAL files.

~~~powershell
docker compose exec backend python tools/db_status.py
~~~

This prints table counts, the latest packet and recent episodes without changing them.

| Table | Stored information |
|---|---|
| samples | Accepted telemetry and arrival times |
| assessments | Risk, input health, ML results and reasons |
| episodes | Open/closed warnings, evidence and corrections |
| events | Evidence additions, recovery and closure |
| actions | Operator acknowledgement, correction, stop and restart |
| vision_observations | Presence, source, confidence, validity and time |
| settings | Operating context |

For the judges: open an episode in scene 3, note its ID, then run:

~~~powershell
docker compose restart backend
~~~

The same open episode remains after restart. Fresh windows rebuild, and the
motor stays stopped until required recovery and a separate restart.

Ordinary **docker compose down** removes containers while keeping your host data
folder. Keep that folder to preserve recorded history.

## 8. Optional YOLO + ByteTrack video inference

First get the Wokwi connection working. Prepare a clear staged recording of a
person entering and leaving the monitored zone. Wokwi does not supply camera frames.

~~~powershell
New-Item -ItemType Directory -Force media
~~~

Copy your video into **media** and name it **factory_demo.mp4**, then run:

~~~powershell
docker compose --profile vision up -d --build vision
docker compose logs -f vision
~~~

The optional image installs CPU PyTorch and tracking dependencies. Its initial
download is larger than the backend. The first successful run downloads weights
to **models/yolo11n.pt**. Prepare them before the event. A GPU is not required.

The worker loops the video, processes up to roughly 5 frames per second and posts
observations to **http://backend:8000/api/vision** inside Docker. CPU speed may
reduce playback/inference speed. It does not open a desktop preview window.

Dashboard **Presence source** changes to YOLO / video or webcam. Video observations
override scripted presence. SQLite stores observations, not frames.

The default normalized zone is **0.15 0.15 0.85 0.95**. To set a different zone:

~~~powershell
docker compose stop vision
docker compose run --rm vision python vision.py --source /media/factory_demo.mp4 --api http://backend:8000 --model /models/yolo11n.pt --headless --loop --zone 0.25 0.20 0.75 0.90
~~~

The video is independent of Wokwi's scene timeline. Use a clip with an outside-zone
interval for recovery. To return to scripted presence:

~~~powershell
docker compose stop vision
~~~

Then click **Use scripted presence** on the dashboard. Stopping video initially
flags that source unavailable; choosing scripted presence explicitly changes it.

For a Windows webcam and annotated preview, use the native Python instructions
in README.md and run **vision.py --source 0**. That Windows process posts to the
Docker backend at http://127.0.0.1:8000. The supplied Docker worker reads files;
it does not expose your Windows USB webcam automatically.

## 9. All six scenarios

| Scene | Result |
|---|---|
| 1 Normal | Valid monitoring, ML window, then Start / restart |
| 2 Weak warnings | Keep running until three vibration crossings appear; roughly 25-45 seconds depending on Wokwi speed |
| 3 Cooling mismatch | Explained mismatch and latched STOP |
| 4 Worker exposure | Occupancy adds exposure to the same episode |
| 5 Sensor failure | Degraded health; earlier warning evidence stays |
| 6 Recovery | Acknowledge, record correction, recovery, closure and separate restart |

For scripted scene 4, stop video and choose scripted presence. For actual
inference, show the YOLO source and let detections determine occupancy.

In scene 6, acknowledge and record **Restored cooling feedback and reconnected
the temperature input**. Allow roughly 30-45 seconds for the feature window and
15-second valid recovery, depending on Wokwi speed. Watch the recovery timer.
After closure, click Start / restart.

## 10. Troubleshooting and offline fallback

| Symptom | Check |
|---|---|
| Cannot open dashboard | Container status, backend logs, occupied port 8000 |
| Connected broker but no readings | Same topic, Wokwi Play, restart after sketch edits |
| Broker disconnected | Internet/DNS, broker status, network access to port 1883 |
| Red degraded LED | Fresh readings, guard, camera health and backend heartbeat |
| RUN command but indicator OFF | Wait for heartbeat; restore inputs; Stop then Start / restart |
| Sensor controls ignored | Select MANUAL / scene 0 |
| Cannot open video | Check media/factory_demo.mp4 exists and is a valid video |
| Recovery blocked | Reasons, valid normal ML, worker outside, acknowledgement and correction |

If port 8000 is occupied, set **PURVA_WEB_PORT=8001** in .env and run
**docker compose up -d backend**. Open http://127.0.0.1:8001.
Docker's internal port stays 8000; native vision would use **--api http://127.0.0.1:8001**.

If the public broker/network fails, run the labelled fallback:

~~~powershell
docker compose stop vision
docker compose -f compose.yaml -f compose.offline.yaml up -d --build backend
~~~

The dashboard displays **LOCAL REPLAY / SYNTHETIC INPUTS**. It demonstrates local
AI, rules and database while Wokwi stays independent. Use scripted presence if
video had previously been enabled.

To return to Wokwi, keep PURVA_INPUT_MODE=mqtt in .env and run:

~~~powershell
docker compose -f compose.yaml up -d backend
~~~

Ordinary shutdown:

~~~powershell
docker compose down
~~~

## Verification and primary references

See README.md for source/API/safety checks. Docker startup and actual video
inference must be verified with your PC, its Docker engine and your chosen video.

- Wokwi networking: https://docs.wokwi.com/guides/esp32-wifi
- Test broker: https://test.mosquitto.org/
- Docker on Windows: https://docs.docker.com/desktop/setup/install/windows-install/
- Compose: https://docs.docker.com/reference/cli/docker/compose/up/
- Bind mounts: https://docs.docker.com/engine/storage/bind-mounts/
- Profiles: https://docs.docker.com/compose/how-tos/profiles/
- YOLO tracking: https://docs.ultralytics.com/modes/track/
- CPU PyTorch: https://pytorch.org/get-started/locally/
