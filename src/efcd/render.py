import html


def _escape(value):
    return html.escape(str(value), quote=True)


def _format_number(value, digits=4):
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return _escape(value)


def render_report_html(report, baseline=None, latest=None):
    source_id = report.get("source_id", "unknown")
    severity = report.get("severity", "unknown")
    changes = report.get("changes", [])
    alert_count = report.get("alert_count", 0)
    alert_severity = report.get("alert_severity", "low")
    alert_flag = report.get("alert", False)
    baseline_meta = report.get("baseline_meta", {}) or {}
    latest_meta = report.get("latest_meta", {}) or {}

    baseline_rows = None
    latest_rows = None
    baseline_fields = None
    latest_fields = None
    if baseline:
        baseline_rows = baseline.get("stats", {}).get("row_count")
        baseline_fields = baseline.get("stats", {}).get("field_count")
    if latest:
        latest_rows = latest.get("stats", {}).get("row_count")
        latest_fields = latest.get("stats", {}).get("field_count")
    if baseline_rows is None:
        baseline_rows = report.get("baseline_summary", {}).get("row_count")
    if baseline_fields is None:
        baseline_fields = report.get("baseline_summary", {}).get("field_count")
    if latest_rows is None:
        latest_rows = report.get("latest_summary", {}).get("row_count")
    if latest_fields is None:
        latest_fields = report.get("latest_summary", {}).get("field_count")

    row_delta = None
    if baseline_rows and latest_rows:
        row_delta = (latest_rows - baseline_rows) / baseline_rows

    severity_class = {
        "low": "sev-low",
        "medium": "sev-med",
        "high": "sev-high",
    }.get(severity, "sev-unk")
    alert_class = {
        "low": "sev-low",
        "medium": "sev-med",
        "high": "sev-high",
    }.get(alert_severity, "sev-unk")

    baseline_mode = baseline_meta.get("mode") or "latest"
    baseline_window = baseline_meta.get("window")
    baseline_id = baseline_meta.get("profile_id") or report.get("baseline_profile_id")
    latest_id = latest_meta.get("profile_id") or report.get("latest_profile_id")
    baseline_set_at = baseline_meta.get("set_at")
    baseline_seasonality = baseline_meta.get("seasonality")
    report_seasonality = report.get("seasonality")
    report_bucket = report.get("seasonality_bucket")

    change_rows = []
    for change in changes:
        change_rows.append(
            "<tr>"
            f"<td>{_escape(change.get('field'))}</td>"
            f"<td>{_escape(change.get('type'))}</td>"
            f"<td>{_escape(change.get('metric'))}</td>"
            f"<td>{_escape(change.get('before'))}</td>"
            f"<td>{_escape(change.get('after'))}</td>"
            f"<td>{_escape(change.get('delta'))}</td>"
            f"<td class=\"{_escape('sev-' + change.get('severity', 'low'))}\">{_escape(change.get('severity'))}</td>"
            f"<td>{_escape(change.get('recommendation'))}</td>"
            f"<td>{_escape(change.get('confidence', '-'))}</td>"
            f"<td>{'yes' if change.get('alert') else 'no'}</td>"
            "</tr>"
        )

    if not change_rows:
        change_rows.append(
            "<tr class=\"empty-row\"><td colspan=\"10\">No changes detected.</td></tr>"
        )

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EFCD Report - {_escape(source_id)}</title>
  <style>
    :root {{
      --bg: #f4f2ee;
      --panel: #ffffff;
      --ink: #141414;
      --muted: #5e5e5e;
      --accent: #1b9aaa;
      --accent-2: #f18f01;
      --border: #e3e0da;
      --shadow: rgba(0, 0, 0, 0.06);
      --radius: 14px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Work Sans", "Source Sans 3", sans-serif;
      background:
        radial-gradient(1200px circle at 10% -10%, #fff5dd, transparent 40%),
        radial-gradient(900px circle at 110% 10%, #e9f7f8, transparent 35%),
        var(--bg);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1080px;
      margin: 40px auto 80px;
      padding: 0 20px;
      animation: fadeUp 0.6s ease-out;
    }}
    header {{
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-bottom: 24px;
    }}
    h1 {{
      font-size: 32px;
      margin: 0;
      letter-spacing: -0.5px;
    }}
    .sub {{
      color: var(--muted);
      font-size: 14px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 12px;
      border-radius: 999px;
      background: #eef6f6;
      color: var(--ink);
      font-weight: 600;
      width: fit-content;
    }}
    .badge .dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--accent);
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 16px 18px;
      box-shadow: 0 10px 20px var(--shadow);
      animation: cardIn 0.5s ease-out;
    }}
    .card h3 {{
      margin: 0 0 6px;
      font-size: 14px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .card .value {{
      font-size: 22px;
      font-weight: 600;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
      box-shadow: 0 12px 24px var(--shadow);
    }}
    thead {{
      background: #f6f4f1;
      text-align: left;
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--border);
      font-size: 13px;
      vertical-align: top;
    }}
    tr:last-child td {{
      border-bottom: none;
    }}
    .sev-low {{ color: #1d7f5f; font-weight: 600; }}
    .sev-med {{ color: #b45309; font-weight: 600; }}
    .sev-high {{ color: #b91c1c; font-weight: 700; }}
    .sev-unk {{ color: #4b5563; font-weight: 600; }}
    .empty-row td {{
      text-align: center;
      color: var(--muted);
      padding: 24px 14px;
    }}
    .footer {{
      margin-top: 20px;
      color: var(--muted);
      font-size: 12px;
    }}
    @keyframes fadeUp {{
      from {{ opacity: 0; transform: translateY(12px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes cardIn {{
      from {{ opacity: 0; transform: translateY(8px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    @media (max-width: 720px) {{
      h1 {{ font-size: 26px; }}
      th, td {{ font-size: 12px; }}
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 10px;
      margin-top: 10px;
      font-size: 13px;
      color: var(--muted);
    }}
    .meta span {{
      display: inline-block;
      min-width: 110px;
      color: var(--ink);
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <div class="badge"><span class="dot"></span>EFCD Change Report</div>
      <h1>Source: {_escape(source_id)}</h1>
      <div class="sub">Severity: <span class="{_escape(severity_class)}">{_escape(severity)}</span> | Alerts: <span class="{_escape(alert_class)}">{_escape(alert_severity)}</span></div>
      <div class="meta">
        <div><span>Baseline</span>{_escape(baseline_mode)}{f' (window {baseline_window})' if baseline_window else ''}</div>
        <div><span>Baseline ID</span>{_escape(baseline_id) if baseline_id else '-'}</div>
        <div><span>Latest ID</span>{_escape(latest_id) if latest_id else '-'}</div>
        <div><span>Pinned at</span>{_escape(baseline_set_at) if baseline_set_at else '-'}</div>
        <div><span>Seasonality</span>{_escape(baseline_seasonality) if baseline_seasonality else '-'}</div>
        <div><span>Alert bucket</span>{_escape(report_bucket) if report_bucket is not None else '-'}</div>
      </div>
    </header>

    <section class="cards">
      <div class="card">
        <h3>Changes</h3>
        <div class="value">{len(changes)}</div>
      </div>
      <div class="card">
        <h3>Alerts</h3>
        <div class="value">{alert_count if alert_flag else 0}</div>
      </div>
      <div class="card">
        <h3>Alert severity</h3>
        <div class="value">{_escape(alert_severity)}</div>
      </div>
      <div class="card">
        <h3>Rows (baseline)</h3>
        <div class="value">{_escape(baseline_rows) if baseline_rows is not None else "-"}</div>
      </div>
      <div class="card">
        <h3>Rows (latest)</h3>
        <div class="value">{_escape(latest_rows) if latest_rows is not None else "-"}</div>
      </div>
      <div class="card">
        <h3>Row delta</h3>
        <div class="value">{_format_number(row_delta * 100.0, 2) + '%' if row_delta is not None else "-"}</div>
      </div>
      <div class="card">
        <h3>Fields (baseline)</h3>
        <div class="value">{_escape(baseline_fields) if baseline_fields is not None else "-"}</div>
      </div>
      <div class="card">
        <h3>Fields (latest)</h3>
        <div class="value">{_escape(latest_fields) if latest_fields is not None else "-"}</div>
      </div>
    </section>

    <table>
      <thead>
        <tr>
          <th>Field</th>
          <th>Change</th>
          <th>Metric</th>
          <th>Before</th>
          <th>After</th>
          <th>Delta</th>
          <th>Severity</th>
          <th>Recommendation</th>
          <th>Confidence</th>
          <th>Alert</th>
        </tr>
      </thead>
      <tbody>
        {''.join(change_rows)}
      </tbody>
    </table>

    <div class="footer">Generated by EFCD.</div>
  </div>
</body>
</html>
"""
    return html_out


def render_index_html(entries):
    def severity_rank(sev):
        return {"high": 0, "medium": 1, "low": 2}.get(sev, 3)

    entries_sorted = sorted(entries, key=lambda e: e.get("created_at", ""), reverse=True)
    entries_sorted = sorted(entries_sorted, key=lambda e: severity_rank(e.get("severity")))

    cards = []
    for entry in entries_sorted:
        link = entry.get("link")
        link_label = "open report"
        baseline = entry.get("baseline_mode") or "-"
        window = entry.get("baseline_window")
        if window:
            baseline = f"{baseline} (w{window})"
        alert_count = entry.get("alert_count", 0)
        alert_severity = entry.get("alert_severity", "low")
        bucket = entry.get("seasonality_bucket")
        bucket_str = str(bucket) if bucket is not None else "-"
        cards.append(
            "<article class=\"card\">"
            f"<div class=\"card-head\"><span class=\"pill {entry.get('severity_class', '')}\">{_escape(entry.get('severity', 'unknown'))}</span>"
            f"<span class=\"source\">{_escape(entry.get('source_id', 'unknown'))}</span></div>"
            f"<div class=\"card-body\">"
            f"<div><span>Changes</span>{_escape(entry.get('changes'))}</div>"
            f"<div><span>Alerts</span>{_escape(alert_count)} ({_escape(alert_severity)})</div>"
            f"<div><span>Baseline</span>{_escape(baseline)}</div>"
            f"<div><span>Bucket</span>{_escape(bucket_str)}</div>"
            f"<div><span>Report ID</span>{_escape(entry.get('report_id'))}</div>"
            f"<div><span>Created</span>{_escape(entry.get('created_at'))}</div>"
            "</div>"
            f"<a class=\"card-link\" href=\"{_escape(link)}\">{link_label}</a>"
            "</article>"
        )

    if not cards:
        cards.append("<div class=\"empty\">No reports found.</div>")

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EFCD Reports</title>
  <style>
    :root {{
      --bg: #f4f2ee;
      --panel: #ffffff;
      --ink: #141414;
      --muted: #5e5e5e;
      --accent: #1b9aaa;
      --accent-2: #f18f01;
      --border: #e3e0da;
      --shadow: rgba(0, 0, 0, 0.06);
      --radius: 16px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Work Sans", "Source Sans 3", sans-serif;
      background:
        radial-gradient(1200px circle at 10% -10%, #fff5dd, transparent 40%),
        radial-gradient(900px circle at 110% 10%, #e9f7f8, transparent 35%),
        var(--bg);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1100px;
      margin: 36px auto 80px;
      padding: 0 20px;
      animation: fadeUp 0.6s ease-out;
    }}
    header {{
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-bottom: 24px;
    }}
    h1 {{
      font-size: 32px;
      margin: 0;
      letter-spacing: -0.5px;
    }}
    .sub {{
      color: var(--muted);
      font-size: 14px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 18px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 16px 18px;
      box-shadow: 0 12px 24px var(--shadow);
      display: flex;
      flex-direction: column;
      gap: 12px;
      animation: cardIn 0.5s ease-out;
    }}
    .card-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }}
    .pill {{
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      background: #eef6f6;
    }}
    .sev-low {{ color: #1d7f5f; }}
    .sev-med {{ color: #b45309; }}
    .sev-high {{ color: #b91c1c; }}
    .sev-unk {{ color: #4b5563; }}
    .source {{
      font-weight: 600;
      font-size: 14px;
    }}
    .card-body {{
      display: grid;
      gap: 8px;
      font-size: 13px;
      color: var(--muted);
    }}
    .card-body span {{
      display: inline-block;
      min-width: 90px;
      color: var(--ink);
      font-weight: 600;
    }}
    .card-link {{
      text-decoration: none;
      color: var(--ink);
      font-weight: 600;
      padding: 10px 12px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: #faf8f4;
      text-align: center;
    }}
    .card-link:hover {{
      border-color: var(--accent);
      color: var(--accent);
    }}
    .empty {{
      padding: 30px;
      text-align: center;
      color: var(--muted);
      border: 1px dashed var(--border);
      border-radius: var(--radius);
      background: rgba(255, 255, 255, 0.6);
    }}
    @keyframes fadeUp {{
      from {{ opacity: 0; transform: translateY(12px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    @keyframes cardIn {{
      from {{ opacity: 0; transform: translateY(8px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    @media (max-width: 720px) {{
      h1 {{ font-size: 26px; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>EFCD Reports</h1>
      <div class="sub">Latest report per source. Severity is ranked high to low.</div>
    </header>
    <section class="grid">
      {''.join(cards)}
    </section>
  </div>
</body>
</html>
"""
    return html_out
