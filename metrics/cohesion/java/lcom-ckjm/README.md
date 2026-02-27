# lcom-ckjm

Module-level cohesion using [dspinellis/ckjm](https://github.com/dspinellis/ckjm) (mean class LCOM).

## Build

```bash
docker build -t lcom-ckjm:latest metrics/cohesion/java/lcom-ckjm
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  lcom-ckjm:latest
```

## Dry run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  lcom-ckjm:latest --dry-run
```

## Output file pattern

`/results/<project>-<timestamp>-lcom-ckjm-ckjm-default.jsonl`

Timestamp format is UTC ISO8601 with seconds (for example `2026-02-24T15:04:05Z`).

## Output row format (JSONL)

Each line in the output file is one JSON object:

```json
{
  "project": "string",
  "metric": "lcom",
  "variant": "ckjm-default",
  "component_type": "module",
  "component": "string",
  "value": 0.0,
  "tool": "ckjm",
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
- this collector uses CKJM bytecode analysis (`gr.spinellis.ckjm.MetricsFilter`), not CK source analysis.
- CKJM is built from the official source repository `dspinellis/ckjm` inside the Docker image.
- class files are read from module build folders:
  - `target/classes`
  - `build/classes/java/main`
  - `build/classes/kotlin/main`
  - `build/classes`
  - `out/production`
