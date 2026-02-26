# jsonl-schema-validator

Validates metric JSONL files under `/results`.

## Build

```bash
docker build -t validate-results-jsonl-schema-validator:latest metrics/generic/validate-results/jsonl-schema-validator
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/results:/results" \
  validate-results-jsonl-schema-validator:latest
```

## Validated JSONL schema

Each JSON line must include:

```json
{
  "project": "string",
  "metric": "string",
  "variant": "string",
  "component_type": "module",
  "component": "string",
  "value": 0.0,
  "tool": "string",
  "tool_version": "string",
  "parameters": {},
  "timestamp_utc": "YYYY-MM-DDTHH:MM:SSZ"
}
```

## Behavior

- Recursively scans `/results` for `.jsonl` files
- Validates required keys and basic types
- Enforces `component_type == "module"`
- Exits with non-zero status if any row is invalid
