import json
import statistics
from collections import Counter
from datetime import datetime, timezone

TOP_K = 10
DISTINCT_LIMIT = 1000


def _flatten_dict(obj, parent_key=""):
    items = {}
    if not isinstance(obj, dict):
        return items
    for key, value in obj.items():
        full_key = f"{parent_key}.{key}" if parent_key else str(key)
        if isinstance(value, dict):
            items.update(_flatten_dict(value, full_key))
        else:
            items[full_key] = value
    return items


def _try_float(value):
    try:
        if isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _percentile(sorted_values, p):
    if not sorted_values:
        return None
    k = int(round((p / 100.0) * (len(sorted_values) - 1)))
    return sorted_values[k]


class _FieldAccumulator:
    def __init__(self):
        self.present_count = 0
        self.null_count = 0
        self.type_counts = Counter()
        self.numeric_values = []
        self.string_lengths = []
        self.distinct_values = set()
        self.distinct_overflow = False
        self.top_values = Counter()

    def add(self, value):
        self.present_count += 1

        if value is None or value == "":
            self.null_count += 1
            return

        if isinstance(value, bool):
            self.type_counts["bool"] += 1
            self._track_value(value)
            return

        if isinstance(value, (int, float)):
            self.type_counts["number"] += 1
            self.numeric_values.append(float(value))
            self._track_value(value)
            return

        if isinstance(value, list):
            self.type_counts["array"] += 1
            self._track_value(value)
            return

        if isinstance(value, dict):
            self.type_counts["object"] += 1
            self._track_value(value)
            return

        # Fallback: treat as string, but allow numeric parsing
        num = _try_float(value)
        if num is not None:
            self.type_counts["number"] += 1
            self.numeric_values.append(num)
        else:
            self.type_counts["string"] += 1
            self.string_lengths.append(len(str(value)))
        self._track_value(value)

    def _track_value(self, value):
        normalized = self._normalize_value(value)
        if normalized is None:
            return
        if not self.distinct_overflow:
            self.distinct_values.add(normalized)
            if len(self.distinct_values) > DISTINCT_LIMIT:
                self.distinct_overflow = True
                self.distinct_values = set(list(self.distinct_values)[:DISTINCT_LIMIT])
        self.top_values[normalized] += 1

    @staticmethod
    def _normalize_value(value):
        if value is None:
            return None
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, (list, dict)):
            return json.dumps(value, sort_keys=True)[:200]
        return str(value)[:200]


def _infer_type(type_counts):
    if not type_counts:
        return "unknown"
    # Choose the dominant type by count
    return type_counts.most_common(1)[0][0]


def _numeric_stats(values):
    if not values:
        return {"min": None, "max": None, "mean": None, "stdev": None, "p50": None, "p95": None}
    sorted_vals = sorted(values)
    mean = statistics.mean(sorted_vals)
    stdev = statistics.stdev(sorted_vals) if len(sorted_vals) > 1 else 0.0
    return {
        "min": sorted_vals[0],
        "max": sorted_vals[-1],
        "mean": mean,
        "stdev": stdev,
        "p50": _percentile(sorted_vals, 50),
        "p95": _percentile(sorted_vals, 95),
    }


def profile_rows(rows, source, sample_rows=10000, bytes_size=None):
    accumulators = {}
    total_rows = 0

    for row in rows:
        if total_rows >= sample_rows:
            break
        if not isinstance(row, dict):
            continue
        total_rows += 1
        flat = _flatten_dict(row)
        for field, value in flat.items():
            if field not in accumulators:
                accumulators[field] = _FieldAccumulator()
            accumulators[field].add(value)

    fields_out = []
    for name, acc in sorted(accumulators.items()):
        missing_count = total_rows - acc.present_count
        null_count = acc.null_count + missing_count
        null_rate = null_count / total_rows if total_rows else 0.0
        inferred_type = _infer_type(acc.type_counts)

        numeric = _numeric_stats(acc.numeric_values) if inferred_type == "number" else {
            "min": None, "max": None, "mean": None, "stdev": None, "p50": None, "p95": None
        }
        if inferred_type == "string":
            min_len = min(acc.string_lengths) if acc.string_lengths else None
            max_len = max(acc.string_lengths) if acc.string_lengths else None
        else:
            min_len = None
            max_len = None

        top_values = acc.top_values.most_common(TOP_K)

        fields_out.append({
            "name": name,
            "inferred_type": inferred_type,
            "present_count": acc.present_count,
            "missing_count": missing_count,
            "null_rate": round(null_rate, 6),
            "distinct_count": len(acc.distinct_values),
            "distinct_overflow": acc.distinct_overflow,
            "top_values": top_values,
            "numeric": numeric,
            "string": {"min_len": min_len, "max_len": max_len},
        })

    now = datetime.now(timezone.utc)
    profile_id = now.strftime("%Y%m%dT%H%M%SZ")
    fetched_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    profile = {
        "profile_id": profile_id,
        "source": {
            "id": source.get("id"),
            "type": source.get("type"),
            "uri": source.get("uri"),
            "fetched_at": fetched_at,
        },
        "sample": {
            "rows": total_rows,
            "bytes": bytes_size,
        },
        "stats": {
            "row_count": total_rows,
            "field_count": len(fields_out),
        },
        "fields": fields_out,
    }
    return profile
