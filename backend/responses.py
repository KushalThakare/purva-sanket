"""Persisted command verification for a simulation, not physical stop proof."""
import json
import uuid


class ResponseVerifier:
    DEADLINE_SECONDS = 8

    def __init__(self, connect, clock):
        self.connect, self.clock = connect, clock
        self.current = None
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS response_commands (
              command_id TEXT PRIMARY KEY, device_session TEXT, episode_id TEXT,
              requested_running INTEGER NOT NULL, requested_at REAL NOT NULL,
              sent_at REAL, deadline_at REAL, acknowledged_at REAL,
              confirmed_at REAL, status TEXT NOT NULL, detail TEXT NOT NULL);
            """)
            # A new process issues a new STOP. Old acknowledgements cannot satisfy it.
            db.execute("UPDATE response_commands SET status='SUPERSEDED',detail=? WHERE status IN ('REQUESTED','ACKNOWLEDGED')",
                       ("Backend restarted; fresh stop confirmation required",))

    def save(self):
        c = self.current
        with self.connect() as db:
            db.execute("""INSERT OR REPLACE INTO response_commands VALUES
              (:command_id,:device_session,:episode_id,:requested_running,
               :requested_at,:sent_at,:deadline_at,:acknowledged_at,
               :confirmed_at,:status,:detail)""", c)

    def ensure(self, running, session, episode_id=None, force=False):
        c = self.current
        if force or c is None or c["requested_running"] != bool(running) or c["device_session"] != session:
            if c and c["status"] in ("REQUESTED", "ACKNOWLEDGED"):
                c["status"], c["detail"] = "SUPERSEDED", "A newer command replaces this request"
                self.save()
            self.current = {
                "command_id": str(uuid.uuid4()), "device_session": session,
                "episode_id": episode_id, "requested_running": bool(running),
                "requested_at": self.clock(), "sent_at": None, "deadline_at": None,
                "acknowledged_at": None, "confirmed_at": None,
                "status": "REQUESTED", "detail": "Waiting for command publication and matching feedback"}
            self.save()
        elif episode_id and not c["episode_id"]:
            c["episode_id"] = episode_id
            self.save()
        return self.current

    def mark_sent(self, command_id):
        c = self.current
        if c and c["device_session"] is not None and c["command_id"] == command_id and c["sent_at"] is None:
            c["sent_at"] = self.clock()
            c["deadline_at"] = c["sent_at"] + self.DEADLINE_SECONDS
            c["detail"] = "Published; waiting for matching acknowledgement and feedback"
            self.save()

    def observe(self, packet, fresh):
        c = self.current
        if not c:
            return
        before = dict(c)
        protocol = packet.get("response_protocol") == 1
        ack = fresh and protocol and packet.get("ack_command_id") == c["command_id"]
        feedback_matches = (fresh and protocol and
                            packet.get("feedback_command_id") == c["command_id"] and
                            packet.get("motor_feedback_valid") is True and
                            isinstance(packet.get("motor_feedback_running"), bool))
        confirmed = ack and feedback_matches and packet["motor_feedback_running"] == c["requested_running"]
        if ack and c["acknowledged_at"] is None:
            c["acknowledged_at"] = self.clock()
            if c["status"] != "CONFIRMED":
                c["status"] = "ACKNOWLEDGED"
        if confirmed:
            if c["confirmed_at"] is None or c["status"] != "CONFIRMED":
                c["confirmed_at"] = self.clock()
            c["status"] = "CONFIRMED"
            c["detail"] = "Matching acknowledgement and simulated motor feedback received"
        elif fresh and c["status"] == "CONFIRMED":
            c["status"] = "UNCONFIRMED"
            c["detail"] = "Previously confirmed feedback is no longer available or matching"
        elif c["deadline_at"] is not None and self.clock() >= c["deadline_at"]:
            c["status"] = "UNCONFIRMED"
            if not ack:
                c["detail"] = "Matching command acknowledgement missing at the demo deadline"
            elif not feedback_matches:
                c["detail"] = "Acknowledged; matching motor feedback missing at the demo deadline"
            else:
                c["detail"] = "Acknowledged; simulated motor feedback disagrees with the requested state"
        if c != before:
            self.save()

    def snapshot(self, packet, fresh):
        c = self.current
        if not c:
            return {"status": "REQUESTED", "confirmed": False}
        protocol = packet.get("response_protocol") == 1
        status = c["status"]
        if fresh and not protocol:
            status = "PROTOCOL_REQUIRED"
        elif not fresh and status == "CONFIRMED":
            status = "STALE_CONFIRMATION"
        feedback_valid = (fresh and protocol and packet.get("motor_feedback_valid") is True and
                          packet.get("feedback_command_id") == c["command_id"])
        return {**c, "status": status,
                "confirmed": status == "CONFIRMED" and feedback_valid,
                "feedback_running": packet.get("motor_feedback_running") if feedback_valid else None,
                "feedback_source": packet.get("motor_feedback_source", "Unavailable"),
                "protocol_available": protocol,
                "seconds_remaining": max(0, round(c["deadline_at"]-self.clock(), 1)) if c["deadline_at"] else None,
                "confirmation_seconds": round(c["confirmed_at"]-c["sent_at"], 3)
                    if c["confirmed_at"] is not None and c["sent_at"] is not None else None,
                "boundary": "Simulation feedback; this does not establish a physical or certified stop"}


def simulated_response(control, running=None):
    """Labelled replay device. Faults are applied separately at the input boundary."""
    return {
        "response_protocol": 1,
        "ack_command_id": control["command_id"],
        "feedback_command_id": control["command_id"],
        "motor_feedback_valid": True,
        "motor_feedback_running": bool(control["motor_on"]) if running is None else bool(running),
        "motor_feedback_source": "Offline simulated actuator feedback",
        "motor_indicator": bool(control["motor_on"]),
    }
