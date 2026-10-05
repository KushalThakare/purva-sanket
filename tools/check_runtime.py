"""Check app reachability and current input health; does not change demo state."""
import argparse
import json
import sys
import urllib.error
import urllib.request


def fetch(api, path):
    with urllib.request.urlopen(api.rstrip("/")+path, timeout=5) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    try:
        health = fetch(args.api, "/api/health")
        state = fetch(args.api, "/api/state")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print("Application check failed:", exc)
        return 1
    failures = []
    if health["database"] != "reachable":
        failures.append("Database is unavailable")
    if state["input_mode"] == "mqtt" and not state["mqtt_connected"]:
        failures.append("Public MQTT broker is disconnected")
    age = state["telemetry_age_s"]
    if age is None or age > 6:
        failures.append("No fresh telemetry: check Wokwi Play, topic match and broker/network")
    if state["monitoring_health"] != "AVAILABLE":
        failures.extend(state["faults"])
    report = {"application": "reachable", "input_mode": state["input_mode"],
              "broker_connected": state["mqtt_connected"], "topic": state["topic"],
              "telemetry_age_s": age, "source": state["source"],
              "scene": state["scene"], "monitoring_health": state["monitoring_health"],
              "sensor_ml": state["ml"]["status"], "motor_command": state["motor_command"],
              "motor_indicator": state["motor_feedback"], "issues": failures}
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
