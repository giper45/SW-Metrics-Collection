# churn-git

Module-level code churn from git history.

## Build

```bash
docker build -t churn-git:latest metrics/evolution/generic/churn-git
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  churn-git:latest
```

## Dry run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  churn-git:latest --dry-run
```

## Output file pattern

`/results/<project>-<timestamp>-code-churn-git-default.jsonl`

## Notes

- `value` is historical churn: `sum(added + deleted)`.
- Test paths are excluded from churn aggregation.
