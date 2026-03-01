# cc-lizard

Module-level mean cyclomatic complexity using lizard.

## Build

```bash
docker build -t cc-lizard:latest metrics/complexity/generic/cc-lizard
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  cc-lizard:latest
```

## Dry run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  cc-lizard:latest
```

## Output file pattern

`/results/<project>-<timestamp>-cc-lizard-default.jsonl`

Timestamp format is UTC ISO8601 with seconds (for example `2026-02-24T15:04:05Z`).

## Output row format (JSONL)

Each line in the output file is one JSON object:

```json
{
  "project": "string",
  "metric": "cc",
  "variant": "lizard-default",
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

- Excludes test folders by default.
- value is the mean CC over considered functions in each module.
