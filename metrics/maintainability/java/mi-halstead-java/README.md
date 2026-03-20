# mi-halstead-java

Module-level maintainability index for Java using Halstead-based analysis.

## Build

```bash
docker build -t mi-halstead-java:latest metrics/maintainability/java/mi-halstead-java
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  mi-halstead-java:latest
```

## Dry run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  mi-halstead-java:latest
```

## Output file pattern

`/results/software-metrics/jsonl/<project>-<timestamp>-maintainability-index-mi-halstead-default.jsonl`

## Notes

- `value` is maintainability index in `[0,100]` per module.
- Additional Halstead aggregates are stored in `parameters`.
