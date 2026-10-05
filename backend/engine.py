"""Explicit demo rules + independent input health + persistent warning episodes."""
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from collections import deque
from pathlib import Path
from .ml import score, models
from .responses import ResponseVerifier
from .faults import FaultInjector
from .comparison import ComparisonTracker

SCENES = {
    0: "Manual Wokwi inputs", 1: "Normal monitoring", 2: "Weak warnings",
    3: "Cooling mismatch", 4: "Worker exposure", 5: "Sensor failure",
    6: "Corrective action and recovery", 7: "ML pattern below fixed limits"}


class Engine:
    STALE_SECONDS = 6
    RECOVERY_SECONDS = 15

    def __init__(self, database, clock=time.time):
        self.clock = clock
        self.lock = threading.RLock()
        self.database = str(database)
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS samples (
              id INTEGER PRIMARY KEY, received_at REAL NOT NULL,
              device_id TEXT, session_id TEXT, seq INTEGER, packet_json TEXT,
              UNIQUE(device_id,session_id,seq));
            CREATE TABLE IF NOT EXISTS assessments (
              id INTEGER PRIMARY KEY, sample_id INTEGER, created_at REAL,
              risk TEXT, health TEXT, reasons_json TEXT, ml_json TEXT);
            CREATE TABLE IF NOT EXISTS episodes (
              id TEXT PRIMARY KEY, machine_id TEXT, zone_id TEXT,
              opened_at REAL, closed_at REAL, status TEXT,
              acknowledged INTEGER DEFAULT 0, corrective_note TEXT DEFAULT '',
              peak_level INTEGER DEFAULT 1, evidence_json TEXT DEFAULT '{}');
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY, episode_id TEXT, created_at REAL,
              kind TEXT, detail_json TEXT);
            CREATE TABLE IF NOT EXISTS actions (
              id INTEGER PRIMARY KEY, episode_id TEXT, created_at REAL,
              kind TEXT, operator TEXT, note TEXT, result TEXT);
            CREATE TABLE IF NOT EXISTS vision_observations (
              id INTEGER PRIMARY KEY, received_at REAL, observation_json TEXT);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE INDEX IF NOT EXISTS samples_time ON samples(received_at);
            """)
        self.mode = self.setting("mode", "PRODUCTION")
        self.stop_latched = True  # every backend start requires an explicit start
        self.restart_nonce = 0
        self.packet = None
        self.last_received = None
        self.current_session = None
        self.retired_sessions = set()
        self.last_seq = -1
        self.window = deque(maxlen=10)
        self.vibration_crossings = deque()
        self.vibration_high = False
        self.recovery_since = None
        self.vision = {"present": False, "valid": False, "source": "none", "at": 0}
        self.vision_external = False
        self.last_state = None
        self.injector = FaultInjector()
        self.responses = ResponseVerifier(self.connect, self.clock)
        self.comparison = ComparisonTracker(self.connect)
        self.response_failure = None
        self.force_command = False
        models()  # train reproducible demo models once

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def setting(self, key, default):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row[0] if row else default

    def active_episode(self):
        with self.connect() as db:
            row = db.execute("SELECT * FROM episodes WHERE closed_at IS NULL ORDER BY opened_at DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def event(self, episode_id, kind, detail):
        with self.connect() as db:
            db.execute("INSERT INTO events(episode_id,created_at,kind,detail_json) VALUES (?,?,?,?)",
                       (episode_id, self.clock(), kind, json.dumps(detail)))

    def ingest(self, packet):
        with self.lock:
            now = self.clock()
            packet, arrived_at = self.injector.transform(packet, now, self.packet)
            if packet is None:
                return False
            if now-arrived_at > self.STALE_SECONDS:
                self.injector.expired += 1
                return False  # a known locally delayed packet must not refresh health
            session = packet["session_id"]
            if session in self.retired_sessions:
                self.injector.rejected += 1
                return False
            if session == self.current_session and packet["seq"] <= self.last_seq:
                self.injector.rejected += 1
                return False
            with self.connect() as db:
                cursor = db.execute("INSERT OR IGNORE INTO samples(received_at,device_id,session_id,seq,packet_json) VALUES (?,?,?,?,?)",
                                    (now, packet["device_id"], session, packet["seq"], json.dumps(packet)))
                if cursor.rowcount == 0:
                    self.injector.rejected += 1
                    return False  # duplicates never refresh input freshness
                sample_id = cursor.lastrowid
            if session != self.current_session:
                if self.current_session is not None:
                    self.retired_sessions.add(self.current_session)
                self.window.clear()
                self.current_session = session
            if self.last_received is not None and now - self.last_received > self.STALE_SECONDS:
                self.window.clear()
            self.last_seq = packet["seq"]
            self.packet = packet
            self.last_received = now
            if packet["temp_valid"] and packet["vibration_valid"] and packet["temp_c"] is not None and packet["vibration_rms_ms2"] is not None:
                self.window.append((now, packet["temp_c"], packet["vibration_rms_ms2"]))
            else:
                self.window.clear()  # missing inputs never become zero-valued normal inputs
            v = packet.get("vibration_rms_ms2")
            if packet["vibration_valid"] and v is not None:
                if v >= .45 and not self.vibration_high:
                    self.vibration_crossings.append(now)
                    self.vibration_high = True
                elif v < .30:
                    self.vibration_high = False
            if "worker_simulated" in packet:
                # Pair scripted presence with this accepted packet. External
                # video observations take precedence and are never overwritten.
                self.update_vision(packet["worker_simulated"], source="simulated")
            state = self.evaluate()
            self.comparison.record(packet, now, self.mode, state["comparison"])
            with self.connect() as db:
                db.execute("INSERT INTO assessments(sample_id,created_at,risk,health,reasons_json,ml_json) VALUES (?,?,?,?,?,?)",
                           (sample_id, now, state["risk"], state["monitoring_health"],
                            json.dumps(state["current_evidence"]), json.dumps(state["ml"])))
            return True

    def update_vision(self, present, valid=True, source="simulated", confidence=None):
        with self.lock:
            if source == "vision":
                self.vision_external = True
            elif self.vision_external:
                return
            valid = valid and not self.injector.enabled["camera_missing"]
            self.vision = {"present": bool(present), "valid": bool(valid),
                           "source": source, "confidence": confidence, "at": self.clock()}
            with self.connect() as db:
                db.execute("INSERT INTO vision_observations(received_at,observation_json) VALUES (?,?)",
                           (self.clock(), json.dumps(self.vision)))

    def use_simulated_vision(self):
        with self.lock:
            self.vision_external = False

    def set_mode(self, mode):
        with self.lock:
            if self.mode != mode:
                self.mode = mode
                self.window.clear()
                self.recovery_since = None
                with self.connect() as db:
                    db.execute("INSERT OR REPLACE INTO settings VALUES('mode',?)", (mode,))
                self.event(None, "MODE_SELECTED", {"mode": mode, "selected_by": "operator"})

    def set_fault(self, name, enabled):
        with self.lock:
            self.injector.set(name, enabled)
            if name == "camera_missing" and enabled:
                self.vision["valid"] = False
            if name == "temperature_missing":
                self.window.clear()
            if name.startswith("response_"):
                self.stop_latched = True
                self.force_command = True
            ep = self.active_episode()
            self.event(ep["id"] if ep else None, "TEST_FAULT_CHANGED",
                       {"name": name, "enabled": bool(enabled), "source": "simulation fault panel"})
            return self.evaluate()

    def clear_faults(self):
        with self.lock:
            for name, enabled in list(self.injector.enabled.items()):
                if enabled:
                    self.set_fault(name, False)
            return self.evaluate()

    def control_payload(self):
        state = self.evaluate()
        return {"motor_on": state["motor_command"], "alarm": state["alarm"],
                "degraded": state["monitoring_health"] == "DEGRADED",
                "warning": state["episode"] is not None,
                "restart_nonce": state["restart_nonce"], "mode": state["mode"],
                "command_id": state["response"]["command_id"], "response_protocol": 1}

    def mark_control_sent(self, command_id):
        with self.lock:
            self.responses.mark_sent(command_id)

    def evaluate(self):
        with self.lock:
            now = self.clock()
            p = self.packet or {}
            fresh = self.last_received is not None and now - self.last_received <= self.STALE_SECONDS
            temp_ok = fresh and p.get("temp_valid", False) and p.get("temp_c") is not None
            vibration_ok = fresh and p.get("vibration_valid", False) and p.get("vibration_rms_ms2") is not None
            vision_ok = self.vision["valid"] and now - self.vision["at"] <= self.STALE_SECONDS
            faults = []
            if not fresh:
                faults.append("Telemetry missing or stale")
            if not temp_ok:
                faults.append("Temperature unavailable")
            if not vibration_ok:
                faults.append("Vibration unavailable")
            if not vision_ok:
                faults.append("Camera/presence observation unavailable")
            health = "AVAILABLE" if not faults else "DEGRADED"
            temperature = p.get("temp_c") if temp_ok else None
            vibration = p.get("vibration_rms_ms2") if vibration_ok else None
            while self.vibration_crossings and now - self.vibration_crossings[0] > 60:
                self.vibration_crossings.popleft()
            reasons = []
            def add(code, text, level=1):
                reasons.append({"code": code, "text": text, "level": level})
            critical = False
            if temperature is not None and temperature >= 60:
                add("hot", "Temperature at or above the 60 C demo stop threshold", 3)
                critical = True
            elif temperature is not None and temperature >= 45:
                add("warm", "Temperature at or above the 45 C demo warning threshold")
            if vibration is not None and vibration >= .45:
                add("vibration", "Vibration RMS above the demo reference band")
            if vibration_ok and vibration >= .30 and len(self.vibration_crossings) >= 3:
                add("recurrence", "At least three vibration crossings in the last 60 seconds")
            if fresh and p.get("cooling_command") and not p.get("cooling_feedback"):
                add("cooling", "Cooling commanded ON; injected airflow feedback is absent", 2)
                if temperature is not None and temperature >= 55:
                    add("cooling_stop", "Temperature >=55 C together with absent cooling feedback: demo stop", 3)
                    critical = True
            if fresh and not p.get("guard_closed", True):
                add("guard", "Guard feedback OPEN: demo stop", 3)
                critical = True
            if self.mode != "PRODUCTION" and fresh and p.get("run_requested", True):
                add("mode", f"{self.mode.title()} mode requires the demo machine to remain stopped", 2)
                critical = True
            ml = {"status": "WARMUP", "samples": len(self.window), "required": 10,
                  "training_source": "synthetic normal windows"}
            if not temp_ok or not vibration_ok:
                ml["status"] = "UNAVAILABLE"
            elif len(self.window) == 10:
                ml = score(list(self.window), self.mode)
                if ml["values"][1] >= .15:
                    add("trend", "Temperature is rising within the recent window")
            rule_reasons = list(reasons)
            if ml["status"] == "ANOMALY":
                add("ml", "Isolation Forest flags an unusual recent sensor window")
            episode = self.active_episode()
            if critical or health == "DEGRADED":
                self.stop_latched = True
            target = not self.stop_latched and health == "AVAILABLE" and self.mode == "PRODUCTION" and not critical
            self.responses.ensure(target, self.current_session,
                                  episode["id"] if episode else None, self.force_command)
            self.force_command = False
            self.responses.observe(p, fresh)
            response = self.responses.snapshot(p, fresh)
            if self.responses.current["status"] == "UNCONFIRMED":
                self.response_failure = self.responses.current["detail"]
                self.stop_latched = True
                if self.responses.current["requested_running"]:
                    self.responses.ensure(False, self.current_session, episode["id"] if episode else None)
                    response = self.responses.snapshot(p, fresh)
            if response["confirmed"] and not response["requested_running"]:
                self.response_failure = None
            if self.response_failure:
                add("response", "Demo response unconfirmed: "+self.response_failure, 3)
                rule_reasons.append(reasons[-1])
            if rule_reasons and vision_ok and self.vision["present"]:
                rule_reasons.append({"code": "exposure", "text":
                    "A person is inside the monitored zone while equipment warnings exist", "level": 3})
            if reasons and vision_ok and self.vision["present"]:
                add("exposure", "A person is inside the monitored zone while equipment warnings exist", 3)
            if reasons:
                if episode is None:
                    episode_id = str(uuid.uuid4())
                    with self.connect() as db:
                        db.execute("INSERT INTO episodes(id,machine_id,zone_id,opened_at,status) VALUES(?,?,?,?,?)",
                                   (episode_id, "motor-01", "zone-01", now, "OPEN"))
                    self.event(episode_id, "OPENED", {"source": p.get("source", "unknown")})
                    episode = self.active_episode()
                evidence = json.loads(episode["evidence_json"])
                for reason in reasons:
                    if reason["code"] not in evidence:
                        self.event(episode["id"], "EVIDENCE_ADDED", reason)
                    evidence[reason["code"]] = reason["text"]
                peak = max(episode["peak_level"], max(r["level"] for r in reasons))
                with self.connect() as db:
                    db.execute("UPDATE episodes SET evidence_json=?,peak_level=? WHERE id=?",
                               (json.dumps(evidence), peak, episode["id"]))
                episode = self.active_episode()
                self.responses.ensure(not self.stop_latched and health == "AVAILABLE" and self.mode == "PRODUCTION",
                                      self.current_session, episode["id"])
            # Explicit rules and degraded monitoring constrain the demo output.
            # An Isolation Forest anomaly or person detection alone never authorizes a stop.
            if critical or health == "DEGRADED":
                self.stop_latched = True
            eligible = (episode is not None and not reasons and health == "AVAILABLE"
                        and ml["status"] == "NORMAL" and temperature < 45
                        and vibration < .30 and p.get("guard_closed", False)
                        and (not p.get("cooling_command") or p.get("cooling_feedback"))
                        and not self.vision["present"]
                        and response["confirmed"] and not response["requested_running"]
                        and not self.injector.snapshot()["active"]
                        and episode["acknowledged"] and bool(episode["corrective_note"]))
            if eligible:
                if self.recovery_since is None:
                    self.recovery_since = now
                    self.event(episode["id"], "RECOVERY_STARTED", {})
                if now - self.recovery_since >= self.RECOVERY_SECONDS:
                    with self.connect() as db:
                        db.execute("UPDATE episodes SET status='CLOSED',closed_at=? WHERE id=?", (now, episode["id"]))
                    self.event(episode["id"], "CLOSED", {"valid_recovery_seconds": self.RECOVERY_SECONDS})
                    episode = None
                    self.recovery_since = None
                else:
                    with self.connect() as db:
                        db.execute("UPDATE episodes SET status='RECOVERING' WHERE id=?", (episode["id"],))
                    episode = self.active_episode()
            else:
                self.recovery_since = None
                if episode:
                    status = "ACKNOWLEDGED" if episode["acknowledged"] else "OPEN"
                    with self.connect() as db:
                        db.execute("UPDATE episodes SET status=? WHERE id=?", (status, episode["id"]))
                    episode["status"] = status
            level = max([r["level"] for r in reasons] + ([episode["peak_level"]] if episode else [0]))
            risk = ["NORMAL", "WATCH", "WARNING", "HIGH"][min(level, 3)]
            motor = not self.stop_latched and health == "AVAILABLE" and self.mode == "PRODUCTION" and not critical
            self.last_state = {
                "timestamp": now, "mode": self.mode,
                "source": p.get("source", "waiting"), "scene": p.get("scene", 0),
                "scene_name": SCENES.get(p.get("scene", 0), "Manual"),
                "temperature_c": temperature, "vibration_rms_ms2": vibration,
                "cooling_command": p.get("cooling_command") if fresh else None,
                "cooling_feedback": p.get("cooling_feedback") if fresh else None,
                "guard_closed": p.get("guard_closed") if fresh else None,
                "risk": risk, "monitoring_health": health, "faults": faults,
                "current_evidence": reasons, "episode": episode, "ml": ml,
                "vision": {**self.vision, "fresh": vision_ok},
                "motor_command": motor, "stop_latched": self.stop_latched,
                "motor_feedback": p.get("motor_indicator"),
                "alarm": bool((episode and not episode["acknowledged"]) or self.response_failure or critical),
                "recovery_seconds": int(now - self.recovery_since) if self.recovery_since is not None else 0,
                "recovery_required": self.RECOVERY_SECONDS,
                "telemetry_age_s": round(now-self.last_received, 1) if self.last_received is not None else None,
                "restart_nonce": self.restart_nonce}
            self.last_state["response"] = self.responses.snapshot(p, fresh)
            self.last_state["fault_injection"] = self.injector.snapshot()
            self.last_state["sample_seq"] = self.last_seq
            self.last_state["device_session"] = self.current_session
            self.last_state["comparison"] = self.comparison.snapshot(
                rule_reasons, reasons, health, ml["status"], critical or health == "DEGRADED" or bool(self.response_failure))
            return self.last_state

    def operator_action(self, kind, operator="Demo operator", note=""):
        with self.lock:
            state = self.evaluate()
            ep = self.active_episode()
            if kind == "restart":
                if (ep or state["monitoring_health"] != "AVAILABLE" or state["current_evidence"]
                    or self.mode != "PRODUCTION" or not state["response"]["confirmed"]
                    or state["response"]["requested_running"] or self.injector.snapshot()["active"]):
                    raise ValueError("Restart blocked: restore monitoring, clear test faults, resolve the episode and confirm STOP feedback first.")
                self.stop_latched = False
                self.restart_nonce += 1
            elif kind == "stop":
                self.stop_latched = True
                self.force_command = True
            elif kind in ("acknowledge", "corrective_action"):
                if not ep:
                    raise ValueError("There is no open episode.")
                if kind == "corrective_action" and not note.strip():
                    raise ValueError("Describe the corrective action before recording it.")
                with self.connect() as db:
                    if kind == "acknowledge":
                        db.execute("UPDATE episodes SET acknowledged=1 WHERE id=?", (ep["id"],))
                    else:
                        db.execute("UPDATE episodes SET corrective_note=? WHERE id=?", (note.strip(), ep["id"]))
            else:
                raise ValueError("Unknown action.")
            with self.connect() as db:
                db.execute("INSERT INTO actions(episode_id,created_at,kind,operator,note,result) VALUES(?,?,?,?,?,?)",
                           (ep["id"] if ep else None, self.clock(), kind, operator, note, "RECORDED"))
            self.event(ep["id"] if ep else None, "OPERATOR_ACTION", {"kind": kind, "note": note})
            return self.evaluate()

    def history(self):
        with self.lock, self.connect() as db:
            def rows(table, limit=100):
                order = "opened_at" if table == "episodes" else "id"
                return [dict(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY {order} DESC LIMIT ?", (limit,))]
            return {"episodes": rows("episodes", 30), "events": rows("events"),
                    "actions": rows("actions", 30), "samples": rows("samples", 60),
                    "response_commands": [dict(row) for row in db.execute(
                        "SELECT * FROM response_commands ORDER BY requested_at DESC LIMIT 30")],
                    "comparison_runs": [dict(row) for row in db.execute(
                        "SELECT * FROM comparison_runs ORDER BY started_at DESC LIMIT 30")]}
