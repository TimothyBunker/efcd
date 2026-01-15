import json
import os
from glob import glob
from datetime import datetime, timezone


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_profile(out_dir, source_id, profile):
    base = os.path.join(out_dir, "profiles", source_id)
    _ensure_dir(base)
    filename = f"{profile['profile_id']}.json"
    path = os.path.join(base, filename)
    _write_json(path, profile)
    return path


def save_report(out_dir, source_id, report):
    base = os.path.join(out_dir, "reports", source_id)
    _ensure_dir(base)
    filename = f"{report['report_id']}.json"
    path = os.path.join(base, filename)
    _write_json(path, report)
    return path


def list_profiles(out_dir, source_id):
    pattern = os.path.join(out_dir, "profiles", source_id, "*.json")
    return sorted(glob(pattern))


def list_reports(out_dir, source_id):
    pattern = os.path.join(out_dir, "reports", source_id, "*.json")
    return sorted(glob(pattern))


def list_report_sources(out_dir):
    base = os.path.join(out_dir, "reports")
    if not os.path.isdir(base):
        return []
    sources = []
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name)
        if os.path.isdir(path):
            sources.append(name)
    return sources


def load_latest_profiles(out_dir, source_id, count=2):
    files = list_profiles(out_dir, source_id)
    if len(files) < count:
        return []
    latest = files[-count:]
    return [_read_json(p) for p in latest]


def load_latest_report(out_dir, source_id):
    files = list_reports(out_dir, source_id)
    if not files:
        return None
    return _read_json(files[-1])


def find_profile_path(out_dir, source_id, profile_id):
    path = os.path.join(out_dir, "profiles", source_id, f"{profile_id}.json")
    return path if os.path.exists(path) else None


def find_report_path(out_dir, source_id, report_id):
    path = os.path.join(out_dir, "reports", source_id, f"{report_id}.json")
    return path if os.path.exists(path) else None


def load_profile(path):
    return _read_json(path)


def load_report(path):
    return _read_json(path)


def _baseline_path(out_dir, source_id):
    return os.path.join(out_dir, "baselines", f"{source_id}.json")


def save_baseline(out_dir, source_id, profile_id):
    base = os.path.join(out_dir, "baselines")
    _ensure_dir(base)
    path = _baseline_path(out_dir, source_id)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "source_id": source_id,
        "profile_id": profile_id,
        "set_at": now,
    }
    _write_json(path, payload)
    return path


def load_baseline(out_dir, source_id):
    path = _baseline_path(out_dir, source_id)
    if not os.path.exists(path):
        return None
    return _read_json(path)


def clear_baseline(out_dir, source_id):
    path = _baseline_path(out_dir, source_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
