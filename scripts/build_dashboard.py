"""Render the 6-panel dashboard defined in config/dashboard.yaml from data/logs.jsonl.

    python scripts/build_dashboard.py                      # -> reports/dashboard.html
    python scripts/build_dashboard.py --out other.html

The window is the contract's time_range_minutes (60), ending at the newest log event so
the page can be regenerated later for evidence. Panels are bucketed per minute; each
panel shows its headline aggregations, unit, threshold and pass/breach status.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio
from app.metrics import percentile

SERIES_VARS = ["--series-1", "--series-2", "--series-3", "--series-4"]


# ---------- data ----------

def load_records(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            rec["_ts"] = datetime.fromisoformat(rec["ts"].replace("Z", "+00:00"))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
        records.append(rec)
    return records


def minute_buckets(records: list[dict], start: datetime, minutes: int) -> list[list[dict]]:
    buckets: list[list[dict]] = [[] for _ in range(minutes)]
    for rec in records:
        idx = int((rec["_ts"] - start).total_seconds() // 60)
        if 0 <= idx < minutes:
            buckets[idx].append(rec)
    return buckets


def by_event(records: list[dict], *events: str) -> list[dict]:
    return [r for r in records if r.get("event") in events]


def safe_pct(num: int, den: int) -> float | None:
    return round(num / den * 100, 2) if den else None


def retrieval_success_pct(records: list[dict]) -> float | None:
    flags = [r["tool_success"] for r in records if r.get("tool_success") is not None]
    return safe_pct(sum(1 for f in flags if f is True), len(flags))


def compute_panels(records: list[dict], buckets: list[list[dict]], minutes: int) -> dict:
    sent = by_event(records, "response_sent")
    received = by_event(records, "request_received")
    failed = by_event(records, "request_failed")
    lat = [r["latency_ms"] for r in sent]
    ttft = [r["ttft_ms"] for r in sent]
    active_minutes = sum(1 for b in buckets if by_event(b, "request_received")) or 1

    def per_minute(fn):
        return [fn(b) for b in buckets]

    def pct_fn(field, p):
        return lambda b: (percentile([r[field] for r in by_event(b, "response_sent")], p)
                          if by_event(b, "response_sent") else None)

    return {
        "latency": {
            "values": {"p50": percentile(lat, 50), "p95": percentile(lat, 95),
                       "p99": percentile(lat, 99), "ttft_p95": percentile(ttft, 95)},
            "series": {"P50": per_minute(pct_fn("latency_ms", 50)),
                       "P95": per_minute(pct_fn("latency_ms", 95)),
                       "P99": per_minute(pct_fn("latency_ms", 99)),
                       "TTFT P95": per_minute(pct_fn("ttft_ms", 95))},
            "kind": "line",
        },
        "traffic": {
            "values": {"count": len(received),
                       "rate_per_minute": round(len(received) / active_minutes, 2)},
            "series": {"Requests": per_minute(lambda b: len(by_event(b, "request_received")) or None)},
            "kind": "bar",
        },
        "errors": {
            "values": {"error_rate_pct": safe_pct(len(failed), len(received)) or 0.0,
                       "count_by_value": dict(Counter(r.get("error_type") for r in failed)),
                       "tool_success_rate_pct": retrieval_success_pct(records)},
            "series": {"Error rate": per_minute(lambda b: safe_pct(len(by_event(b, "request_failed")),
                                                                  len(by_event(b, "request_received")))),
                       "Retrieval success": per_minute(retrieval_success_pct)},
            "kind": "line",
        },
        "cost": {
            "values": {"total": round(sum(r["cost_usd"] for r in sent), 6),
                       "sum_by_minute": round(max((sum(r["cost_usd"] for r in by_event(b, "response_sent"))
                                                   for b in buckets), default=0.0), 6)},
            "series": {"Cost": per_minute(lambda b: round(sum(r["cost_usd"] for r in by_event(b, "response_sent")), 6)
                                          if by_event(b, "response_sent") else None)},
            "kind": "bar",
        },
        "tokens": {
            "values": {"sum_by_field": max(sum(r["tokens_in"] for r in sent), sum(r["tokens_out"] for r in sent)),
                       "tokens_in": sum(r["tokens_in"] for r in sent),
                       "tokens_out": sum(r["tokens_out"] for r in sent)},
            "series": {"Input": per_minute(lambda b: sum(r["tokens_in"] for r in by_event(b, "response_sent")) or None),
                       "Output": per_minute(lambda b: sum(r["tokens_out"] for r in by_event(b, "response_sent")) or None)},
            "kind": "line",
        },
        "quality": {
            "values": {"mean": round(mean(r["quality_score"] for r in sent), 3) if sent else None},
            "series": {"Mean quality": per_minute(lambda b: round(mean(r["quality_score"] for r in by_event(b, "response_sent")), 3)
                                                  if by_event(b, "response_sent") else None)},
            "kind": "line",
        },
    }


def threshold_ok(value, operator: str, limit: float) -> bool | None:
    if value is None:
        return None
    return value <= limit if operator == "lte" else value >= limit


# ---------- rendering ----------

def fmt(value, unit: str = "") -> str:
    if value is None:
        return "–"
    if isinstance(value, dict):
        return ", ".join(f"{k}: {v}" for k, v in value.items()) or "none"
    if unit == "usd":
        return f"${value:,.4f}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return f"{value:,}"


def svg_chart(series: dict[str, list], kind: str, start: datetime, threshold: float | None,
              unit: str, show_threshold_line: bool) -> str:
    w, h, pl, pr, pt, pb = 560, 200, 48, 12, 12, 26
    n = len(next(iter(series.values())))
    values = [v for s in series.values() for v in s if v is not None]
    ymax = max(values + ([threshold] if show_threshold_line and threshold is not None else []) + [1e-9])
    ymax *= 1.1
    x = lambda i: pl + (i + 0.5) * (w - pl - pr) / n
    y = lambda v: pt + (h - pt - pb) * (1 - v / ymax)
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart">']
    for frac in (0, 0.5, 1):
        gy = y(ymax / 1.1 * frac)
        parts.append(f'<line x1="{pl}" x2="{w - pr}" y1="{gy:.1f}" y2="{gy:.1f}" class="grid"/>')
        parts.append(f'<text x="{pl - 6}" y="{gy + 4:.1f}" class="tick" text-anchor="end">{ymax / 1.1 * frac:,.4g}</text>')
    for i in range(0, n, 10):
        label = (start + timedelta(minutes=i)).strftime("%H:%M")
        parts.append(f'<text x="{x(i):.1f}" y="{h - 8}" class="tick" text-anchor="middle">{label}</text>')
    if show_threshold_line and threshold is not None:
        ty = y(threshold)
        parts.append(f'<line x1="{pl}" x2="{w - pr}" y1="{ty:.1f}" y2="{ty:.1f}" class="threshold"/>')
        parts.append(f'<text x="{w - pr}" y="{ty - 4:.1f}" class="tick" text-anchor="end">threshold {threshold:,.4g}</text>')
    bar_w = max(2.0, (w - pl - pr) / n - 2)
    for s_idx, (name, pts) in enumerate(series.items()):
        color = f"var({SERIES_VARS[s_idx]})"
        if kind == "bar":
            for i, v in enumerate(pts):
                if v is None:
                    continue
                top = y(v)
                parts.append(f'<rect x="{x(i) - bar_w / 2:.1f}" y="{top:.1f}" width="{bar_w:.1f}" height="{h - pb - top:.1f}" '
                             f'rx="2" fill="{color}"><title>{name} @ {(start + timedelta(minutes=i)).strftime("%H:%M")}: {fmt(v, unit)}</title></rect>')
            continue
        run: list[str] = []
        for i, v in enumerate(pts + [None]):
            if v is not None:
                run.append(f"{x(i):.1f},{y(v):.1f}")
            elif run:
                if len(run) > 1:
                    parts.append(f'<polyline points="{" ".join(run)}" fill="none" stroke="{color}" stroke-width="2"/>')
                run = []
        for i, v in enumerate(pts):
            if v is not None:
                parts.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="4" fill="{color}" class="dot">'
                             f'<title>{name} @ {(start + timedelta(minutes=i)).strftime("%H:%M")}: {fmt(v, unit)}</title></circle>')
    parts.append(f'<line x1="{pl}" x2="{w - pr}" y1="{h - pb}" y2="{h - pb}" class="axis"/></svg>')
    return "".join(parts)


def render_panel(panel: dict, data: dict, start: datetime) -> str:
    th = panel["threshold"]
    agg_value = data["values"].get(th["aggregation"])
    ok = threshold_ok(agg_value, th["operator"], th["value"])
    status = {True: ("ok", "✓ Within threshold"), False: ("breach", "✕ Breached"), None: ("nodata", "• No data")}[ok]
    op = "≤" if th["operator"] == "lte" else "≥"
    tiles = "".join(
        f'<div class="tile"><div class="tile-label">{html.escape(k)}</div><div class="tile-value">{html.escape(fmt(v, panel["unit"]))}</div></div>'
        for k, v in data["values"].items()
    )
    legend = ""
    if len(data["series"]) > 1:
        legend = '<div class="legend">' + "".join(
            f'<span><i style="background:var({SERIES_VARS[i]})"></i>{html.escape(name)}</span>'
            for i, name in enumerate(data["series"])
        ) + "</div>"
    # A per-minute threshold line only makes sense when the threshold is per-minute comparable.
    per_minute_threshold = th["aggregation"] in {"p95", "rate_per_minute", "error_rate_pct", "mean"}
    chart = svg_chart(data["series"], data["kind"], start, th["value"], panel["unit"], per_minute_threshold)
    return f"""
<section class="panel">
  <header>
    <h2>{html.escape(panel["title"])}</h2>
    <span class="status {status[0]}">{status[1]}</span>
  </header>
  <p class="meta">unit: <b>{html.escape(panel["unit"])}</b> · threshold: <b>{th["aggregation"]} {op} {fmt(th["value"])}</b> · events: {", ".join(panel["events"])}</p>
  <div class="tiles">{tiles}</div>
  {legend}
  {chart}
  <p class="query"><code>{html.escape(panel["query"])}</code></p>
</section>"""


CSS = """
:root { color-scheme: light;
  --page:#f9f9f7; --surface-1:#fcfcfb; --text-primary:#0b0b0b; --text-secondary:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,0.10);
  --series-1:#2a78d6; --series-2:#eb6834; --series-3:#1baf7a; --series-4:#eda100;
  --good:#0ca30c; --critical:#d03b3b; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark;
  --page:#0d0d0d; --surface-1:#1a1a19; --text-primary:#ffffff; --text-secondary:#c3c2b7;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
  --series-1:#3987e5; --series-2:#d95926; --series-3:#199e70; --series-4:#c98500; } }
:root[data-theme="dark"] { color-scheme: dark;
  --page:#0d0d0d; --surface-1:#1a1a19; --text-primary:#ffffff; --text-secondary:#c3c2b7;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10);
  --series-1:#3987e5; --series-2:#d95926; --series-3:#199e70; --series-4:#c98500; }
* { box-sizing: border-box; }
body { margin:0; background:var(--page); color:var(--text-primary); font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }
main { max-width:1240px; margin:0 auto; padding:24px 16px; }
h1 { font-size:22px; margin:0 0 4px; } .sub { color:var(--text-secondary); margin:0 0 20px; }
.grid-panels { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr)); gap:16px; }
.panel { background:var(--surface-1); border:1px solid var(--border); border-radius:12px; padding:16px; min-width:0; }
.panel header { display:flex; justify-content:space-between; align-items:center; gap:8px; }
.panel h2 { font-size:16px; margin:0; }
.meta, .query { color:var(--text-secondary); font-size:12px; margin:6px 0; overflow-wrap:anywhere; }
.query code { font-size:11px; color:var(--muted); }
.status { font-size:12px; font-weight:600; padding:2px 8px; border-radius:999px; border:1px solid currentColor; white-space:nowrap; }
.status.ok { color:var(--good); } .status.breach { color:var(--critical); } .status.nodata { color:var(--muted); }
.tiles { display:flex; flex-wrap:wrap; gap:8px; margin:8px 0; }
.tile { border:1px solid var(--border); border-radius:8px; padding:6px 10px; min-width:96px; }
.tile-label { font-size:11px; color:var(--text-secondary); } .tile-value { font-size:18px; font-weight:600; }
.legend { display:flex; flex-wrap:wrap; gap:12px; font-size:12px; color:var(--text-secondary); margin:4px 0; }
.legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; vertical-align:-1px; }
.chart { width:100%; height:auto; display:block; }
.chart .grid { stroke:var(--grid); stroke-width:1; } .chart .axis { stroke:var(--axis); stroke-width:1; }
.chart .threshold { stroke:var(--critical); stroke-width:1.5; stroke-dasharray:5 4; }
.chart .tick { fill:var(--muted); font-size:10px; font-variant-numeric:tabular-nums; }
.chart .dot { stroke:var(--surface-1); stroke-width:2; }
"""


def render(config: dict, panels: dict, start: datetime, end: datetime, total_records: int) -> str:
    dash = config["dashboard"]
    body = "".join(render_panel(p, panels[p["id"]], start) for p in dash["panels"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="{dash["refresh_seconds"]}">
<title>Day 13 Dashboard</title><style>{CSS}</style></head>
<body><main>
<h1>{html.escape(dash["title"])}</h1>
<p class="sub">Time range: last {dash["time_range_minutes"]} min · {start:%Y-%m-%d %H:%M} → {end:%H:%M} UTC ·
refresh {dash["refresh_seconds"]}s · source: data/logs.jsonl ({total_records} records in window)</p>
<div class="grid-panels">{body}</div>
</main></body></html>"""


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "config" / "dashboard.yaml")
    parser.add_argument("--logs", type=Path, default=REPO_ROOT / "data" / "logs.jsonl")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "reports" / "dashboard.html")
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    minutes = config["dashboard"]["time_range_minutes"]
    records = load_records(args.logs)
    if not records:
        print(f"No log records in {args.logs}")
        return 1
    end = max(r["_ts"] for r in records).replace(second=0, microsecond=0) + timedelta(minutes=1)
    start = end - timedelta(minutes=minutes)
    window = [r for r in records if r["_ts"] >= start]
    buckets = minute_buckets(window, start, minutes)
    panels = compute_panels(window, buckets, minutes)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(config, panels, start, end, len(window)), encoding="utf-8")

    print(f"Window {start:%H:%M}–{end:%H:%M} UTC, {len(window)} records")
    for panel in config["dashboard"]["panels"]:
        th = panel["threshold"]
        value = panels[panel["id"]]["values"].get(th["aggregation"])
        ok = threshold_ok(value, th["operator"], th["value"])
        flag = {True: "OK    ", False: "BREACH", None: "NODATA"}[ok]
        values = ", ".join(f"{k}={fmt(v)}" for k, v in panels[panel["id"]]["values"].items())
        print(f"[{flag}] {panel['id']:<8} {values}  (threshold {th['aggregation']} {th['operator']} {th['value']} {panel['unit']})")
    print(f"Dashboard written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
