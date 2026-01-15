# MVP Spec: External Feed Change Detector

## Problem
Third-party data feeds change without notice (schema, semantics, volume), causing broken pipelines, silent report errors, or model degradation. Most data observability tools focus on internal pipelines, not vendor feeds.

## MVP goals
- Detect schema and semantic drift in external feeds.
- Produce an actionable change report with severity and recommended action.
- Support easy, sidecar adoption without altering downstream systems.

## Non-goals (MVP)
- Full data lineage or end-to-end data observability.
- Complex ML anomaly detection models.
- Real-time streaming guarantees.

## Target user persona
Data platform lead or analytics engineer at a company that relies on 3rd-party feeds (fintech risk, pricing, ads, enrichment).

## Concrete, provably existing resources
- Public feeds: USGS Earthquakes, NOAA Weather, SEC EDGAR, FRED, OpenAQ, GDELT.
- Connectors: Airbyte/Meltano open connectors for common data sources.
- Validation libraries: Great Expectations, Soda Core, Deequ (optional to integrate).

## Inputs
### Feed types (MVP)
- `http-json`: HTTP GET returning JSON list or object containing a list.
- `local-jsonl`: JSON Lines file (one JSON object per line).
- `local-csv`: CSV file with headers.

### CLI inputs
- `--source-id` (string, required)
- `--source-type` (`http-json`, `local-jsonl`, `local-csv`, required for `profile`/`run`)
- `--uri` (string path or URL, required for `profile`/`run`)
- `--data-path` (optional dot path into JSON, e.g., `features` for GeoJSON)
- `--sample-rows` (int, default 10000)
- `--out-dir` (default `data`)
- `--webhook-url` (optional)

## Outputs
### Profile JSON (stored under `data/profiles/<source-id>/`)
- One file per run with timestamp-based ID.
- Contains source metadata, row counts, and per-field profiles.

### Change report JSON (stored under `data/reports/<source-id>/`)
- One file per detect run.
- Contains a list of detected changes with severity and recommended action.

### Alert payload
- JSON posted to a webhook if provided.
- Includes source, severity, summary, and a link/path to the report.

## Data schemas (logical)

### Profile
```
{
  "profile_id": "20250113T120301Z",
  "source": {
    "id": "usgs_quakes",
    "type": "http-json",
    "uri": "https://...",
    "fetched_at": "2025-01-13T12:03:01Z"
  },
  "sample": {
    "rows": 500,
    "bytes": 123456
  },
  "stats": {
    "row_count": 500,
    "field_count": 12
  },
  "fields": [
    {
      "name": "properties.mag",
      "inferred_type": "number",
      "present_count": 500,
      "missing_count": 0,
      "null_rate": 0.02,
      "distinct_count": 120,
      "top_values": [["0.3", 10], ["0.4", 9]],
      "numeric": {"min": 0.1, "max": 5.3, "mean": 1.1, "stdev": 0.7, "p50": 0.9, "p95": 2.7},
      "string": {"min_len": null, "max_len": null}
    }
  ]
}
```

### Change report
```
{
  "report_id": "20250113T120501Z",
  "source_id": "usgs_quakes",
  "baseline_profile_id": "20250112T120301Z",
  "latest_profile_id": "20250113T120301Z",
  "created_at": "2025-01-13T12:05:01Z",
  "severity": "high",
  "changes": [
    {
      "field": "properties.mag",
      "type": "mean_shift",
      "metric": "mean",
      "before": 1.1,
      "after": 2.6,
      "delta": 1.5,
      "severity": "medium",
      "recommendation": "investigate"
    }
  ]
}
```

## Detection rules (MVP)
- Schema changes: added/removed fields (severity: medium).
- Type changes: inferred type changed (severity: high).
- Null rate shifts: abs delta > 0.10 (severity: medium).
- Distinct count changes: ratio > 2.0 or < 0.5 (severity: medium).
- Numeric mean shift: abs delta > 3x baseline stdev (severity: medium).
- Row count change: abs delta > 20% (severity: medium).

## Success metrics (MVP)
- Detect a breaking or suspicious change in a live public feed within 1 run.
- Generate a report that a data engineer can act on in < 5 minutes.
- Convert 1 pilot to a paid trial using the report as evidence.
