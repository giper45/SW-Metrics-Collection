# normalized-collector

Generic container collector that emits normalized long-format output for inter-agreement analysis.

## Build

```bash
docker build -t normalized-collector:latest metrics/generic/normalized-collector
```

## Run (LOC with cloc)

```bash
docker run --rm \
  -e METRIC_KEY=loc \
  -e TOOL_KEY=cloc \
  -e COMMAND='cloc --json --quiet --skip-uniqueness {project_path}' \
  -e TOOL_VERSION_COMMAND='cloc --version' \
  -e ENTITY_TYPE=project \
  -e VARIANT_KEY=default \
  -e SCOPE_FILTER=no_tests \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  normalized-collector:latest
```

## Output layout

For each discovered project:

- `/results/<project>/<run_id>/<metric_key>/<tool_key>/manifest.json`
- `/results/<project>/<run_id>/<metric_key>/<tool_key>/data.csv`

`run_id` format: `YYYYMMDDTHHMMSSZ`.

## manifest.json

Includes at least:

- `schema_version`, `project`, `run_id`, `metric_key`, `tool_key`, `tool_version`
- `container_image`, `source_path`, `generated_at_utc`, `command`
- `status` (`success` or `error`) and optional `error_message`

## data.csv

Fixed header:

```csv
entity_type,entity_id,metric_name,metric_value,unit,language,tool_key,variant_key,scope_filter,path_hint
```

Column semantics:

- `entity_type`: project/module/class/function granularity
- `entity_id`: canonical identifier
- `metric_name`: canonical metric name
- `metric_value`: float value
- `unit`: `count` or `ratio`
- `language`: `java` / `python` / `mixed` / `unknown`
- `tool_key`: normalized tool id
- `variant_key`: variant id (usually `default`)
- `scope_filter`: usually `no_tests`
- `path_hint`: optional source path hint
