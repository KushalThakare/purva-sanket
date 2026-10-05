import json
import os
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
import paho.mqtt.client as mqtt
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from .engine import Engine
from .profiles import profile
from .settings import valid_topic
from .responses import simulated_response
from .faults import FAULT_LABELS

ROOT = Path(__file__).resolve().parents[1]


class Telemetry(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    device_id: Literal["motor-01"] = "motor-01"
    session_id: str = Field(min_length=1, max_length=80)
    seq: int = Field(ge=0)
    device_ts_ms: int = Field(default=0, ge=0)
    scene: int = Field(default=0, ge=0, le=7)
    temp_c: float | None = Field(default=None, ge=-55, le=125)
    temp_valid: bool
    vibration_rms_ms2: float | None = Field(default=None, ge=0, le=100)
    vibration_valid: bool = True
    cooling_command: bool
    cooling_feedback: bool
    guard_closed: bool = True
    run_requested: bool = True
    source: str = Field(default="synthetic HTTP input", max_length=80)
    motor_indicator: bool | None = None
    worker_simulated: bool = False
    response_protocol: int = Field(default=0, ge=0, le=1)
    ack_command_id: str | None = Field(default=None, max_length=80)
    feedback_command_id: str | None = Field(default=None, max_length=80)
    motor_feedback_valid: bool = False
    motor_feedback_running: bool | None = None
    motor_feedback_source: str = Field(default="Unavailable", max_length=100)


class Vision(BaseModel):
    present: bool
    valid: bool = True
    source: Literal["vision", "simulated"] = "vision"
    confidence: float | None = Field(default=None, ge=0, le=1)


class Action(BaseModel):
    kind: Literal["acknowledge", "corrective_action", "stop", "restart"]
    operator: str = Field(default="Demo operator", max_length=80)
    note: str = Field(default="", max_length=500)


class SceneSelection(BaseModel):
    scene: int = Field(ge=0, le=7)


class ModeSelection(BaseModel):
    mode: Literal["PRODUCTION", "CLEANING", "MAINTENANCE"]


class FaultSelection(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    enabled: bool


class Bridge:
    def __init__(self, engine, mode, topic):
        self.engine, self.mode, self.topic = engine, mode, topic
        self.connected = False
        self.last_error = ""
        self.stop_event = threading.Event()
        self.scene, self.step, self.seq = 1, 0, 0
        self.session = "replay-"+str(uuid.uuid4())
        self.client = None
        self.thread = None
        self.lock = threading.RLock()
        if mode == "mqtt":
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="purva-laptop-"+secrets.token_hex(4))
            self.client.on_connect = self.on_connect
            self.client.on_disconnect = self.on_disconnect
            self.client.on_message = self.on_message
            self.client.reconnect_delay_set(1, 15)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self.connected = not reason_code.is_failure
        if self.connected:
            client.subscribe(self.topic+"/telemetry", qos=1)
            self.last_error = ""
        else:
            self.last_error = str(reason_code)

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.connected = False

    def on_message(self, client, userdata, message):
        try:
            if len(message.payload) > 4096:
                raise ValueError("Oversized telemetry")
            packet = Telemetry.model_validate_json(message.payload).model_dump()
            self.engine.ingest(packet)
        except Exception as exc:
            self.last_error = "Rejected telemetry: "+str(exc)[:180]

    def start(self):
        if self.client:
            self.client.connect_async(os.getenv("PURVA_MQTT_HOST", "test.mosquitto.org"), int(os.getenv("PURVA_MQTT_PORT", "1883")), keepalive=30)
            self.client.loop_start()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def publish(self, suffix, payload):
        if self.client and self.connected:
            return self.client.publish(self.topic+suffix, json.dumps(payload), qos=1, retain=False).rc == mqtt.MQTT_ERR_SUCCESS
        return False

    def select_scene(self, scene):
        with self.lock:
            self.scene, self.step = scene, 0
        if self.mode == "mqtt":
            if not self.publish("/scenario", {"scene": scene}):
                raise ValueError("MQTT is not connected. Select the scene using Wokwi's buttons, or wait for the broker.")
        elif scene == 0:
            raise ValueError("Manual circuit controls are available in MQTT/Wokwi mode.")

    def run(self):
        while not self.stop_event.is_set():
            try:
                if self.mode == "offline":
                    control = self.engine.control_payload()
                    self.engine.mark_control_sent(control["command_id"])
                    with self.lock:
                        packet = profile(self.scene, self.step, self.session, self.seq)
                        self.step += 1
                        self.seq += 1
                    packet.update(simulated_response(control))
                    self.engine.ingest(Telemetry.model_validate(packet).model_dump())
                control = self.engine.control_payload()
                if self.publish("/control", control):
                    self.engine.mark_control_sent(control["command_id"])
            except Exception as exc:
                self.last_error = str(exc)[:180]
            self.stop_event.wait(1)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
        if self.client:
            self.client.disconnect()
            self.client.loop_stop()


@asynccontextmanager
async def lifespan(app):
    mode = os.getenv("PURVA_INPUT_MODE", "offline").lower()
    if mode not in ("offline", "mqtt"):
        raise ValueError("PURVA_INPUT_MODE must be offline or mqtt")
    topic = os.getenv("PURVA_TOPIC", "").strip().rstrip("/")
    if mode == "mqtt" and not valid_topic(topic):
        raise ValueError("Generate a unique PURVA_TOPIC with configure_topic.py, then copy TOPIC_BASE into Wokwi")
    app.state.engine = Engine(os.getenv("PURVA_DB", str(ROOT/"data"/"purva.db")))
    app.state.bridge = Bridge(app.state.engine, mode, topic)
    app.state.bridge.start()
    yield
    app.state.bridge.stop()


app = FastAPI(title="PURVA SANKET Simulation Demo", version="2.0.0-demo", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT/"frontend"), name="static")


@app.get("/")
def home():
    return FileResponse(ROOT/"frontend"/"index.html")


@app.get("/api/state")
def state():
    engine, bridge = app.state.engine, app.state.bridge
    return {**engine.evaluate(), "input_mode": bridge.mode,
            "mqtt_connected": bridge.connected, "bridge_error": bridge.last_error,
            "topic": bridge.topic}


@app.get("/api/health")
def health():
    # Container liveness is separate from sensor freshness and equipment risk.
    try:
        with app.state.engine.connect() as db:
            db.execute("SELECT 1").fetchone()
    except Exception as exc:
        raise HTTPException(503, "Database unavailable") from exc
    bridge = app.state.bridge
    return {"application": "running", "database": "reachable", "version": "2.0.0-demo",
            "input_mode": bridge.mode, "mqtt_connected": bridge.connected}


@app.get("/api/history")
def history():
    return app.state.engine.history()


@app.post("/api/telemetry")
def telemetry(packet: Telemetry):
    if app.state.bridge.mode == "offline":
        raise HTTPException(409, "Offline replay is active. Use MQTT mode for external telemetry.")
    return {"accepted": app.state.engine.ingest(packet.model_dump())}


@app.post("/api/vision")
def vision(observation: Vision):
    app.state.engine.update_vision(**observation.model_dump())
    return {"recorded": True}


@app.post("/api/vision/simulated")
def simulated_vision():
    app.state.engine.use_simulated_vision()
    return {"source": "simulated"}


@app.post("/api/action")
def action(request: Action):
    try:
        return app.state.engine.operator_action(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/scene")
def select_scene(request: SceneSelection):
    try:
        app.state.bridge.select_scene(request.scene)
        return {"requested_scene": request.scene}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/mode")
def mode(request: ModeSelection):
    app.state.engine.set_mode(request.mode)
    return {"mode": request.mode, "selected_by": "operator"}


@app.post("/api/fault")
def inject_fault(request: FaultSelection):
    if request.name not in FAULT_LABELS:
        raise HTTPException(422, "Unknown simulation fault")
    return app.state.engine.set_fault(request.name, request.enabled)


@app.post("/api/faults/clear")
def clear_faults():
    return app.state.engine.clear_faults()


@app.get("/api/comparison/export")
def export_comparison():
    return Response(app.state.engine.comparison.export_csv(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="purva_comparison.csv"'})
