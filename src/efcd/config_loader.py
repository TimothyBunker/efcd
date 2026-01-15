import json
import os

from .config import DEFAULT_THRESHOLDS

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


DEFAULT_ALERT = {
    "min_severity": "medium",
    "min_confidence": 0.6,
    "persist_runs": 1,
}

DEFAULTS = {
    "baseline_mode": "latest",
    "baseline_window": 7,
    "seasonality": "none",
    "alert": DEFAULT_ALERT,
    "thresholds": DEFAULT_THRESHOLDS,
}


def _deep_merge(base, override):
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _normalize_config(config):
    config = config or {}
    defaults = _deep_merge(DEFAULTS, config.get("defaults", {}))
    sources = config.get("sources", {}) or {}
    return {"defaults": defaults, "sources": sources}


def load_config(path=None):
    if path is None:
        for candidate in ("feeds.yml", "feeds.yaml", "feeds.json"):
            if os.path.exists(candidate):
                path = candidate
                break

    if path is None:
        return _normalize_config({})

    if not os.path.exists(path):
        raise FileNotFoundError(path)

    _, ext = os.path.splitext(path)
    ext = ext.lower()
    with open(path, "r", encoding="utf-8") as f:
        if ext == ".json":
            data = json.load(f)
        elif ext in (".yml", ".yaml"):
            if yaml is None:
                raise RuntimeError("PyYAML is required to load YAML config files")
            data = yaml.safe_load(f) or {}
        else:
            raise ValueError(f"unsupported config extension: {ext}")

    return _normalize_config(data)


def get_source_config(config, source_id):
    defaults = config.get("defaults", {})
    source = (config.get("sources", {}) or {}).get(source_id, {})
    return _deep_merge(defaults, source)
