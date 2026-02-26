# static-warnings-checkstyle

Module-level Java static warning count using checkstyle.

## Build

```bash
docker build -t static-warnings-checkstyle:latest metrics/quality/java/static-warnings-checkstyle
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  static-warnings-checkstyle:latest
```

## Dry run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  static-warnings-checkstyle:latest --dry-run
```

## Output file pattern

`/results/<project>-<timestamp>-static-warnings-checkstyle-default.jsonl`

## Notes

- `value` is total warning count per module.
- Configuration enforces `NeedBraces` and `LineLength(max=100)`.
- Test and vendor directories are excluded.
