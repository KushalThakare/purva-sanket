"""Configure matching Wokwi, native-Python and Docker MQTT settings."""
import argparse
import re
import secrets
from pathlib import Path
from backend.settings import valid_topic

DEFAULTS = {
    "PURVA_INPUT_MODE": "mqtt",
    "PURVA_MQTT_HOST": "test.mosquitto.org",
    "PURVA_MQTT_PORT": "1883",
    "PURVA_WEB_PORT": "8000",
}


def configure(root, topic=None, new=False):
    root = Path(root)
    topic_file, env_file = root/"topic.txt", root/".env"
    env_text = env_file.read_text(encoding="utf-8-sig") if env_file.exists() else ""
    existing = {}
    for line in env_text.splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            existing[key.strip()] = value.strip()
    if topic is None and not new:
        if topic_file.exists():
            topic = topic_file.read_text(encoding="utf-8-sig").strip()
        elif valid_topic(existing.get("PURVA_TOPIC", "")):
            topic = existing["PURVA_TOPIC"]
    if topic is None:
        topic = "purva-sanket/"+secrets.token_hex(8)
    if not valid_topic(topic):
        raise ValueError("Use purva-sanket/ followed by 8-64 letters, digits, underscores or hyphens. Replace placeholders; use --new to generate a new topic.")
    sketch = root/"wokwi"/"sketch.ino"
    text, count = re.subn(r'const char\* TOPIC_BASE = "[^"]+";',
                         f'const char* TOPIC_BASE = "{topic}";', sketch.read_text(encoding="utf-8-sig"))
    if count != 1:
        raise RuntimeError("Could not locate exactly one TOPIC_BASE in sketch.ino")
    # Keep comments, custom broker/port settings and unrelated environment keys.
    lines = [line for line in env_text.splitlines() if not re.match(r"\s*PURVA_TOPIC\s*=", line)]
    for key, value in DEFAULTS.items():
        if key not in existing:
            lines.append(f"{key}={value}")
    lines.append(f"PURVA_TOPIC={topic}")
    sketch.write_text(text, encoding="utf-8")
    topic_file.write_text(topic+"\n", encoding="utf-8")
    env_file.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return topic


def main():
    parser = argparse.ArgumentParser()
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--topic", help="Explicit team topic to use on both sides")
    options.add_argument("--new", action="store_true", help="Rotate the topic; update Wokwi afterward")
    args = parser.parse_args()
    try:
        topic = configure(Path(__file__).resolve().parent, args.topic, args.new)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print("Configured topic:", topic)
    print(".env and topic.txt are ready. Re-running this helper keeps the topic unless --new is used.")
    print("In Wokwi, replace TOPIC_BASE with this exact line:")
    print(f'const char* TOPIC_BASE = "{topic}";')
    print("Save and restart Wokwi, then run: docker compose up -d --build backend")
    print("Native Python alternative: python run.py --input mqtt")


if __name__ == "__main__":
    main()
