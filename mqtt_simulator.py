"""Local MQTT sensor simulator — replaces Wokwi's ESP32 over the broker.

Publishes the same JSON telemetry that sketch.ino would, so the dashboard
runs in full MQTT mode with a live broker connection.  Ctrl+C to stop.
"""
import json, math, random, time, uuid, argparse
from pathlib import Path

def main():
    import paho.mqtt.client as mqtt

    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", default="test.mosquitto.org")
    parser.add_argument("--port", type=int, default=1883)
    args = parser.parse_args()

    topic_file = Path(__file__).parent / "topic.txt"
    if not topic_file.exists():
        raise SystemExit("Run  python configure_topic.py  first.")
    topic_base = topic_file.read_text().strip()

    telemetry_topic = f"{topic_base}/telemetry"
    control_topic   = f"{topic_base}/control"
    scenario_topic  = f"{topic_base}/scenario"

    session_id = uuid.uuid4().hex[:12]
    sequence = 0
    scene = 1
    scene_start = time.time()
    motor_command = False
    last_command_id = ""

    # --- MQTT setup -----------------------------------------------------------
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(client, userdata, flags, rc, properties=None):
        print(f"[OK] Connected to {args.broker}  topic={topic_base}")
        client.subscribe(control_topic)
        client.subscribe(scenario_topic)

    def on_message(client, userdata, msg):
        nonlocal motor_command, scene, scene_start, last_command_id
        try:
            payload = json.loads(msg.payload)
        except Exception:
            return
        if msg.topic == scenario_topic:
            scene = payload.get("scene", scene)
            scene_start = time.time()
            print(f"[SCENE] Changed to {scene}")
        elif msg.topic == control_topic:
            motor_command = payload.get("motor", motor_command)
            last_command_id = payload.get("command_id", "")
            print(f"[CTRL] motor={'RUN' if motor_command else 'STOP'}  cmd={last_command_id[:8]}")

    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Connecting to {args.broker}:{args.port} ...")
    client.connect(args.broker, args.port, keepalive=60)
    client.loop_start()
    time.sleep(1)

    # --- Scene profiles (mirrors sketch.ino) ----------------------------------
    def scene_inputs(t):
        """Return (temperature, vibration_rms, temp_valid, cooling_cmd,
                   cooling_fb, guard_closed, worker)"""
        if scene == 1:
            return 35 + 0.2*math.sin(t), 0.10 + 0.01*math.sin(t*0.7), True, True, True, True, False
        elif scene == 2:
            temp = 39 + min(t, 25)*0.5
            phase = int(t) % 8
            vib = 0.65 if 2 <= phase <= 4 else 0.10
            return temp, vib, True, True, True, True, False
        elif scene in (3, 4, 5):
            temp = 56 + 0.2*math.sin(t)
            worker = scene in (4, 5)
            temp_valid = scene != 5
            return temp, 0.65, temp_valid, True, False, True, worker
        elif scene == 6:
            return 34 + 0.15*math.sin(t), 0.08, True, False, True, True, False
        elif scene == 7:
            temp = 35 + min(t, 20)*0.054
            return temp, 0.22, True, True, True, True, False
        else:
            return 35, 0.10, True, True, True, True, False

    # --- Publish loop ---------------------------------------------------------
    try:
        while True:
            t = time.time() - scene_start
            temp, vib, temp_valid, cool_cmd, cool_fb, guard, worker = scene_inputs(t)

            # Add a little noise like the real sensors would
            if temp_valid:
                temp += random.gauss(0, 0.05)
            vib += random.gauss(0, 0.005)
            vib = max(0, vib)

            sequence += 1
            payload = {
                "session": session_id,
                "seq": sequence,
                "temperature_c": round(temp, 2) if temp_valid else None,
                "temperature_valid": temp_valid,
                "vibration_rms_ms2": round(vib, 4),
                "cooling_command": cool_cmd,
                "cooling_feedback": cool_fb,
                "guard_closed": guard,
                "worker_present": worker,
                "scene": scene,
                "source": "mqtt_simulator",
                "motor_feedback": motor_command,
                "motor_feedback_valid": True,
                "command_ack": last_command_id if last_command_id else None,
            }

            client.publish(telemetry_topic, json.dumps(payload))
            print(f"[TX] seq={sequence:4d}  scene={scene}  temp={payload['temperature_c']}  vib={payload['vibration_rms_ms2']}  motor={'RUN' if motor_command else 'STOP'}")
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\n[STOP] Simulator stopped.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
