"""Same accepted inputs and protective rules; only ML evidence differs."""
import csv
import io
import json
import uuid


class ComparisonTracker:
    def __init__(self, connect):
        self.connect = connect
        self.current, self.key = None, None
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS comparison_runs (
              id TEXT PRIMARY KEY, started_at REAL NOT NULL, scene INTEGER,
              mode TEXT, device_session TEXT, sample_count INTEGER DEFAULT 0,
              rule_first_warning_at REAL, hybrid_first_warning_at REAL,
              rule_warning_samples INTEGER DEFAULT 0,
              hybrid_warning_samples INTEGER DEFAULT 0,
              rule_warning_events INTEGER DEFAULT 0,
              hybrid_warning_events INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS comparison_samples (
              id INTEGER PRIMARY KEY, run_id TEXT, received_at REAL,
              seq INTEGER, health TEXT, ml_status TEXT,
              rule_warning INTEGER, hybrid_warning INTEGER,
              critical_rule_stop INTEGER, rule_reasons_json TEXT,
              hybrid_reasons_json TEXT, injected_faults_json TEXT);
            """)
        self.last_rule = self.last_hybrid = False

    def record(self, packet, now, mode, result):
        key = (packet["session_id"], packet.get("scene", 0), mode)
        with self.connect() as db:
            if self.key != key:
                self.key = key
                run_id = str(uuid.uuid4())
                db.execute("""INSERT INTO comparison_runs(id,started_at,scene,mode,device_session)
                           VALUES(?,?,?,?,?)""", (run_id, now, key[1], mode, key[0]))
                self.current = dict(db.execute("SELECT * FROM comparison_runs WHERE id=?", (run_id,)).fetchone())
                self.last_rule = self.last_hybrid = False
            c = self.current
            rule, hybrid = result["rules"]["warning"], result["hybrid"]["warning"]
            c["sample_count"] += 1
            for prefix, value, prior in (("rule", rule, self.last_rule), ("hybrid", hybrid, self.last_hybrid)):
                c[prefix+"_warning_samples"] += int(value)
                c[prefix+"_warning_events"] += int(value and not prior)
                if value and c[prefix+"_first_warning_at"] is None:
                    c[prefix+"_first_warning_at"] = now
            self.last_rule, self.last_hybrid = rule, hybrid
            db.execute("""UPDATE comparison_runs SET sample_count=:sample_count,
                rule_first_warning_at=:rule_first_warning_at,hybrid_first_warning_at=:hybrid_first_warning_at,
                rule_warning_samples=:rule_warning_samples,hybrid_warning_samples=:hybrid_warning_samples,
                rule_warning_events=:rule_warning_events,hybrid_warning_events=:hybrid_warning_events WHERE id=:id""", c)
            db.execute("""INSERT INTO comparison_samples(run_id,received_at,seq,health,ml_status,
                rule_warning,hybrid_warning,critical_rule_stop,rule_reasons_json,
                hybrid_reasons_json,injected_faults_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (c["id"], now, packet["seq"], result["monitoring_health"], result["ml_status"],
                 int(rule), int(hybrid), int(result["critical_rule_stop"]),
                 json.dumps(result["rules"]["reasons"]), json.dumps(result["hybrid"]["reasons"]),
                 json.dumps(packet.get("injected_faults", []))))

    def snapshot(self, rules, hybrid, health, ml_status, critical):
        def path(reasons):
            level = max([r["level"] for r in reasons] or [0])
            return {"warning": bool(reasons),
                    "risk": ["NORMAL", "WATCH", "WARNING", "HIGH"][min(level, 3)],
                    "reasons": [r["text"] for r in reasons]}
        c = dict(self.current) if self.current else None
        difference = None
        if c and c["rule_first_warning_at"] is not None and c["hybrid_first_warning_at"] is not None:
            difference = round(c["rule_first_warning_at"]-c["hybrid_first_warning_at"], 3)
        if c:
            for prefix in ("rule", "hybrid"):
                first = c[prefix+"_first_warning_at"]
                c[prefix+"_first_warning_seconds"] = round(first-c["started_at"], 3) if first is not None else None
        return {"rules": path(rules), "hybrid": path(hybrid),
                "monitoring_health": health, "ml_status": ml_status,
                "critical_rule_stop": bool(critical), "run": c,
                "hybrid_lead_seconds": difference,
                "scope": "Current evidence on identical inputs; both retain the same explicit protective and health checks",
                "boundary": "Synthetic observations; warning counts are not factory accuracy or accident predictions"}

    def export_csv(self):
        with self.connect() as db:
            rows = db.execute("""SELECT run_id,received_at,seq,health,ml_status,rule_warning,
                hybrid_warning,critical_rule_stop,rule_reasons_json,hybrid_reasons_json,
                injected_faults_json FROM comparison_samples ORDER BY id DESC LIMIT 10000""").fetchall()
        out = io.StringIO(newline="")
        writer = csv.writer(out)
        writer.writerow(["run_id","received_at","seq","health","ml_status","rule_warning",
                         "hybrid_warning","critical_rule_stop","rule_reasons_json",
                         "hybrid_reasons_json","injected_faults_json"])
        writer.writerows(tuple(row) for row in reversed(rows))
        return out.getvalue()
