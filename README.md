# External Feed Change Detector (EFCD)

Detect silent schema and semantic changes in third-party data feeds before they break pipelines.

## Quick start

Create a local venv if you want, then install the package in editable mode:

```
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

### Profile a public JSON feed

USGS Earthquake feed (GeoJSON). We pull the `features` list.

```
efcd profile \
  --source-id usgs_quakes \
  --source-type http-json \
  --uri https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson \
  --data-path features \
  --sample-rows 500
```

### Detect changes vs the previous profile

```
efcd detect --source-id usgs_quakes
```

### Render a report to HTML

```
efcd render --source-id usgs_quakes
```

### Baseline policies

Pin a baseline and compare future runs to it:

```
efcd baseline --source-id usgs_quakes --use-latest
efcd detect --source-id usgs_quakes --baseline-mode pinned
```

Use a rolling baseline (compare against N runs ago):

```
efcd detect --source-id usgs_quakes --baseline-mode rolling --baseline-window 7
```

Use a rolling aggregated baseline (merge stats across last N profiles):

```
efcd detect --source-id usgs_quakes --baseline-mode rolling-agg --baseline-window 7
```

Use a seasonal baseline (match weekday or hour buckets):

```
efcd detect --source-id usgs_quakes --baseline-mode seasonal --seasonality weekday
efcd detect --source-id usgs_quakes --baseline-mode seasonal-agg --seasonality weekday-hour --baseline-window 4
```

### Render a report index

```
efcd index --out-dir data
```

### One-shot run with a webhook alert

```
efcd run \
  --source-id usgs_quakes \
  --source-type http-json \
  --uri https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson \
  --data-path features \
  --webhook-url https://example.com/webhook
```

## Install via pipx

Install from the local repo:

```
./scripts/install_pipx.sh
```

If you prefer manual steps:

```
python -m pip install --user pipx
python -m pipx ensurepath
pipx install -e .
```

## Docker

Build the image:

```
docker build -t efcd .
```

Run a profile (mount data output and optional config):

```
docker run --rm \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/feeds.yml:/app/feeds.yml" \
  efcd profile \
  --source-id usgs_quakes \
  --source-type http-json \
  --uri https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson \
  --data-path features
```

Detect changes:

```
docker run --rm \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/feeds.yml:/app/feeds.yml" \
  efcd detect --source-id usgs_quakes
```

Render an HTML report and index:

```
docker run --rm \
  -v "$(pwd)/data:/app/data" \
  efcd render --source-id usgs_quakes

docker run --rm \
  -v "$(pwd)/data:/app/data" \
  efcd index
```

## CI (Docker publish)

The GitHub Actions workflow lives at `.github/workflows/efcd-docker.yml` and publishes to GHCR as `ghcr.io/<owner>/efcd` on pushes to `main` and tags starting with `v`.

## CLI

- `profile`: fetch data, compute a profile, store JSON
- `detect`: compare latest two profiles, emit a change report
- `render`: generate a static HTML report for the latest run
- `run`: profile + detect + alert
- `baseline`: manage pinned baselines
- `index`: generate an index page for latest reports

## Config (feeds.yml)

You can define baseline policy, thresholds, and field-level contracts in `feeds.yml`.
If you prefer YAML, install PyYAML:

```
pip install pyyaml
```

Minimal example:

```
defaults:
  baseline_mode: rolling-agg
  baseline_window: 7
  seasonality: none
  alert:
    min_severity: medium
    min_confidence: 0.6
    persist_runs: 1
  thresholds:
    null_rate_delta: 0.1
    distinct_ratio: 2.0
    mean_std_multiplier: 3.0
    row_count_delta: 0.2
sources:
  jhu_daily:
    baseline_mode: seasonal-agg
    seasonality: weekday
    fields:
      Country_Region:
        importance: high
        alert:
          min_severity: high
          min_confidence: 0.75
          persist_runs: 2
      Confirmed:
        type: number
        importance: high
        alert:
          min_severity: medium
          min_confidence: 0.6
          persist_runs: 2
```

Notes:
- Per-field `alert` overrides global alert thresholds for that field only.
- If seasonality is set, alert persistence is counted within the same seasonality bucket.
```

Profiles and reports are stored under `data/` by default.

## Notes

- This is a minimal, dependency-free scaffold intended for fast MVP iteration.
- It supports JSON (HTTP), local JSONL, and local CSV sources.
