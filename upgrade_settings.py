"""Copy an existing local demo's settings and data into a freshly extracted upgrade."""
import argparse
import shutil
from pathlib import Path
from configure_topic import configure


def upgrade(previous, target):
    previous, target = Path(previous).resolve(), Path(target).resolve()
    if previous == target:
        raise ValueError("Choose the old project and a separate freshly extracted upgrade folder.")
    if not (previous/"compose.yaml").is_file() or not (previous/"backend"/"engine.py").is_file():
        raise ValueError("The previous path must be the inner purva-wokwi-starter folder.")
    for folder in ("data", "media", "models"):
        destination = target/folder
        if (previous/folder).exists() and destination.exists() and any(destination.iterdir()):
            raise ValueError("The upgrade "+folder+" folder already contains files. Use a fresh extraction to preserve both copies.")
    for filename in (".env", "topic.txt"):
        source = previous/filename
        if source.is_file():
            shutil.copy2(source, target/filename)
    for folder in ("data", "media", "models"):
        if (previous/folder).is_dir():
            shutil.copytree(previous/folder, target/folder, dirs_exist_ok=True)
    topic = configure(target)
    print("Existing settings and available data copied into the upgrade.")
    print("The original project files are preserved.")
    print("Configured MQTT topic:", topic)
    print("Replace Wokwi sketch.ino AND diagram.json with the upgraded copies.")
    print("Then run: docker compose up -d --build backend")
    return topic


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="previous", required=True, help="Previous inner project directory")
    args = parser.parse_args()
    try:
        upgrade(args.previous, Path(__file__).resolve().parent)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
