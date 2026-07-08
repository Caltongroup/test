"""
KQBL Music Log Web UI  —  python webapp.py  then open http://localhost:5000
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import zipfile
from datetime import date, timedelta
from pathlib import Path

from flask import (Flask, redirect, render_template_string, request,
                   send_file, url_for)

app = Flask(__name__)
app.secret_key = "kqbl-musiclog-ui"

BASE_DIR = Path(__file__).parent
DEFAULT_LIBRARY = BASE_DIR / "data" / "demo_library.csv"
STATE_DIR = BASE_DIR / "state"
STATE_DIR.mkdir(exist_ok=True)
HISTORY_FILE = STATE_DIR / "history.json"
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# ── HTML template ──────────────────────────────────────────────────────────────
TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KQBL Music Log Generator</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Arial, sans-serif; background: #1a1a2e; color: #e0e0e0; min-height: 100vh; }
  header { background: #16213e; padding: 18px 32px; display: flex; align-items: center; gap: 14px; border-bottom: 3px solid #e94560; }
  header img { width: 48px; height: 48px; }
  header h1 { font-size: 1.5rem; color: #fff; letter-spacing: 1px; }
  header span { color: #e94560; font-weight: bold; }
  .container { max-width: 860px; margin: 40px auto; padding: 0 20px; }
  .card { background: #16213e; border-radius: 10px; padding: 28px 32px; margin-bottom: 28px; box-shadow: 0 4px 18px rgba(0,0,0,.4); }
  .card h2 { font-size: 1.15rem; color: #e94560; margin-bottom: 18px; text-transform: uppercase; letter-spacing: 1px; }
  label { display: block; font-size: .9rem; color: #aaa; margin-bottom: 5px; margin-top: 14px; }
  input[type=date], input[type=number], select, input[type=file] {
    width: 100%; padding: 10px 12px; border-radius: 6px; border: 1px solid #2e3a5c;
    background: #0f3460; color: #e0e0e0; font-size: 1rem;
  }
  input[type=file] { cursor: pointer; }
  .row { display: flex; gap: 16px; }
  .row > div { flex: 1; }
  .btn { display: inline-block; margin-top: 22px; padding: 12px 30px; border-radius: 6px;
         background: #e94560; color: #fff; font-size: 1rem; font-weight: bold;
         border: none; cursor: pointer; transition: background .2s; }
  .btn:hover { background: #c73652; }
  .btn-secondary { background: #0f3460; }
  .btn-secondary:hover { background: #1a4a7a; }
  .alert { padding: 12px 16px; border-radius: 6px; margin-bottom: 18px; font-size: .95rem; }
  .alert-error { background: #4a1020; border: 1px solid #e94560; color: #f88; }
  .alert-success { background: #0a3020; border: 1px solid #2ecc71; color: #6f8; }
  .alert-warn { background: #3a2a00; border: 1px solid #f39c12; color: #fc8; }
  table { width: 100%; border-collapse: collapse; font-size: .85rem; margin-top: 10px; }
  th { background: #0f3460; color: #e94560; padding: 8px 10px; text-align: left; }
  td { padding: 7px 10px; border-bottom: 1px solid #2e3a5c; }
  tr:hover td { background: #1e2e4e; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: .78rem; font-weight: bold; }
  .badge-PC { background:#c0392b; color:#fff; }
  .badge-PR { background:#e67e22; color:#fff; }
  .badge-PT { background:#f1c40f; color:#222; }
  .badge-ST { background:#27ae60; color:#fff; }
  .badge-P2K { background:#2980b9; color:#fff; }
  .badge-S2K { background:#8e44ad; color:#fff; }
  .badge-P90 { background:#16a085; color:#fff; }
  .badge-S90 { background:#d35400; color:#fff; }
  .badge-TB  { background:#7f8c8d; color:#fff; }
  .badge-AF  { background:#2c3e50; color:#aaa; }
  .log-block { background: #0a0f1e; border-radius: 6px; padding: 14px 16px; font-family: monospace; font-size: .82rem; white-space: pre; overflow-x: auto; max-height: 340px; overflow-y: auto; color: #b0c4de; margin-top: 10px; }
  .tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
  .tab-btn { padding: 8px 18px; border-radius: 6px 6px 0 0; border: 1px solid #2e3a5c; border-bottom: none; background: #0f3460; color: #aaa; cursor: pointer; font-size: .88rem; }
  .tab-btn.active { background: #16213e; color: #e94560; font-weight: bold; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .stat-row { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 10px; }
  .stat { background: #0f3460; border-radius: 8px; padding: 14px 20px; flex: 1; min-width: 130px; text-align: center; }
  .stat .num { font-size: 2rem; font-weight: bold; color: #e94560; }
  .stat .lbl { font-size: .8rem; color: #aaa; margin-top: 4px; }
  footer { text-align: center; padding: 24px; color: #555; font-size: .8rem; }
  .problems-list li { padding: 4px 0; font-size: .88rem; color: #f88; }
  .ok-msg { color: #6f8; font-size: .95rem; }
  a.dl-link { color: #6cf; text-decoration: none; font-size: .88rem; }
  a.dl-link:hover { text-decoration: underline; }
</style>
</head>
<body>
<header>
  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
    <circle cx="24" cy="24" r="22" fill="#e94560" opacity=".15" stroke="#e94560" stroke-width="2"/>
    <circle cx="24" cy="24" r="8" fill="#e94560"/>
    <line x1="24" y1="2" x2="24" y2="10" stroke="#e94560" stroke-width="2.5"/>
    <line x1="24" y1="38" x2="24" y2="46" stroke="#e94560" stroke-width="2.5"/>
    <line x1="2" y1="24" x2="10" y2="24" stroke="#e94560" stroke-width="2.5"/>
    <line x1="38" y1="24" x2="46" y2="24" stroke="#e94560" stroke-width="2.5"/>
  </svg>
  <h1>KQBL&nbsp;<span>Music Log Generator</span></h1>
</header>

<div class="container">

{% for msg in messages %}
  <div class="alert alert-{{ msg.type }}">{{ msg.text }}</div>
{% endfor %}

<!-- ── Generate form ── -->
<div class="card">
  <h2>Generate Daily Logs</h2>
  <form method="post" action="/generate" enctype="multipart/form-data">
    <label>Library File <small style="color:#777">(leave blank to use the built-in demo library)</small></label>
    <input type="file" name="library" accept=".csv,.xlsx">

    <div class="row">
      <div>
        <label>Start Date</label>
        <input type="date" name="start" value="{{ default_start }}" required>
      </div>
      <div>
        <label>Number of Days</label>
        <input type="number" name="days" value="7" min="1" max="31" required>
      </div>
    </div>

    <label>Reset History?</label>
    <select name="reset_history">
      <option value="no">No — keep rolling rotation memory</option>
      <option value="yes">Yes — start fresh</option>
    </select>

    <button class="btn" type="submit">&#9654;&nbsp; Generate Logs</button>
  </form>
</div>

<!-- ── Results ── -->
{% if logs %}
<div class="card">
  <h2>Generated Logs — {{ logs|length }} day(s)</h2>

  <!-- Stats bar -->
  <div class="stat-row">
    <div class="stat"><div class="num">{{ total_slots }}</div><div class="lbl">Total slots</div></div>
    <div class="stat"><div class="num">{{ logs|length }}</div><div class="lbl">Days</div></div>
    <div class="stat"><div class="num">{{ problems|length }}</div><div class="lbl">Rule issues</div></div>
    <div class="stat"><div class="num"><a class="dl-link" href="/download">⬇ ZIP</a></div><div class="lbl">Download all</div></div>
  </div>

  <!-- Rule audit -->
  {% if problems %}
  <details style="margin-top:18px">
    <summary style="cursor:pointer;color:#f88;font-weight:bold">⚠ {{ problems|length }} rule issue(s) found</summary>
    <ul class="problems-list" style="margin-top:10px;padding-left:20px">
      {% for p in problems %}<li>{{ p }}</li>{% endfor %}
    </ul>
  </details>
  {% else %}
  <p class="ok-msg" style="margin-top:14px">&#10003; All programming rules pass.</p>
  {% endif %}

  <!-- Day tabs -->
  <div class="tabs" style="margin-top:22px" id="day-tabs">
    {% for log in logs %}
    <button class="tab-btn {% if loop.first %}active{% endif %}"
            onclick="showTab('day-{{ loop.index0 }}', this)">
      {{ log.date_iso }} ({{ ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][log.weekday] }})
    </button>
    {% endfor %}
  </div>

  {% for log in logs %}
  <div class="tab-content {% if loop.first %}active{% endif %}" id="day-{{ loop.index0 }}">
    <table>
      <thead><tr><th>Time</th><th>Title</th><th>Artist</th><th>Cat</th><th>Tempo</th><th>Mood</th><th>Era</th></tr></thead>
      <tbody>
      {% for slot in log.slots %}
      <tr>
        <td>{{ slot.time_str }}</td>
        <td>{{ slot.song.title }}</td>
        <td>{{ slot.song.artist }}</td>
        <td><span class="badge badge-{{ slot.song.category }}">{{ slot.song.category }}</span></td>
        <td>{{ slot.song.tempo }}</td>
        <td>{{ slot.song.mood.name }}</td>
        <td>{{ slot.song.year }}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    <p style="margin-top:8px;color:#777;font-size:.82rem">{{ log.slots|length }} slots &nbsp;|&nbsp;
      <a class="dl-link" href="/download/{{ log.date_iso }}">⬇ Download this day's .LOG</a></p>
  </div>
  {% endfor %}
</div>
{% endif %}

</div><!-- /container -->

<footer>KQBL Music Log Automation &nbsp;·&nbsp; musiclog v1.0</footer>

<script>
function showTab(id, btn) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
}
</script>
</body>
</html>
"""


# ── helpers ────────────────────────────────────────────────────────────────────

def _run_generate(library_path: Path, start: date, days: int) -> tuple:
    """Return (logs, problems, rendered_files_dict)."""
    from musiclog.history import HistoryStore
    from musiclog.library import load_library
    from musiclog.scheduler import Scheduler
    from musiclog.validate import validate_logs
    from musiclog.export import render_log

    songs = load_library(str(library_path))
    history = HistoryStore(str(HISTORY_FILE))
    scheduler = Scheduler(songs, history)
    logs = scheduler.schedule_days(start, days)
    problems = validate_logs(logs, songs)

    files = {}
    for log in logs:
        fname = f"KQBL {log.date_iso}.LOG"
        files[fname] = render_log(log)

    return logs, problems, files


# ── state: keep last-generated data in memory ──────────────────────────────────
_last: dict = {}   # {logs, problems, files}


@app.route("/", methods=["GET"])
def index():
    default_start = date.today().isoformat()
    logs = _last.get("logs", [])
    problems = _last.get("problems", [])
    total_slots = sum(len(l.slots) for l in logs)
    messages = _last.pop("flash", [])
    return render_template_string(
        TEMPLATE,
        logs=logs,
        problems=problems,
        total_slots=total_slots,
        default_start=default_start,
        messages=messages,
    )


@app.route("/generate", methods=["POST"])
def generate():
    try:
        # Library
        uploaded = request.files.get("library")
        if uploaded and uploaded.filename:
            suffix = Path(uploaded.filename).suffix
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            uploaded.save(tmp.name)
            library_path = Path(tmp.name)
        else:
            library_path = DEFAULT_LIBRARY

        # Date / days
        start = date.fromisoformat(request.form["start"])
        days = int(request.form["days"])
        if days < 1 or days > 31:
            raise ValueError("Days must be 1–31.")

        # History reset
        if request.form.get("reset_history") == "yes":
            HISTORY_FILE.unlink(missing_ok=True)

        logs, problems, files = _run_generate(library_path, start, days)
        _last["logs"] = logs
        _last["problems"] = problems
        _last["files"] = files

        msg_type = "alert-warn" if problems else "alert-success"
        msg_text = (f"Generated {days} day(s) starting {start}. "
                    + (f"{len(problems)} rule issue(s) found — see below."
                       if problems else "All rules clean!"))
        _last["flash"] = [{"type": msg_type.replace("alert-", ""), "text": msg_text}]

    except Exception as exc:
        _last["flash"] = [{"type": "error", "text": f"Error: {exc}"}]

    return redirect(url_for("index"))


@app.route("/download")
def download_all():
    files = _last.get("files", {})
    if not files:
        return "No logs generated yet.", 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name="KQBL_logs.zip",
                     mimetype="application/zip")


@app.route("/download/<date_iso>")
def download_day(date_iso: str):
    files = _last.get("files", {})
    fname = f"KQBL {date_iso}.LOG"
    content = files.get(fname)
    if content is None:
        return "Log not found.", 404
    return send_file(
        io.BytesIO(content.encode()),
        as_attachment=True,
        download_name=fname,
        mimetype="text/plain",
    )


if __name__ == "__main__":
    print("\n  KQBL Music Log Generator")
    print("  Open your browser at:  http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False)
