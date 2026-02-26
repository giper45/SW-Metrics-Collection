# scc-default

Module-level lines-of-code using scc (code lines only).

## Build

```bash
docker build -t loc-scc-default:latest metrics/generic/lines-of-code/scc-default
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  loc-scc-default:latest
```

## Dry run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  loc-scc-default:latest --dry-run
```

## Output file pattern

`/results/<project>-<timestamp>-lines-of-code-scc-default.jsonl`

Timestamp format is UTC ISO8601 with seconds (for example `2026-02-24T15:04:05Z`).

## Output row format (JSONL)

Each line in the output file is one JSON object:

```json
{
  "project": "string",
  "metric": "lines-of-code",
  "variant": "scc-default",
  "component_type": "module",
  "component": "string",
  "value": 0.0,
  "tool": "scc",
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

- Generic multi-language LOC collector variant.
