import argparse
import json
import os
import sys

from .alerts import send_webhook
from .config import DEFAULT_OUT_DIR, DEFAULT_SAMPLE_ROWS
from .config_loader import get_source_config, load_config
from .detect import (
    aggregate_profiles,
    apply_alerting,
    apply_contract_checks,
    compare_profiles,
    seasonality_bucket,
    seasonality_match,
)
from .feeds import fetch_http_json, load_local_csv, load_local_jsonl
from .profile import profile_rows
from .render import render_index_html, render_report_html
from .store import (
    clear_baseline,
    find_profile_path,
    load_baseline,
    load_latest_profiles,
    load_latest_report,
    load_profile,
    load_report,
    list_report_sources,
    list_reports,
    list_profiles,
    save_baseline,
    save_profile,
    save_report,
)


def _load_rows(source_type, uri, data_path=None):
    if source_type == "http-json":
        return fetch_http_json(uri, data_path=data_path)
    if source_type == "local-jsonl":
        return load_local_jsonl(uri)
    if source_type == "local-csv":
        return load_local_csv(uri)
    raise ValueError(f"Unsupported source type: {source_type}")


def _profile(args):
    config = load_config(args.config)
    source_cfg = get_source_config(config, args.source_id)
    data_path = args.data_path if args.data_path is not None else source_cfg.get("data_path")
    sample_rows = args.sample_rows if args.sample_rows is not None else source_cfg.get("sample_rows", DEFAULT_SAMPLE_ROWS)

    rows, bytes_size = _load_rows(args.source_type, args.uri, data_path=data_path)
    source = {"id": args.source_id, "type": args.source_type, "uri": args.uri}
    profile = profile_rows(rows, source, sample_rows=sample_rows, bytes_size=bytes_size)
    path = save_profile(args.out_dir, args.source_id, profile)
    print(f"saved profile: {path}")
    return profile, path


def _detect(args):
    config = load_config(args.config)
    source_cfg = get_source_config(config, args.source_id)
    thresholds = source_cfg.get("thresholds", {})

    baseline_mode = args.baseline_mode or source_cfg.get("baseline_mode", "latest")
    baseline_window = args.baseline_window if args.baseline_window is not None else source_cfg.get("baseline_window", 7)
    seasonality = args.seasonality or source_cfg.get("seasonality", "none")

    baseline_meta = {"mode": None, "window": None, "profile_id": None, "profile_ids": None, "set_at": None}
    if args.baseline_path and args.latest_path:
        baseline = load_profile(args.baseline_path)
        latest = load_profile(args.latest_path)
        baseline_meta["mode"] = "explicit"
        baseline_meta["profile_id"] = baseline.get("profile_id")
    else:
        mode = baseline_mode
        if mode == "latest":
            profiles = load_latest_profiles(args.out_dir, args.source_id, count=2)
            if len(profiles) < 2:
                print("not enough profiles to compare")
                return None, None
            baseline, latest = profiles[0], profiles[1]
            baseline_meta["mode"] = "latest"
            baseline_meta["profile_id"] = baseline.get("profile_id")
        elif mode == "rolling":
            window = max(baseline_window, 1)
            profiles = load_latest_profiles(args.out_dir, args.source_id, count=window + 1)
            if len(profiles) < (window + 1):
                print("not enough profiles for rolling baseline")
                return None, None
            baseline, latest = profiles[0], profiles[-1]
            baseline_meta["mode"] = "rolling"
            baseline_meta["window"] = window
            baseline_meta["profile_id"] = baseline.get("profile_id")
        elif mode == "pinned":
            baseline_meta = load_baseline(args.out_dir, args.source_id)
            if baseline_meta is None:
                print("no pinned baseline set")
                return None, None
            baseline_id = baseline_meta.get("profile_id")
            baseline_path = find_profile_path(args.out_dir, args.source_id, baseline_id)
            if baseline_path is None:
                print("pinned baseline profile not found")
                return None, None
            baseline = load_profile(baseline_path)
            latest_list = load_latest_profiles(args.out_dir, args.source_id, count=1)
            if not latest_list:
                print("no latest profile found")
                return None, None
            latest = latest_list[0]
            baseline_meta["mode"] = "pinned"
            baseline_meta["profile_id"] = baseline.get("profile_id")
        elif mode == "rolling-agg":
            window = max(baseline_window, 1)
            profiles = load_latest_profiles(args.out_dir, args.source_id, count=window + 1)
            if len(profiles) < (window + 1):
                print("not enough profiles for rolling aggregate baseline")
                return None, None
            baseline_profiles = profiles[:-1]
            latest = profiles[-1]
            baseline = aggregate_profiles(baseline_profiles)
            baseline_meta["mode"] = "rolling-agg"
            baseline_meta["window"] = window
            baseline_meta["profile_id"] = baseline.get("profile_id") if baseline else None
            baseline_meta["profile_ids"] = [p.get("profile_id") for p in baseline_profiles]
        elif mode in ("seasonal", "seasonal-agg"):
            all_paths = list_profiles(args.out_dir, args.source_id)
            if len(all_paths) < 2:
                print("not enough profiles for seasonal baseline")
                return None, None
            latest = load_profile(all_paths[-1])
            candidates = [load_profile(p) for p in all_paths[:-1]]
            matches = [p for p in candidates if seasonality_match(p, latest, seasonality)]
            if not matches:
                print("no seasonal matches found")
                return None, None
            if mode == "seasonal":
                baseline = matches[-1]
                baseline_meta["mode"] = "seasonal"
                baseline_meta["profile_id"] = baseline.get("profile_id")
            else:
                window = max(baseline_window, 1)
                baseline_profiles = matches[-window:]
                baseline = aggregate_profiles(baseline_profiles)
                baseline_meta["mode"] = "seasonal-agg"
                baseline_meta["window"] = window
                baseline_meta["profile_id"] = baseline.get("profile_id") if baseline else None
                baseline_meta["profile_ids"] = [p.get("profile_id") for p in baseline_profiles]
            baseline_meta["seasonality"] = seasonality
        else:
            print(f"unsupported baseline mode: {mode}")
            return None, None

    report = compare_profiles(baseline, latest, thresholds=thresholds)

    field_rules = source_cfg.get("fields", {})
    report["changes"].extend(apply_contract_checks(latest, field_rules))

    alert_cfg = source_cfg.get("alert", {})
    prior_reports = []
    report_files = list_reports(args.out_dir, args.source_id)
    max_persist = max(int(alert_cfg.get("persist_runs", 1)), 1)
    for field_cfg in (source_cfg.get("fields", {}) or {}).values():
        field_alert = (field_cfg or {}).get("alert", {})
        max_persist = max(max_persist, int(field_alert.get("persist_runs", 1)))

    if report_files:
        window = max(max_persist - 1, 0)
        if window > 0:
            for path in reversed(report_files[-window:]):
                prior_reports.append(load_report(path))

    seasonality_bucket_value = seasonality_bucket(latest.get("profile_id"), seasonality)
    apply_alerting(
        report["changes"],
        alert_cfg,
        thresholds,
        field_rules,
        prior_reports,
        seasonality_bucket_value=seasonality_bucket_value,
    )

    alerts = [c for c in report["changes"] if c.get("alert")]
    severity_order = {"low": 1, "medium": 2, "high": 3}
    alert_sev = "low"
    for change in alerts:
        sev = change.get("severity") or "low"
        if severity_order.get(sev, 0) > severity_order.get(alert_sev, 0):
            alert_sev = sev

    report["alert"] = bool(alerts)
    report["alert_count"] = len(alerts)
    report["alert_severity"] = alert_sev if alerts else "low"
    report["baseline_meta"] = baseline_meta
    report["latest_meta"] = {"profile_id": latest.get("profile_id")}
    report["baseline_summary"] = baseline.get("stats", {}) if baseline else {}
    report["latest_summary"] = latest.get("stats", {}) if latest else {}
    report["seasonality"] = seasonality
    report["seasonality_bucket"] = seasonality_bucket_value
    path = save_report(args.out_dir, args.source_id, report)
    print(f"saved report: {path}")
    print(json.dumps({"severity": report["severity"], "changes": len(report["changes"]), "alerts": report["alert_count"]}, indent=2))
    return report, path


def _run(args):
    _, _ = _profile(args)
    report, path = _detect(args)
    if report and args.webhook_url:
        if report.get("alert"):
            payload = {
                "source_id": report.get("source_id"),
                "severity": report.get("severity"),
                "alert_severity": report.get("alert_severity"),
                "alert_count": report.get("alert_count"),
                "changes": report.get("changes"),
                "report_path": path,
            }
            status = send_webhook(args.webhook_url, payload)
            print(f"webhook status: {status}")
        else:
            print("no alert triggered; webhook skipped")


def _baseline(args):
    if args.clear:
        removed = clear_baseline(args.out_dir, args.source_id)
        print("baseline cleared" if removed else "no baseline to clear")
        return True

    if args.use_latest and args.profile_id:
        print("provide only one of --use-latest or --profile-id")
        return None

    if args.use_latest:
        latest_list = load_latest_profiles(args.out_dir, args.source_id, count=1)
        if not latest_list:
            print("no profiles found")
            return None
        profile_id = latest_list[0].get("profile_id")
        path = save_baseline(args.out_dir, args.source_id, profile_id)
        print(f"baseline set: {profile_id} ({path})")
        return True

    if args.profile_id:
        path = save_baseline(args.out_dir, args.source_id, args.profile_id)
        print(f"baseline set: {args.profile_id} ({path})")
        return True

    current = load_baseline(args.out_dir, args.source_id)
    if current is None:
        print("no pinned baseline set")
        return False
    print(json.dumps(current, indent=2))
    return True


def _render(args):
    if not args.report_path and not args.source_id:
        print("provide --report-path or --source-id")
        return None

    if args.report_path:
        report = load_report(args.report_path)
        source_id = report.get("source_id")
    else:
        report = load_latest_report(args.out_dir, args.source_id)
        if report is None:
            print("no reports found")
            return None
        source_id = args.source_id

    source_id = source_id or "unknown"

    baseline = None
    latest = None
    baseline_id = report.get("baseline_profile_id")
    latest_id = report.get("latest_profile_id")

    if baseline_id and source_id:
        baseline_path = find_profile_path(args.out_dir, source_id, baseline_id)
        if baseline_path:
            baseline = load_profile(baseline_path)
    if latest_id and source_id:
        latest_path = find_profile_path(args.out_dir, source_id, latest_id)
        if latest_path:
            latest = load_profile(latest_path)

    html = render_report_html(report, baseline=baseline, latest=latest)
    if args.out_path:
        out_path = args.out_path
    else:
        report_id = report.get("report_id", "report")
        out_path = f"{args.out_dir}/reports/{source_id}/{report_id}.html"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"saved html: {out_path}")
    return out_path


def _index(args):
    sources = list_report_sources(args.out_dir)
    entries = []
    for source_id in sources:
        report_files = list_reports(args.out_dir, source_id)
        if not report_files:
            continue
        latest_report_path = report_files[-1]
        report = load_report(latest_report_path)
        report_id = report.get("report_id")
        html_path = latest_report_path.replace(".json", ".html")
        link = html_path if os.path.exists(html_path) else latest_report_path
        severity = report.get("severity", "unknown")
        entries.append({
            "source_id": source_id,
            "severity": severity,
            "severity_class": f"sev-{severity}" if severity else "sev-unk",
            "changes": len(report.get("changes", [])),
            "report_id": report_id,
            "created_at": report.get("created_at", ""),
            "baseline_mode": (report.get("baseline_meta", {}) or {}).get("mode"),
            "baseline_window": (report.get("baseline_meta", {}) or {}).get("window"),
            "alert_count": report.get("alert_count", 0),
            "alert_severity": report.get("alert_severity", "low"),
            "seasonality_bucket": report.get("seasonality_bucket"),
            "link": link,
        })

    html = render_index_html(entries)
    out_path = args.out_path or f"{args.out_dir}/reports/index.html"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"saved index: {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(prog="efcd", description="External Feed Change Detector")
    sub = parser.add_subparsers(dest="command", required=True)

    profile = sub.add_parser("profile", help="fetch data and compute a profile")
    profile.add_argument("--source-id", required=True)
    profile.add_argument("--source-type", required=True, choices=["http-json", "local-jsonl", "local-csv"])
    profile.add_argument("--uri", required=True)
    profile.add_argument("--data-path", default=None)
    profile.add_argument("--sample-rows", type=int, default=None)
    profile.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    profile.add_argument("--config", default=None)
    profile.set_defaults(func=_profile)

    detect = sub.add_parser("detect", help="compare latest two profiles")
    detect.add_argument("--source-id", required=True)
    detect.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    detect.add_argument("--baseline-path", default=None)
    detect.add_argument("--latest-path", default=None)
    detect.add_argument(
        "--baseline-mode",
        default=None,
        choices=["latest", "pinned", "rolling", "rolling-agg", "seasonal", "seasonal-agg"],
        help="baseline selection: latest, pinned, rolling, rolling-agg, seasonal, seasonal-agg",
    )
    detect.add_argument(
        "--baseline-window",
        type=int,
        default=None,
        help="rolling modes use a window of N profiles",
    )
    detect.add_argument(
        "--seasonality",
        default=None,
        choices=["none", "weekday", "hour", "weekday-hour"],
        help="seasonality bucket for seasonal baselines",
    )
    detect.add_argument("--config", default=None)
    detect.set_defaults(func=_detect)

    run = sub.add_parser("run", help="profile + detect + optional alert")
    run.add_argument("--source-id", required=True)
    run.add_argument("--source-type", required=True, choices=["http-json", "local-jsonl", "local-csv"])
    run.add_argument("--uri", required=True)
    run.add_argument("--data-path", default=None)
    run.add_argument("--sample-rows", type=int, default=None)
    run.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    run.add_argument("--webhook-url", default=None)
    run.add_argument("--baseline-mode", default=None, choices=["latest", "pinned", "rolling", "rolling-agg", "seasonal", "seasonal-agg"])
    run.add_argument("--baseline-window", type=int, default=None)
    run.add_argument("--seasonality", default=None, choices=["none", "weekday", "hour", "weekday-hour"])
    run.add_argument("--config", default=None)
    run.set_defaults(func=_run)

    baseline = sub.add_parser("baseline", help="manage pinned baselines")
    baseline.add_argument("--source-id", required=True)
    baseline.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    baseline.add_argument("--profile-id", default=None)
    baseline.add_argument("--use-latest", action="store_true")
    baseline.add_argument("--clear", action="store_true")
    baseline.set_defaults(func=_baseline)

    render = sub.add_parser("render", help="render a report to HTML")
    render.add_argument("--source-id", default=None)
    render.add_argument("--report-path", default=None)
    render.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    render.add_argument("--out-path", default=None)
    render.set_defaults(func=_render)

    index = sub.add_parser("index", help="render a report index page")
    index.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    index.add_argument("--out-path", default=None)
    index.set_defaults(func=_index)

    args = parser.parse_args()
    result = args.func(args)
    if result is None:
        sys.exit(1)


if __name__ == "__main__":
    main()
