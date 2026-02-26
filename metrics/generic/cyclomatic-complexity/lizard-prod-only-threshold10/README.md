# lizard-prod-only-threshold10

Module-level mean cyclomatic complexity using lizard, production-only, thresholded.

## Build

```bash
docker build -t cc-lizard-prod-only-threshold10:latest metrics/generic/cyclomatic-complexity/lizard-prod-only-threshold10
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  cc-lizard-prod-only-threshold10:latest
```

## Dry run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  cc-lizard-prod-only-threshold10:latest --dry-run
```

## Output file pattern

`/results/<project>-<timestamp>-cyclomatic-complexity-lizard-prod-only-threshold10.jsonl`

Timestamp format is UTC ISO8601 with seconds (for example `2026-02-24T15:04:05Z`).

## Output row format (JSONL)

Each line in the output file is one JSON object:

```json
{
  "project": "string",
  "metric": "cyclomatic-complexity",
  "variant": "lizard-prod-only-threshold10",
  "component_type": "module",
  "component": "string",
  "value": 0.0,
  "tool": "lizard",
  "tool_version": "string",
  "parameters": {},
  "timestamp_utc": "2026-02-24T15:04:05Z"
}
```

## Field semantics

- `project`: top-level project directory under `/app`
- `component`: top-level module directory inside the project (or project fallback)
- `value`: module-level aggregated numeric value
- `parameters`: collector-specific configuration and derived metadata

## Collector notes

- Excludes test folders.
- Only functions with CC >= 10 are included in the module mean.
