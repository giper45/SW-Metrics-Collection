# cc-ckjm

Module-level raw Java complexity components from CKJM/CK (`WMC` and `NOM`).
Normalization to comparable `cc` is performed downstream via `analysis/normalize.py`.

## Build

```bash
docker build -t cc-ckjm:latest metrics/complexity/java/cc-ckjm
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  cc-ckjm:latest
```

## Dry run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  cc-ckjm:latest --dry-run
```

## Output file pattern

`/results/<project>-<timestamp>-wmc-ckjm-raw.jsonl`

Timestamp format is UTC ISO8601 with seconds (for example `2026-02-24T15:04:05Z`).

## Output row format (JSONL)

Each line in the output file is one JSON object:

```json
{
  "project": "string",
  "metric": "wmc|nom",
  "variant": "ckjm-raw",
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
- `metric`: raw complexity component (`wmc` or `nom`)
- `value`: module-level sum across eligible classes
- `parameters`: collector-specific configuration and derived metadata

## Collector notes

- Raw rows are emitted per module for:
- `wmc`: sum of class WMC values.
- `nom`: sum of class NOM values.
- Classes with `NOM <= 0` are excluded from both sums.
- Test packages/classes are excluded.

## Normalization step

To derive comparable CC proxy rows (`metric=cc`, `variant=ckjm-normalized`), run:

```bash
python3 analysis/normalize.py results results_normalized
```
