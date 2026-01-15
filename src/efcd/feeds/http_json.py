import json
import urllib.request


def _extract_data(obj, data_path=None):
    if data_path:
        parts = data_path.split(".")
        cur = obj
        for part in parts:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return []
        return cur if isinstance(cur, list) else []

    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("data", "items", "features", "results", "records"):
            if key in obj and isinstance(obj[key], list):
                return obj[key]
    return []


def fetch_http_json(uri, data_path=None, timeout=30):
    req = urllib.request.Request(uri, headers={"User-Agent": "efcd/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        bytes_size = len(raw)
        data = json.loads(raw.decode("utf-8", errors="ignore"))
    rows = _extract_data(data, data_path=data_path)
    # Filter to dict-like records only
    rows = [r for r in rows if isinstance(r, dict)]
    return rows, bytes_size
