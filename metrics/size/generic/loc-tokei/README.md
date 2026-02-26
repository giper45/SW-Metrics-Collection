# loc-tokei

Module-level LOC using tokei (code lines only).

## Build

```bash
docker build -t loc-tokei:latest metrics/size/generic/loc-tokei
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  loc-tokei:latest
```

## Dry run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  loc-tokei:latest --dry-run
```

## Output file pattern

`/results/<project>-<timestamp>-loc-tokei-default.jsonl`

Timestamp format is UTC ISO8601 with seconds (for example `2026-02-24T15:04:05Z`).

## Output row format (JSONL)

Each line in the output file is one JSON object:

```json
{
  "project": "string",
  "metric": "loc",
  "variant": "tokei-default",
  "component_type": "module",
  "component": "string",
  "value": 0.0,
  "tool": "tokei",
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

- Ignores hidden, vendor, and test directories according to collector filters.
