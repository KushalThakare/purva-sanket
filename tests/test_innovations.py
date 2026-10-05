import csv
import io
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from backend.app import app, Bridge
from backend.engine import Engine
from backend.profiles import profile
from backend.responses import simulated_response
from test_safety import Clock, feed
from upgrade_settings import upgrade


@pytest.fixture
def setup(tmp_path):
    clock=Clock()
    return Engine(tmp_path/"innovation.db",clock),clock


def one(engine,clock,seq,scene=1,changes=None):
    clock.advance()
    control=engine.control_payload()
    engine.mark_control_sent(control["command_id"])
    packet=profile(scene,seq,seq=seq)
    packet.update(simulated_response(control))
    packet.update(changes or {})
    engine.ingest(packet)
    return engine.evaluate()


def test_acknowledgement_without_feedback_never_confirms_stop(setup):
    engine,clock=setup
    feed(engine,clock,1,12)
    engine.set_fault("response_feedback_missing",True)
    for seq in range(12,24):
        state=one(engine,clock,seq)
    assert state["response"]["acknowledged_at"] is not None
    assert state["response"]["status"] == "UNCONFIRMED"
    assert state["response"]["feedback_running"] is None
    assert not state["motor_command"] and state["stop_latched"]
    assert "response" in json.loads(state["episode"]["evidence_json"])
    engine.operator_action("acknowledge")
    assert engine.evaluate()["alarm"]  # acknowledgement cannot silence an unresolved response failure
    with pytest.raises(ValueError):
        engine.operator_action("restart")


@pytest.mark.parametrize("fault",["response_ack_missing","response_feedback_running"])
def test_response_faults_latch_stop_and_require_recovery(setup,fault):
    engine,clock=setup
    feed(engine,clock,1,12)
    engine.set_fault(fault,True)
    for seq in range(12,24):
        state=one(engine,clock,seq)
    assert state["response"]["status"] == "UNCONFIRMED"
    episode_id=state["episode"]["id"]
    engine.clear_faults()
    state=one(engine,clock,24)
    assert state["response"]["confirmed"]
    assert state["episode"]["id"] == episode_id
    engine.operator_action("acknowledge")
    engine.operator_action("corrective_action",note="Restored simulated actuator feedback")
    state=feed(engine,clock,6,35,25)
    assert state["episode"] is None
    assert not state["motor_command"]
    engine.operator_action("restart")
    assert engine.evaluate()["motor_command"]


def test_wrong_command_id_and_duplicate_ack_are_rejected(setup):
    engine,clock=setup
    feed(engine,clock,1,12)
    old=engine.responses.current["command_id"]
    engine.operator_action("stop")
    for seq in range(12,24):
        state=one(engine,clock,seq,changes={"ack_command_id":old,"feedback_command_id":old})
    assert state["response"]["status"] == "UNCONFIRMED"
    packet=profile(1,0,seq=23)
    packet.update(simulated_response(engine.control_payload()))
    assert not engine.ingest(packet)
    assert not engine.evaluate()["response"]["confirmed"]


def test_repeated_and_delayed_packets_do_not_refresh_health(setup):
    engine,clock=setup
    feed(engine,clock,1,12)
    engine.set_fault("telemetry_repeated",True)
    for seq in range(12,22):
        one(engine,clock,seq)
    assert engine.evaluate()["monitoring_health"] == "DEGRADED"
    assert engine.evaluate()["cooling_feedback"] is None
    assert engine.evaluate()["guard_closed"] is None
    assert engine.injector.rejected == 10
    engine.clear_faults()
    state=one(engine,clock,22)
    assert state["monitoring_health"] == "AVAILABLE"
    engine.set_fault("telemetry_delayed",True)
    for seq in range(23,36):
        one(engine,clock,seq)
    assert engine.evaluate()["monitoring_health"] == "DEGRADED"
    assert engine.injector.withheld > 0 and engine.injector.expired > 0
    engine.clear_faults()
    assert one(engine,clock,36)["monitoring_health"] == "AVAILABLE"


@pytest.mark.parametrize("fault",["temperature_missing","camera_missing","cooling_missing"])
def test_input_faults_enter_processing_and_preserve_warning(setup,fault):
    engine,clock=setup
    state=feed(engine,clock,3,12)
    episode=state["episode"]["id"]
    engine.set_fault(fault,True)
    state=one(engine,clock,12)
    if fault=="temperature_missing":
        assert state["temperature_c"] is None and state["ml"]["status"]=="UNAVAILABLE"
    elif fault=="camera_missing":
        assert not state["vision"]["fresh"]
    else:
        assert not state["cooling_feedback"]
        assert "cooling" in [r["code"] for r in state["current_evidence"]]
    assert state["episode"]["id"]==episode
    engine.clear_faults()
    assert engine.active_episode()["id"]==episode


def test_same_input_comparison_exposes_ml_contribution_and_exports(setup):
    engine,clock=setup
    feed(engine,clock,1,12)
    state=feed(engine,clock,7,15,12)
    c=state["comparison"]
    assert not c["rules"]["warning"] and c["hybrid"]["warning"]
    assert state["ml"]["status"]=="ANOMALY"
    assert c["run"]["rule_warning_samples"]==0
    assert c["run"]["hybrid_warning_samples"]>0
    assert c["hybrid_lead_seconds"] is None  # no invented time advantage
    rows=list(csv.DictReader(io.StringIO(engine.comparison.export_csv())))
    assert len(rows)==27 and rows[-1]["rule_warning"]=="0" and rows[-1]["hybrid_warning"]=="1"
    state=feed(engine,clock,3,3,27)
    assert state["comparison"]["rules"]["warning"]
    assert state["comparison"]["hybrid"]["warning"]
    assert state["comparison"]["critical_rule_stop"]


def test_fresh_stop_confirmation_is_required_after_backend_restart(setup):
    engine,clock=setup
    feed(engine,clock,1,12)
    old=engine.responses.current["command_id"]
    restored=Engine(engine.database,clock)
    clock.advance()
    packet=profile(1,0,seq=12)
    packet.update(simulated_response({"command_id":old,"motor_on":False}))
    restored.ingest(packet)
    assert not restored.evaluate()["response"]["confirmed"]
    with pytest.raises(ValueError):
        restored.operator_action("restart")
    assert restored.history()["response_commands"]


def test_old_database_migration_preserves_existing_episode(tmp_path):
    database=tmp_path/"old.db"
    with sqlite3.connect(database) as db:
        db.execute("""CREATE TABLE episodes (id TEXT PRIMARY KEY,machine_id TEXT,zone_id TEXT,
            opened_at REAL,closed_at REAL,status TEXT,acknowledged INTEGER DEFAULT 0,
            corrective_note TEXT DEFAULT '',peak_level INTEGER DEFAULT 1,evidence_json TEXT DEFAULT '{}')""")
        db.execute("INSERT INTO episodes(id,machine_id,zone_id,opened_at,status,evidence_json) VALUES(?,?,?,?,?,?)",
                   ("old-episode","motor-01","zone-01",1000,"OPEN",'{"cooling":"Earlier cooling warning"}'))
    engine=Engine(database,Clock())
    assert engine.active_episode()["id"]=="old-episode"
    assert json.loads(engine.active_episode()["evidence_json"])["cooling"]=="Earlier cooling warning"
    assert engine.evaluate()["stop_latched"]


def test_fault_api_and_csv_endpoints(tmp_path,monkeypatch):
    monkeypatch.setenv("PURVA_INPUT_MODE","mqtt")
    monkeypatch.setenv("PURVA_TOPIC","purva-sanket/fault-api-1234")
    monkeypatch.setenv("PURVA_DB",str(tmp_path/"api.db"))
    monkeypatch.setattr(Bridge,"start",lambda self:None)
    with TestClient(app) as client:
        assert client.post("/api/fault",json={"name":"unknown","enabled":True}).status_code==422
        assert client.post("/api/fault",json={"name":"temperature_missing","enabled":True}).status_code==200
        client.post("/api/telemetry",json=profile(1,0,seq=0)).raise_for_status()
        state=client.get("/api/state").json()
        assert state["temperature_c"] is None
        assert state["response"]["status"]=="PROTOCOL_REQUIRED"
        assert client.post("/api/faults/clear",json={}).json()["fault_injection"]["active"]==[]
        response=client.get("/api/comparison/export")
        assert response.status_code==200 and response.headers["content-type"].startswith("text/csv")
        assert "rule_warning" in response.text


def test_upgrade_copies_existing_settings_and_quiescent_data(tmp_path):
    previous,target=tmp_path/"previous",tmp_path/"updated"
    (previous/"backend").mkdir(parents=True)
    (previous/"backend"/"engine.py").write_text("# previous code")
    (previous/"compose.yaml").write_text("name: purva-sanket")
    (previous/".env").write_text("# custom settings\nPURVA_WEB_PORT=8001\nPURVA_TOPIC=purva-sanket/preserved-1234\nCUSTOM_SETTING=keep\n")
    (previous/"data").mkdir()
    (previous/"data"/"purva.db").write_bytes(b"existing history")
    (target/"wokwi").mkdir(parents=True)
    (target/"wokwi"/"sketch.ino").write_text('const char* TOPIC_BASE = "purva-sanket/REPLACE_WITH_RANDOM_TEAM_ID";\n')
    assert upgrade(previous,target)=="purva-sanket/preserved-1234"
    assert (target/"data"/"purva.db").read_bytes()==b"existing history"
    assert (previous/"data"/"purva.db").read_bytes()==b"existing history"
    assert "PURVA_WEB_PORT=8001" in (target/".env").read_text()
    assert "CUSTOM_SETTING=keep" in (target/".env").read_text()
    assert "preserved-1234" in (target/"wokwi"/"sketch.ino").read_text()


def test_upgrade_refuses_to_overwrite_populated_destination(tmp_path):
    previous,target=tmp_path/"previous",tmp_path/"updated"
    for folder in (previous/"backend",previous/"data",target/"data"):
        folder.mkdir(parents=True)
    (previous/"compose.yaml").write_text("name: purva-sanket")
    (previous/"backend"/"engine.py").write_text("# previous")
    (target/"data"/"purva.db").write_bytes(b"new history")
    with pytest.raises(ValueError,match="already contains"):
        upgrade(previous,target)
    assert (target/"data"/"purva.db").read_bytes()==b"new history"
