"""
dashboard.py - builds reports/dashboard.html from the monitor history.

It reads the JSON files saved by monitor.py (reports/history/*.json)
and writes ONE html page: device cards, latest checks, proposed fixes
and a timeline of the last checks. The page reloads itself every 30 s.
"""
import json
from html import escape
from pathlib import Path

HISTORY_DIR = Path("reports/history")
OUTPUT = Path("reports/dashboard.html")
REFRESH_SECONDS = 30
TIMELINE_SIZE = 10

RANK = {"OK": 0, "WARN": 1, "ISSUE": 2}          # worst status wins
LABEL = {"OK": "OK", "WARN": "Warning", "ISSUE": "Issue"}


def load_history():
    """All saved checks, oldest first."""
    runs = []
    for path in sorted(HISTORY_DIR.glob("*.json")):
        runs.append(json.loads(path.read_text(encoding="utf-8")))
    return runs


def worst(statuses):
    return max(statuses, key=lambda s: RANK[s]) if statuses else "OK"


def device_cards(results):
    devices = {}
    for r in results:
        devices.setdefault(r["device"], []).append(r)
    cards = []
    for name, items in devices.items():
        status = worst([r["status"] for r in items])
        problems = sum(1 for r in items if r["status"] != "OK")
        summary = "all checks passed" if problems == 0 else f"{problems} to review"
        cards.append(
            f'<div class="card {status.lower()}"><span class="name">{escape(name)}</span>'
            f'<span class="pill {status.lower()}">{LABEL[status]}</span>'
            f'<span class="sub">{len(items)} checks · {summary}</span></div>'
        )
    return "\n".join(cards)


def checks_table(results):
    rows = []
    for r in sorted(results, key=lambda r: -RANK[r["status"]]):
        rows.append(
            f'<tr><td>{escape(r["device"])}</td><td>{escape(r["check"])}</td>'
            f'<td><span class="pill {r["status"].lower()}">{LABEL[r["status"]]}</span></td>'
            f'<td>{escape(r["detail"])}</td></tr>'
        )
    return "\n".join(rows)


def fixes_block(results):
    blocks = []
    for r in results:
        if r["status"] != "OK" and r["fix"]:
            commands = escape("\n".join(r["fix"]))
            blocks.append(
                f'<div class="fix"><div class="fix-head">{escape(r["device"])} · {escape(r["check"])}'
                f' <span class="muted">— proposed, not applied</span></div><pre>{commands}</pre></div>'
            )
    return "\n".join(blocks) or '<p class="muted">No fix needed.</p>'


def timeline_table(runs):
    rows = []
    for run in reversed(runs[-TIMELINE_SIZE:]):
        statuses = [r["status"] for r in run["results"]]
        ok, warn, issue = (statuses.count(s) for s in ("OK", "WARN", "ISSUE"))
        overall = worst(statuses)
        rows.append(
            f'<tr><td>{escape(run["time"].replace("T", " "))}</td>'
            f'<td><span class="pill {overall.lower()}">{LABEL[overall]}</span></td>'
            f'<td class="num">{ok}</td><td class="num">{warn}</td><td class="num">{issue}</td></tr>'
        )
    return "\n".join(rows)


STYLE = """
:root{--bg:#f3f5f8;--card:#ffffff;--ink:#15202e;--muted:#5d6b7c;--line:#d8dee6;
--ok:#1f7a4d;--ok-bg:#e3f3ea;--warn:#9a5b00;--warn-bg:#fdf1dc;--bad:#b42318;--bad-bg:#fde8e6;--code:#eef2f6}
@media (prefers-color-scheme: dark){:root{--bg:#0e1622;--card:#162233;--ink:#e6edf5;--muted:#9aa9ba;--line:#2a3a4f;
--ok:#4cc38a;--ok-bg:#143326;--warn:#e7ad52;--warn-bg:#3a2a10;--bad:#ff7a6b;--bad-bg:#3c1916;--code:#0b121c}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Segoe UI",Arial,sans-serif;font-size:15px;
padding:24px max(16px,4vw)}
.wrap{max-width:1100px;margin:0 auto;display:flex;flex-direction:column;gap:20px}
header{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-end;gap:12px}
h1{margin:0;font-size:24px} h2{margin:0 0 10px;font-size:17px}
.eyebrow{margin:0 0 4px;font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.muted{color:var(--muted);font-weight:400}
.overall{font-size:15px;font-weight:600;padding:8px 14px;border-radius:999px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-left:6px solid var(--line);border-radius:10px;
padding:14px;display:flex;flex-direction:column;gap:6px}
.card.ok{border-left-color:var(--ok)} .card.warn{border-left-color:var(--warn)} .card.issue{border-left-color:var(--bad)}
.name{font-size:20px;font-weight:700} .sub{font-size:13px;color:var(--muted)}
.pill{display:inline-block;width:max-content;font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px}
.pill.ok{color:var(--ok);background:var(--ok-bg)} .pill.warn{color:var(--warn);background:var(--warn-bg)}
.pill.issue{color:var(--bad);background:var(--bad-bg)}
section{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.fix{border:1px dashed var(--line);border-radius:8px;padding:10px;margin-bottom:10px}
.fix-head{font-weight:600;margin-bottom:6px}
pre{margin:0;background:var(--code);padding:10px;border-radius:6px;font-family:Consolas,"Courier New",monospace;
font-size:13px;overflow-x:auto}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px}
"""


def build_dashboard():
    runs = load_history()
    if not runs:
        raise SystemExit("No history yet: run python monitor.py first.")
    latest = runs[-1]
    results = latest["results"]
    overall = worst([r["status"] for r in results])
    to_review = sum(1 for r in results if r["status"] != "OK")

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{REFRESH_SECONDS}">
<title>Nettora ConfigGuard</title><style>{STYLE}</style></head>
<body><div class="wrap">
<header>
  <div><p class="eyebrow">Nettora ConfigGuard · network status</p>
  <h1>Last check: {escape(latest["time"].replace("T", " "))}</h1>
  <p class="muted">{len(results)} checks · {to_review} to review · page refreshes every {REFRESH_SECONDS} s</p></div>
  <span class="overall pill {overall.lower()}">Overall: {LABEL[overall]}</span>
</header>
<div class="cards">{device_cards(results)}</div>
<section><h2>Latest checks</h2><div class="scroll"><table>
<tr><th>Device</th><th>Check</th><th>Status</th><th>Detail</th></tr>
{checks_table(results)}
</table></div></section>
<div class="grid2">
<section><h2>Proposed fixes</h2>{fixes_block(results)}</section>
<section><h2>Timeline (last {TIMELINE_SIZE} checks)</h2><div class="scroll"><table>
<tr><th>Time</th><th>Overall</th><th>OK</th><th>Warn</th><th>Issue</th></tr>
{timeline_table(runs)}
</table></div></section>
</div>
</div></body></html>"""

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    return OUTPUT


if __name__ == "__main__":
    path = build_dashboard()
    print(f"Dashboard written to {path.resolve()}")
