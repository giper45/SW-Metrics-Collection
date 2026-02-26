# coverage-jacoco

Module-level Java instruction coverage ratio using Maven + JaCoCo.

## Build

```bash
docker build -t coverage-jacoco:latest metrics/testing/java/coverage-jacoco
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  coverage-jacoco:latest
```

## Dry run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  coverage-jacoco:latest --dry-run
```

## Output file pattern

`/results/<project>-<timestamp>-test-coverage-jacoco-default.jsonl`

## Notes

- `value` is instruction coverage ratio in `[0,1]`.
- Modules without a `pom.xml` return `0.0`.
