# i-ck-derived

Module-level instability derived from ck outputs.

## Build

```bash
docker build -t i-ck-derived:latest metrics/instability/java/i-ck-derived
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  i-ck-derived:latest
```

## Dry run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  i-ck-derived:latest --dry-run
```

## Output file pattern

`/results/<project>-<timestamp>-instability-ck-derived.jsonl`

Timestamp format is UTC ISO8601 with seconds (for example `2026-02-24T15:04:05Z`).

## Output row format (JSONL)

Each line in the output file is one JSON object:

```json
{
  "project": "string",
  "metric": "instability",
  "variant": "ck-derived",
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

- Instability is computed as I = Ce / (Ca + Ce) from CK-derived class coupling values.
