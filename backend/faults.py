"""Session-only fault injection before normal ingestion and model processing."""
from collections import deque
from copy import deepcopy

FAULT_LABELS = {
    "temperature_missing": "Temperature input missing",
    "camera_missing": "Camera observation unavailable",
    "cooling_missing": "Cooling feedback absent",
    "telemetry_delayed": "Telemetry delayed by 8 seconds",
    "telemetry_repeated": "Repeated telemetry packet",
    "response_ack_missing": "Command acknowledgement missing",
    "response_feedback_missing": "Motor feedback unavailable",
    "response_feedback_running": "Motor feedback reports running",
}


class FaultInjector:
    DELAY_SECONDS = 8

    def __init__(self):
        self.enabled = {name: False for name in FAULT_LABELS}
        self.queue = deque(maxlen=256)
        self.received = self.withheld = self.expired = self.rejected = 0

    def set(self, name, enabled):
        if name not in self.enabled:
            raise ValueError("Unknown simulation fault")
        self.enabled[name] = bool(enabled)
        if name == "telemetry_delayed":
            self.queue.clear()

    def transform(self, packet, now, previous):
        self.received += 1
        p, at = deepcopy(packet), now
        if self.enabled["telemetry_delayed"]:
            self.queue.append((at, p))
            if not self.queue or self.queue[0][0] > now-self.DELAY_SECONDS:
                self.withheld += 1
                return None, at
            at, p = self.queue.popleft()
        if self.enabled["telemetry_repeated"] and previous:
            p = deepcopy(previous)
        if self.enabled["temperature_missing"]:
            p["temp_c"], p["temp_valid"] = None, False
        if self.enabled["cooling_missing"]:
            p["cooling_feedback"] = False
        if self.enabled["response_ack_missing"]:
            p["ack_command_id"] = None
        if self.enabled["response_feedback_missing"]:
            p["motor_feedback_running"], p["motor_feedback_valid"] = None, False
        if self.enabled["response_feedback_running"]:
            p["motor_feedback_running"], p["motor_feedback_valid"] = True, True
            p["motor_feedback_source"] = "Injected running-feedback test"
        p["injected_faults"] = [name for name, enabled in self.enabled.items() if enabled]
        return p, at

    def snapshot(self):
        return {"active": [name for name, enabled in self.enabled.items() if enabled],
                "labels": FAULT_LABELS, "enabled": dict(self.enabled),
                "received_packets": self.received, "withheld_packets": self.withheld,
                "expired_packets": self.expired, "rejected_packets": self.rejected,
                "boundary": "Injected test inputs; clearing faults does not clear warning history"}
