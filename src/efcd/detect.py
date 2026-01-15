import math
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone

from .config import DEFAULT_THRESHOLDS


SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3}
TOP_K = 10


def parse_profile_id(profile_id):
    try:
        return datetime.strptime(profile_id, "%Y%m%dT%H%M%SZ")
    except (TypeError, ValueError):
        return None


def seasonality_key(dt, seasonality):
    if dt is None:
        return None
    if seasonality == "weekday":
        return dt.weekday()
    if seasonality == "hour":
        return dt.hour
    if seasonality == "weekday-hour":
        return (dt.weekday(), dt.hour)
    return None


def seasonality_bucket(profile_id, seasonality):
    if not seasonality or seasonality == "none":
        return None
    dt = parse_profile_id(profile_id)
    return seasonality_key(dt, seasonality)


def _max_severity(current, new):
    if SEVERITY_ORDER.get(new, 0) > SEVERITY_ORDER.get(current, 0):
        return new
    return current


def _median(values):
    if not values:
        return None
    return statistics.median(values)


def aggregate_profiles(profiles):
    if not profiles:
        return None

    row_counts = []
    for profile in profiles:
        row_counts.append(profile.get("stats", {}).get("row_count") or 0)

    avg_rows = int(round(sum(row_counts) / len(row_counts))) if row_counts else 0
    source = profiles[-1].get("source", {})

    field_entries = defaultdict(list)
    for profile, row_count in zip(profiles, row_counts):
        for field in profile.get("fields", []):
            field_entries[field.get("name")].append((field, row_count))

    fields_out = []
    for name, entries in sorted(field_entries.items()):
        type_counts = Counter()
        present_counts = []
        null_rate_weighted = []
        distinct_counts = []
        distinct_overflow = False
        top_values_counter = Counter()

        numeric_means = []
        numeric_stdevs = []
        numeric_counts = []
        numeric_mins = []
        numeric_maxs = []
        p50s = []
        p95s = []

        min_lens = []
        max_lens = []

        for field, row_count in entries:
            inferred_type = field.get("inferred_type") or "unknown"
            type_counts[inferred_type] += 1

            present = field.get("present_count") or 0
            present_counts.append(present)

            null_rate = field.get("null_rate") or 0.0
            null_rate_weighted.append((null_rate, row_count))

            distinct = field.get("distinct_count")
            if distinct is not None:
                distinct_counts.append(distinct)

            if field.get("distinct_overflow"):
                distinct_overflow = True

            for value, count in field.get("top_values", []):
                top_values_counter[value] += count

            numeric = field.get("numeric") or {}
            mean = numeric.get("mean")
            stdev = numeric.get("stdev")
            if mean is not None:
                non_null = int(round((1.0 - null_rate) * row_count))
                if non_null > 0:
                    numeric_means.append(mean)
                    numeric_stdevs.append(stdev if stdev is not None else 0.0)
                    numeric_counts.append(non_null)

            if numeric.get("min") is not None:
                numeric_mins.append(numeric["min"])
            if numeric.get("max") is not None:
                numeric_maxs.append(numeric["max"])
            if numeric.get("p50") is not None:
                p50s.append(numeric["p50"])
            if numeric.get("p95") is not None:
                p95s.append(numeric["p95"])

            string_info = field.get("string") or {}
            if string_info.get("min_len") is not None:
                min_lens.append(string_info["min_len"])
            if string_info.get("max_len") is not None:
                max_lens.append(string_info["max_len"])

        inferred_type = type_counts.most_common(1)[0][0] if type_counts else "unknown"
        avg_present = int(round(sum(present_counts) / len(present_counts))) if present_counts else 0
        missing_count = max(avg_rows - avg_present, 0)

        null_rate = 0.0
        if null_rate_weighted:
            total_rows = sum(weight for _, weight in null_rate_weighted)
            if total_rows > 0:
                null_rate = sum(rate * weight for rate, weight in null_rate_weighted) / total_rows

        distinct_count = int(round(_median(distinct_counts))) if distinct_counts else 0

        numeric_stats = {"min": None, "max": None, "mean": None, "stdev": None, "p50": None, "p95": None}
        if numeric_counts:
            total_n = sum(numeric_counts)
            mean = sum(n * m for n, m in zip(numeric_counts, numeric_means)) / total_n
            mean_sq = sum(
                n * ((s or 0.0) ** 2 + m ** 2)
                for n, m, s in zip(numeric_counts, numeric_means, numeric_stdevs)
            ) / total_n
            variance = max(mean_sq - mean ** 2, 0.0)
            numeric_stats = {
                "min": min(numeric_mins) if numeric_mins else None,
                "max": max(numeric_maxs) if numeric_maxs else None,
                "mean": mean,
                "stdev": math.sqrt(variance),
                "p50": _median(p50s),
                "p95": _median(p95s),
            }

        min_len = min(min_lens) if min_lens else None
        max_len = max(max_lens) if max_lens else None

        fields_out.append({
            "name": name,
            "inferred_type": inferred_type,
            "present_count": avg_present,
            "missing_count": missing_count,
            "null_rate": round(null_rate, 6),
            "distinct_count": distinct_count,
            "distinct_overflow": distinct_overflow,
            "top_values": top_values_counter.most_common(TOP_K),
            "numeric": numeric_stats,
            "string": {"min_len": min_len, "max_len": max_len},
        })

    profile_id = f"rolling-agg-{profiles[0].get('profile_id')}-{profiles[-1].get('profile_id')}"
    profile = {
        "profile_id": profile_id,
        "source": source,
        "sample": {"rows": avg_rows, "bytes": None},
        "stats": {"row_count": avg_rows, "field_count": len(fields_out)},
        "fields": fields_out,
    }
    return profile


def seasonality_match(profile_a, profile_b, seasonality):
    if not seasonality or seasonality == "none":
        return False
    dt_a = parse_profile_id(profile_a.get("profile_id")) if profile_a else None
    dt_b = parse_profile_id(profile_b.get("profile_id")) if profile_b else None
    key_a = seasonality_key(dt_a, seasonality)
    key_b = seasonality_key(dt_b, seasonality)
    return key_a is not None and key_a == key_b


def _severity_at_least(severity, min_severity):
    return SEVERITY_ORDER.get(severity, 0) >= SEVERITY_ORDER.get(min_severity, 0)


def _importance_adjusted_confidence(base_confidence, importance):
    if importance == "high":
        return max(0.0, base_confidence - 0.1)
    if importance == "low":
        return min(1.0, base_confidence + 0.1)
    return base_confidence


def _score_change(change, thresholds, importance):
    change_type = change.get("type")
    delta = change.get("delta")

    if change_type in ("type_change", "contract_type_violation"):
        confidence = 0.95
    elif change_type in ("schema_added", "schema_removed", "contract_field_missing"):
        confidence = 0.85
    elif change_type in ("regex_mismatch", "enum_violation", "range_violation"):
        confidence = 0.9
    elif change_type == "null_rate_shift":
        base = thresholds.get("null_rate_delta", 0.1)
        confidence = min(0.95, 0.5 + (delta or 0.0) / (base * 2.0))
    elif change_type == "distinct_shift":
        base = thresholds.get("distinct_ratio", 2.0)
        ratio = delta or 1.0
        distance = abs(ratio - 1.0)
        confidence = min(0.9, 0.4 + distance / max(base - 1.0, 0.5))
    elif change_type == "mean_shift":
        base = thresholds.get("mean_std_multiplier", 3.0)
        stdev = change.get("baseline_stdev") or 0.0
        if stdev > 0:
            z = (delta or 0.0) / stdev
            confidence = min(0.95, 0.5 + z / (base * 2.0))
        else:
            confidence = 0.6
    elif change_type == "row_count_shift":
        base = thresholds.get("row_count_delta", 0.2)
        confidence = min(0.9, 0.5 + (delta or 0.0) / (base * 2.0))
    else:
        confidence = 0.6

    confidence = max(0.0, min(1.0, confidence))
    return _importance_adjusted_confidence(confidence, importance)


def apply_contract_checks(latest_profile, field_rules):
    changes = []
    fields = {field.get("name"): field for field in latest_profile.get("fields", [])}

    for field_name, rules in (field_rules or {}).items():
        rules = rules or {}
        field = fields.get(field_name)
        required = rules.get("required", False)
        if field is None:
            if required:
                changes.append({
                    "field": field_name,
                    "type": "contract_field_missing",
                    "metric": "presence",
                    "before": "present",
                    "after": "missing",
                    "delta": None,
                    "severity": "high",
                    "recommendation": "investigate",
                })
            continue

        expected_type = rules.get("type")
        if expected_type and field.get("inferred_type") != expected_type:
            changes.append({
                "field": field_name,
                "type": "contract_type_violation",
                "metric": "inferred_type",
                "before": expected_type,
                "after": field.get("inferred_type"),
                "delta": None,
                "severity": "high",
                "recommendation": "investigate",
            })

        enum_vals = rules.get("enum")
        if enum_vals:
            allowed = set(str(v) for v in enum_vals)
            violations = [val for val, _ in field.get("top_values", []) if str(val) not in allowed]
            if violations:
                changes.append({
                    "field": field_name,
                    "type": "enum_violation",
                    "metric": "top_values",
                    "before": "allowed",
                    "after": ",".join(violations[:5]),
                    "delta": len(violations),
                    "severity": "high",
                    "recommendation": "investigate",
                })

        regex = rules.get("regex")
        if regex:
            try:
                pattern = re.compile(regex)
            except re.error:
                pattern = None
            if pattern is not None:
                mismatches = [val for val, _ in field.get("top_values", []) if not pattern.match(str(val))]
                if mismatches:
                    changes.append({
                        "field": field_name,
                        "type": "regex_mismatch",
                        "metric": "top_values",
                        "before": regex,
                        "after": ",".join(mismatches[:5]),
                        "delta": len(mismatches),
                        "severity": "high",
                        "recommendation": "investigate",
                    })

        min_val = rules.get("min")
        max_val = rules.get("max")
        numeric = field.get("numeric", {})
        if min_val is not None and numeric.get("min") is not None and numeric["min"] < min_val:
            changes.append({
                "field": field_name,
                "type": "range_violation",
                "metric": "min",
                "before": min_val,
                "after": numeric.get("min"),
                "delta": numeric.get("min") - min_val,
                "severity": "high",
                "recommendation": "investigate",
            })

        if max_val is not None and numeric.get("max") is not None and numeric["max"] > max_val:
            changes.append({
                "field": field_name,
                "type": "range_violation",
                "metric": "max",
                "before": max_val,
                "after": numeric.get("max"),
                "delta": numeric.get("max") - max_val,
                "severity": "high",
                "recommendation": "investigate",
            })

    return changes


def apply_alerting(changes, alert_cfg, thresholds, field_rules, prior_reports, seasonality_bucket_value=None):
    alert_cfg = alert_cfg or {}
    min_sev = alert_cfg.get("min_severity", "medium")
    min_conf = alert_cfg.get("min_confidence", 0.6)
    persist_runs = max(int(alert_cfg.get("persist_runs", 1)), 1)

    if seasonality_bucket_value is not None:
        prior_reports = [
            report
            for report in prior_reports
            if report.get("seasonality_bucket") == seasonality_bucket_value
        ]

    prior_signatures = []
    for report in prior_reports:
        sigs = {(c.get("field"), c.get("type")) for c in report.get("changes", [])}
        prior_signatures.append(sigs)

    for change in changes:
        field_name = change.get("field")
        field_cfg = (field_rules or {}).get(field_name, {}) or {}
        importance = field_cfg.get("importance", "medium")
        field_alert = field_cfg.get("alert", {}) or {}
        eff_min_sev = field_alert.get("min_severity", min_sev)
        eff_min_conf = field_alert.get("min_confidence", min_conf)
        eff_persist = max(int(field_alert.get("persist_runs", persist_runs)), 1)
        confidence = _score_change(change, thresholds, importance)
        change["confidence"] = round(confidence, 3)
        change["importance"] = importance

        signature = (change.get("field"), change.get("type"))
        persistence = 1
        for sigs in prior_signatures:
            if signature in sigs:
                persistence += 1
            else:
                break
        change["persistence_runs"] = persistence

        effective_min_conf = _importance_adjusted_confidence(eff_min_conf, importance)
        effective_sev = change.get("severity")
        if importance == "high" and effective_sev == "low":
            effective_sev = "medium"

        change["alert"] = (
            _severity_at_least(effective_sev, eff_min_sev)
            and confidence >= effective_min_conf
            and persistence >= eff_persist
        )

    return changes


def compare_profiles(baseline, latest, thresholds=None):
    merged = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        merged.update(thresholds)
    thresholds = merged
    changes = []
    severity = "low"

    baseline_fields = {f["name"]: f for f in baseline.get("fields", [])}
    latest_fields = {f["name"]: f for f in latest.get("fields", [])}

    baseline_names = set(baseline_fields)
    latest_names = set(latest_fields)

    added = sorted(latest_names - baseline_names)
    removed = sorted(baseline_names - latest_names)

    for name in added:
        changes.append({
            "field": name,
            "type": "schema_added",
            "metric": "field",
            "before": None,
            "after": name,
            "delta": None,
            "severity": "medium",
            "recommendation": "investigate",
        })
        severity = _max_severity(severity, "medium")

    for name in removed:
        changes.append({
            "field": name,
            "type": "schema_removed",
            "metric": "field",
            "before": name,
            "after": None,
            "delta": None,
            "severity": "medium",
            "recommendation": "investigate",
        })
        severity = _max_severity(severity, "medium")

    common = sorted(baseline_names & latest_names)
    for name in common:
        b = baseline_fields[name]
        l = latest_fields[name]

        if b.get("inferred_type") != l.get("inferred_type"):
            changes.append({
                "field": name,
                "type": "type_change",
                "metric": "inferred_type",
                "before": b.get("inferred_type"),
                "after": l.get("inferred_type"),
                "delta": None,
                "severity": "high",
                "recommendation": "investigate",
            })
            severity = _max_severity(severity, "high")

        null_delta = abs((l.get("null_rate") or 0.0) - (b.get("null_rate") or 0.0))
        if null_delta > thresholds["null_rate_delta"]:
            changes.append({
                "field": name,
                "type": "null_rate_shift",
                "metric": "null_rate",
                "before": b.get("null_rate"),
                "after": l.get("null_rate"),
                "delta": round(null_delta, 6),
                "severity": "medium",
                "recommendation": "investigate",
            })
            severity = _max_severity(severity, "medium")

        b_distinct = b.get("distinct_count") or 0
        l_distinct = l.get("distinct_count") or 0
        if b_distinct > 0 and l_distinct > 0:
            ratio = l_distinct / b_distinct
            if ratio > thresholds["distinct_ratio"] or ratio < (1.0 / thresholds["distinct_ratio"]):
                changes.append({
                    "field": name,
                    "type": "distinct_shift",
                    "metric": "distinct_count",
                    "before": b_distinct,
                    "after": l_distinct,
                    "delta": round(ratio, 3),
                    "severity": "medium",
                    "recommendation": "investigate",
                })
                severity = _max_severity(severity, "medium")

        b_num = b.get("numeric", {})
        l_num = l.get("numeric", {})
        if b_num.get("mean") is not None and l_num.get("mean") is not None:
            stdev = b_num.get("stdev") or 0.0
            if stdev > 0:
                mean_delta = abs(l_num["mean"] - b_num["mean"])
                if mean_delta > thresholds["mean_std_multiplier"] * stdev:
                    changes.append({
                        "field": name,
                        "type": "mean_shift",
                        "metric": "mean",
                        "before": b_num.get("mean"),
                        "after": l_num.get("mean"),
                        "delta": round(mean_delta, 6),
                        "baseline_stdev": stdev,
                        "severity": "medium",
                        "recommendation": "investigate",
                    })
                    severity = _max_severity(severity, "medium")

    # Row count change
    b_rows = baseline.get("stats", {}).get("row_count") or 0
    l_rows = latest.get("stats", {}).get("row_count") or 0
    if b_rows > 0:
        row_delta = abs(l_rows - b_rows) / b_rows
        if row_delta > thresholds["row_count_delta"]:
            changes.append({
                "field": "__rows__",
                "type": "row_count_shift",
                "metric": "row_count",
                "before": b_rows,
                "after": l_rows,
                "delta": round(row_delta, 6),
                "severity": "medium",
                "recommendation": "investigate",
            })
            severity = _max_severity(severity, "medium")

    now = datetime.now(timezone.utc)
    report_id = now.strftime("%Y%m%dT%H%M%SZ")
    created_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    report = {
        "report_id": report_id,
        "source_id": latest.get("source", {}).get("id"),
        "baseline_profile_id": baseline.get("profile_id"),
        "latest_profile_id": latest.get("profile_id"),
        "created_at": created_at,
        "severity": severity,
        "changes": changes,
    }
    return report
