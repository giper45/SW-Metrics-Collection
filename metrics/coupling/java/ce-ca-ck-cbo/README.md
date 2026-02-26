# ce-ca-ck-cbo

Module-level coupling proxy using ck (CBO aggregate).

## Build

```bash
docker build -t ce-ca-ck-cbo:latest metrics/coupling/java/ce-ca-ck-cbo
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  ce-ca-ck-cbo:latest
```

## Dry run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  ce-ca-ck-cbo:latest --dry-run
```

## Output file pattern

`/results/<project>-<timestamp>-ce-ca-ck-cbo-agg.jsonl`

Timestamp format is UTC ISO8601 with seconds (for example `2026-02-24T15:04:05Z`).

## Output row format (JSONL)

Each line in the output file is one JSON object:

```json
{
  "project": "string",
  "metric": "ce-ca",
  "variant": "ck-cbo-agg",
  "component_type": "module",
  "component": "string",
  "value": 0.0,
  "tool": "ck",
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

- Uses mean class CBO as a Ce/Ca proxy.
- Emits one row per module with parameters.dimension=cbo_mean_proxy.
