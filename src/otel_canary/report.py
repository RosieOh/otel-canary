"""Merges cell results into results.json, status changes, badges and a static dashboard."""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from otel_canary.adapters import ADAPTERS
from otel_canary.matrix import LABELS

BROKEN = ("FAIL", "DEGRADED")
# Worst first, for summarising several transports in one badge.
SEVERITY = ("FAIL", "DEGRADED", "INFRA", "BLOCKED", "PASS")
BADGE_COLORS = {
    "PASS": "brightgreen",
    "FAIL": "red",
    "DEGRADED": "orange",
    "BLOCKED": "lightgrey",
    "INFRA": "yellow",
}
REPO_URL = "https://github.com/RosieOh/otel-canary"


def cell_key(result: dict[str, Any]) -> str:
    cell = result["cell"]
    return f"{cell['adapter']}:{cell['transport']}:{cell.get('label') or cell['otel']}"


def load_results(directory: Path) -> list[dict[str, Any]]:
    return [json.loads(path.read_text()) for path in sorted(directory.glob("*.json"))]


def _repro(cell: dict[str, Any]) -> str:
    return f"uv run otel-canary run --sdk {cell['sdk']} --otel {cell['otel']} --transport {cell['transport']}"


def changes(previous: list[dict[str, Any]], current: list[dict[str, Any]], date: str) -> list[dict[str, Any]]:
    """Status changes against the previous run. With no previous run there is nothing to alert on."""
    if not previous:
        return []
    before = {cell_key(result): result for result in previous}
    found = []
    for result in current:
        key = cell_key(result)
        old = before.get(key, {}).get("status")
        new = result["status"]
        if old == new:
            continue
        cell = result["cell"]
        if new in BROKEN and old not in BROKEN:
            kind = "broke"
        elif old in BROKEN and new == "PASS":
            kind = "recovered"
        else:
            kind = "info"
        title = f"canary: {cell['adapter']} ({cell['transport']}) with OpenTelemetry {cell.get('label') or cell['otel']}"
        if kind == "recovered":
            body = f"Recovered on {date}: **{old} → PASS** with `{cell['sdk']}` and OpenTelemetry `{cell['otel']}`."
        else:
            log = (result.get("logs") or {}).get("adapter", "").strip()
            body = "\n".join(
                [
                    f"**{old or 'new'} → {new}** on {date}",
                    "",
                    f"- SDK: `{cell['sdk']}`",
                    f"- OpenTelemetry: `{cell['otel']}` ({cell.get('label') or 'pinned'})",
                    f"- Transport: {cell['transport']}",
                    f"- Reason: `{result['reason']}`",
                    "",
                    "<details><summary>Adapter log</summary>",
                    "",
                    "```",
                    log[-3000:],
                    "```",
                    "</details>",
                    "",
                    f"Reproduce: `{_repro(cell)}`",
                ]
            )
        found.append({"key": key, "kind": kind, "from": old, "to": new, "title": title, "body": body})
    return found


def badges(current: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """A shields.io endpoint per adapter: the worst status across transports on the latest release."""
    out = {}
    for name in ADAPTERS:
        latest = [r for r in current if r["cell"]["adapter"] == name and r["cell"].get("label") == "latest"]
        if not latest:
            continue
        status = min((r["status"] for r in latest), key=SEVERITY.index)
        out[name] = {
            "schemaVersion": 1,
            "label": f"otel {latest[0]['cell']['otel']}",
            "message": status.lower(),
            "color": BADGE_COLORS[status],
        }
    return out


_CSS = """
:root{--ink:#111;--muted:#6b7280;--line:#e5e7eb;--line2:#d1d5db;--ok:#15803d;--bad:#b91c1c;--warn:#b45309;
--info:#6b7280;--font:"Pretendard",-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Segoe UI",sans-serif;
--mono:"JetBrains Mono",SFMono-Regular,Menlo,monospace}
*{box-sizing:border-box}body{margin:0;background:#fff;color:var(--ink);font-family:var(--font);line-height:1.6}
main{max-width:1080px;margin:0 auto;padding:40px 20px 80px}
h1{font-size:28px;margin:0 0 6px;letter-spacing:-.02em}.muted{color:var(--muted)}.small{font-size:13px}
h2{font-size:18px;margin:36px 0 12px;padding-top:14px;border-top:1px solid var(--ink)}
a{color:#2563eb;text-decoration:none}a:hover{text-decoration:underline}
.wrap{overflow-x:auto;border:1px solid var(--line2);border-radius:10px}
table{border-collapse:collapse;width:100%;min-width:640px;font-size:14px}
th,td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:#374151;border-bottom-color:var(--line2)}tr:last-child td{border-bottom:0}
.badge{display:inline-block;font:600 12px var(--mono);padding:1px 8px;border:1px solid currentColor;border-radius:999px}
.PASS{color:var(--ok)}.FAIL{color:var(--bad)}.DEGRADED{color:var(--warn)}.BLOCKED,.INFRA{color:var(--info)}
code{font-family:var(--mono);font-size:12px}
details{margin-top:6px}summary{cursor:pointer;color:var(--muted);font-size:13px}
pre{font:12px/1.5 var(--mono);border:1px solid var(--line2);border-radius:8px;padding:10px;overflow-x:auto;
white-space:pre-wrap;word-break:break-all;margin:6px 0 0}
ul{padding-left:20px}li{margin:4px 0}
"""


def _cell_html(result: dict[str, Any] | None) -> str:
    if result is None:
        return '<td class="muted">—</td>'
    cell, status = result["cell"], result["status"]
    versions = result.get("versions") or {}
    package = cell["sdk"].split("==")[0]
    shown = {name: versions[name] for name in (package, "opentelemetry-sdk") if name in versions}
    log = ((result.get("logs") or {}).get("adapter") or "").strip()[-2000:]
    parts = [
        f'<td><span class="badge {status}">{status}</span> ',
        f'<span class="small muted">{html.escape(cell["sdk"].split("==")[-1])} · otel {html.escape(cell["otel"])}</span>',
        f'<div class="small">{html.escape(result["reason"])}</div>',
        "<details><summary>details</summary>",
        f'<div class="small">reproduce: <code>{html.escape(_repro(cell))}</code></div>',
        f"<pre>{html.escape(json.dumps(shown, indent=2))}</pre>",
    ]
    if log:
        parts.append(f"<pre>{html.escape(log)}</pre>")
    parts.append("</details></td>")
    return "".join(parts)


def render_html(current: list[dict[str, Any]], found: list[dict[str, Any]], generated_at: str) -> str:
    by_key = {cell_key(result): result for result in current}
    rows = []
    for spec in ADAPTERS.values():
        for transport in sorted(spec.transports):
            cells = "".join(_cell_html(by_key.get(f"{spec.name}:{transport}:{label}")) for label in LABELS)
            rows.append(
                f"<tr><td><strong>{html.escape(spec.package)}</strong>"
                f'<div class="small muted">{transport}</div></td>{cells}</tr>'
            )
    header = "".join(f"<th>{label}</th>" for label in LABELS)
    if found:
        items = "".join(
            f'<li><span class="badge {html.escape(c["to"])}">{html.escape(c["to"])}</span> '
            f'{html.escape(c["title"])} <span class="muted small">from {html.escape(str(c["from"]))}</span></li>'
            for c in found
        )
        changed = f"<ul>{items}</ul>"
    else:
        changed = '<p class="muted small">No changes since the previous run.</p>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>otel-canary</title><style>{_CSS}</style></head>
<body><main>
<h1>otel-canary</h1>
<p class="muted">Do LLM observability SDKs still export spans with the latest OpenTelemetry Python releases?
Each cell installs one SDK with one OpenTelemetry release in a fresh virtualenv and sends a span to a mock
OTLP receiver. <a href="{REPO_URL}">Source and method</a>.</p>
<p class="small muted">Updated {html.escape(generated_at)} ·
<span class="badge PASS">PASS</span> exported · <span class="badge FAIL">FAIL</span> crashed ·
<span class="badge DEGRADED">DEGRADED</span> no or incomplete spans ·
<span class="badge BLOCKED">BLOCKED</span> the SDK doesn't allow this release · <span class="badge INFRA">INFRA</span> the run itself failed</p>
<h2>Matrix</h2>
<div class="wrap"><table><thead><tr><th>SDK</th>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>
<h2>Changes since the previous run</h2>
{changed}
</main></body></html>
"""


def write_report(results_dir: Path, previous_path: Path | None, out_dir: Path) -> dict[str, Any]:
    current = load_results(results_dir)
    previous = json.loads(previous_path.read_text()) if previous_path and previous_path.exists() else []
    now = datetime.now(UTC)
    found = changes(previous, current, now.strftime("%Y-%m-%d"))

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(json.dumps(current, indent=1) + "\n")
    (out_dir / "changes.json").write_text(json.dumps(found, indent=1) + "\n")
    (out_dir / "index.html").write_text(render_html(current, found, now.strftime("%Y-%m-%d %H:%M UTC")))
    badge_dir = out_dir / "badges"
    badge_dir.mkdir(exist_ok=True)
    for name, badge in badges(current).items():
        (badge_dir / f"{name}.json").write_text(json.dumps(badge) + "\n")

    counts: dict[str, int] = {}
    for result in current:
        counts[result["status"]] = counts.get(result["status"], 0) + 1
    return {"cells": len(current), "statuses": counts, "changes": [(c["kind"], c["key"]) for c in found]}
