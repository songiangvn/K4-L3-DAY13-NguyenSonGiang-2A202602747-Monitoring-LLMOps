from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts import build_dashboard

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_three_symptom_alerts_are_complete_and_have_runbooks() -> None:
    alerts = yaml.safe_load((REPO_ROOT / "config" / "alert_rules.yaml").read_text(encoding="utf-8"))["alerts"]
    runbook = (REPO_ROOT / "docs" / "alerts.md").read_text(encoding="utf-8")

    assert len(alerts) == 3
    for alert in alerts:
        for field in ("name", "severity", "condition", "duration", "owner", "slack_channel", "runbook"):
            assert alert.get(field) and "TODO" not in str(alert[field]), (alert.get("name"), field)
        assert alert["type"] == "symptom-based"
        assert alert["channel"] == "slack"
        assert alert["slack_channel"].startswith("#")
        assert alert["name"] in runbook


def test_dashboard_builder_computes_contract_aggregations(tmp_path: Path) -> None:
    rows = []
    for i in range(4):
        cid = f"req-0000000{i}"
        rows.append({"ts": f"2026-09-29T10:00:{i:02d}Z", "event": "request_received", "service": "api", "correlation_id": cid})
        if i == 3:
            rows.append({"ts": f"2026-09-29T10:00:{i:02d}Z", "event": "request_failed", "service": "api",
                         "error_type": "RuntimeError", "tool_name": "retrieval", "tool_success": False})
            continue
        rows.append({"ts": f"2026-09-29T10:00:{i:02d}Z", "event": "response_sent", "service": "api",
                     "latency_ms": 100 * (i + 1), "ttft_ms": 50, "tokens_in": 10, "tokens_out": 20,
                     "cost_usd": 0.001, "quality_score": 0.8, "tool_success": True})
    logs = tmp_path / "logs.jsonl"
    logs.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    records = build_dashboard.load_records(logs)
    start = min(r["_ts"] for r in records)
    panels = build_dashboard.compute_panels(records, build_dashboard.minute_buckets(records, start, 60), 60)

    assert panels["latency"]["values"]["p50"] == 200
    assert panels["traffic"]["values"]["count"] == 4
    assert panels["errors"]["values"]["error_rate_pct"] == 25.0
    assert panels["errors"]["values"]["tool_success_rate_pct"] == 75.0
    assert panels["errors"]["values"]["count_by_value"] == {"RuntimeError": 1}
    assert panels["cost"]["values"]["total"] == 0.003
    assert panels["tokens"]["values"]["tokens_out"] == 60
    assert panels["quality"]["values"]["mean"] == 0.8
