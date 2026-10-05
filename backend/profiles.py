"""Clearly labelled synthetic replay, also mirrored in the Wokwi firmware."""
import math


def profile(scene, step, session="offline-demo", seq=0):
    temp, vib, feedback, valid, worker = 35+.2*math.sin(step), .10+.01*math.sin(step*.7), True, True, False
    if scene == 2:
        temp = 39 + min(step, 25)*.5
        vib = .65 if int(step)%8 in (2,3,4) else .10
    elif scene in (3, 4, 5):
        temp, vib, feedback = 56+.2*math.sin(step), .65, False
        worker = scene in (4, 5)
        valid = scene != 5
    elif scene == 6:
        temp, vib, feedback, valid, worker = 35+.2*math.sin(step), .10+.01*math.sin(step*.7), True, True, False
    elif scene == 7:
        temp, vib = 35+min(step, 9)*.12, .22
    return {
        "device_id": "motor-01", "session_id": session, "seq": seq,
        "device_ts_ms": int(step*1000), "scene": scene,
        "temp_c": round(temp, 3) if valid else None, "temp_valid": valid,
        "vibration_rms_ms2": round(vib, 4), "vibration_valid": True,
        "cooling_command": True, "cooling_feedback": feedback,
        "guard_closed": True, "run_requested": True,
        "source": "offline synthetic replay", "motor_indicator": None,
        "worker_simulated": worker}
