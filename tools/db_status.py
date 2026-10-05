"""Read the running demo database without requiring a separate database server."""
import argparse
import json
import os
from pathlib import Path
import sqlite3


def main():
    default = os.getenv("PURVA_DB", str(Path(__file__).resolve().parents[1]/"data"/"purva.db"))
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default=default)
    args = parser.parse_args()
    path = Path(args.database).resolve()
    if not path.is_file():
        parser.error("Database does not exist yet. Start the backend first.")
    with sqlite3.connect(path.as_uri()+"?mode=ro", uri=True, timeout=5) as db:
        db.row_factory = sqlite3.Row
        tables = ("samples", "assessments", "episodes", "events", "actions", "vision_observations", "settings",
                  "response_commands", "comparison_runs", "comparison_samples")
        counts = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}
        latest = db.execute("SELECT packet_json FROM samples ORDER BY id DESC LIMIT 1").fetchone()
        episodes = [dict(row) for row in db.execute(
            "SELECT id,status,opened_at,closed_at,acknowledged,corrective_note FROM episodes ORDER BY opened_at DESC LIMIT 5")]
    print(json.dumps({"database": str(path), "rows": counts,
                      "latest_packet": json.loads(latest[0]) if latest else None,
                      "latest_episodes": episodes}, indent=2))


if __name__ == "__main__":
    main()
