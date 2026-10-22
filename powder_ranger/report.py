"""Session report: what happened, how fast, and whose session it was.

Reads a session's intent log (and optionally reflex_metrics.csv) and computes:
  - log integrity (chain + seal)
  - decisions: allowed / denied, by source and by reason
  - latency: packet age at the Governor (all sources), capture and inference
    time per reflex chunk (p50 / p90 / p99)
  - safety events: kill switch trips, watchdog neutrals, rejected messages
  - authorship: share of allowed output that came from the player, player
    commands issued, delegations granted and revoked
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np

from .governor.intent_log import load_or_create_log_key, verify_log, verify_seal


def _pct(xs: list[float]) -> dict:
    if not xs:
        return {}
    a = np.asarray(xs, dtype=float)
    return {"n": len(xs), "p50": round(float(np.percentile(a, 50)), 1),
            "p90": round(float(np.percentile(a, 90)), 1), "p99": round(float(np.percentile(a, 99)), 1),
            "max": round(float(a.max()), 1)}


def build_report(log_path: str | Path, metrics_path: str | Path | None = None,
                 seal_key: bytes | None = None) -> dict:
    log_path = Path(log_path)
    ok, n, _, problem = verify_log(log_path)
    seal_ok, seal_problem = verify_seal(log_path, seal_key or load_or_create_log_key()) if ok else (False, "chain broken")
    records = [json.loads(l)["record"] for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    start = next((r for r in records if r["kind"] == "session_start"), {})
    t0 = records[0]["t_wall"] if records else 0
    t1 = records[-1]["t_wall"] if records else 0
    intents = [r for r in records if r["kind"] == "intent"]
    allowed = [r for r in intents if r["allow"]]
    denied = [r for r in intents if not r["allow"]]

    def reason_key(r):
        reason = (r.get("reasons") or ["?"])[0]
        return reason.split(":")[0].split(" seq")[0].split(" (")[0][:48]

    player_allowed = [r for r in allowed if r["source"] == "player"]
    report = {
        "log": str(log_path),
        "integrity": {"chain_ok": ok, "records": n, "problem": problem, "seal_ok": seal_ok, "seal_problem": seal_problem},
        "session": {k: start.get(k) for k in ("adapter", "mode", "profile", "target_process", "pack_id",
                                               "pack_version", "pack_hash", "config_hash")},
        "duration_s": round(t1 - t0, 1),
        "decisions": {
            "allowed": len(allowed), "denied": len(denied),
            "allowed_by_source": dict(Counter(r["source"] for r in allowed)),
            "denied_by_reason": dict(Counter(reason_key(r) for r in denied).most_common()),
        },
        "latency_ms": {"packet_age_at_governor": _pct([r["age_ms"] for r in intents if "age_ms" in r])},
        "safety": {
            "kill_switch": [r.get("reason") for r in records if r["kind"] == "kill_switch"],
            "watchdog_neutral": sum(1 for r in records if r["kind"] == "watchdog"),
            "rejected_messages": sum(1 for r in records if r["kind"] == "rejected_message"),
        },
        "authorship": {
            "player_share_of_allowed_output": round(len(player_allowed) / len(allowed), 3) if allowed else None,
            "player_commands": [r.get("verb") for r in records if r["kind"] == "player_command"],
            "grants": [(r["delegation"]["scope"], r["delegation"].get("note", "")) for r in records
                       if r["kind"] == "grant" and not r.get("refused")],
            "revokes": sum(1 for r in records if r["kind"] == "revoke"),
        },
    }
    if metrics_path and Path(metrics_path).exists():
        rows = list(csv.DictReader(Path(metrics_path).open()))
        rows = [r for r in rows if t0 - 1 <= float(r["t_wall"]) <= t1 + 1]
        report["latency_ms"]["capture"] = _pct([float(r["capture_ms"]) for r in rows])
        report["latency_ms"]["inference"] = _pct([float(r["inference_ms"]) for r in rows])
        report["reflex_chunks"] = len(rows)
    return report


def format_report(r: dict) -> str:
    i, d, a, s = r["integrity"], r["decisions"], r["authorship"], r["safety"]
    lines = [
        f"Session {Path(r['log']).name}  ({r['duration_s']} s)",
        f"  integrity: chain {'OK' if i['chain_ok'] else 'BROKEN ' + i['problem']}, "
        f"seal {'OK' if i['seal_ok'] else 'NOT VERIFIED (' + i['seal_problem'] + ')'}",
        "  session:   " + ", ".join(f"{k}={v}" for k, v in r["session"].items() if v),
        f"  decisions: {d['allowed']} allowed {d['allowed_by_source']}, {d['denied']} denied",
    ]
    for reason, count in d["denied_by_reason"].items():
        lines.append(f"     denied {count:>5} x {reason}")
    for name, stats in r["latency_ms"].items():
        if stats:
            lines.append(f"  latency {name:<24} p50 {stats['p50']} / p90 {stats['p90']} / p99 {stats['p99']} ms (n={stats['n']})")
    lines.append(f"  safety:    kill switch {s['kill_switch'] or 'none'}, watchdog neutrals {s['watchdog_neutral']}, "
                 f"rejected messages {s['rejected_messages']}")
    share = a["player_share_of_allowed_output"]
    lines.append(f"  authorship: player share of output {'n/a' if share is None else f'{share:.0%}'}, "
                 f"commands {a['player_commands'] or 'none'}, grants {[g[0] for g in a['grants']] or 'none'}, "
                 f"revokes {a['revokes']}")
    return "\n".join(lines)
