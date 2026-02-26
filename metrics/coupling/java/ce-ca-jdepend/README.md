# ce-ca-jdepend

Module-level coupling using jdepend.

## Build

```bash
docker build -t ce-ca-jdepend:latest metrics/coupling/java/ce-ca-jdepend
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  ce-ca-jdepend:latest
```

## Dry run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  ce-ca-jdepend:latest --dry-run
```

## Output file pattern

`/results/<project>-<timestamp>-ce-ca-jdepend-default.jsonl`

Timestamp format is UTC ISO8601 with seconds (for example `2026-02-24T15:04:05Z`).

## Output row format (JSONL)

Each line in the output file is one JSON object:

```json
{
  "project": "string",
  "metric": "ce-ca",
  "variant": "jdepend-default",
  "component_type": "module",
  "component": "string",
  "value": 0.0,
  "tool": "jdepend",
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

- Emits two rows per module: one with parameters.dimension=ce and one with parameters.dimension=ca.
- value is aggregated package coupling for that dimension.
