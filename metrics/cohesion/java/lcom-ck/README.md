# lcom-ck

Module-level cohesion using ck (mean class LCOM).

## Build

```bash
docker build -t lcom-ck:latest metrics/cohesion/java/lcom-ck
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  lcom-ck:latest
```

## Dry run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  lcom-ck:latest
```

## Output file pattern

`/results/<project>-<timestamp>-lcom-ck-default.jsonl`

Timestamp format is UTC ISO8601 with seconds (for example `2026-02-24T15:04:05Z`).

## Output row format (JSONL)

Each line in the output file is one JSON object:

```json
{
  "project": "string",
  "metric": "lcom",
  "variant": "ck-default",
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

- value is mean class LCOM at module level.
