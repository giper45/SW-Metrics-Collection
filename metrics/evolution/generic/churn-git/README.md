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
  churn-git:latest
```

## Output file pattern

`/results/software-metrics/jsonl/<project>-<timestamp>-code-churn-git-default.jsonl`

## Notes

- `value` is historical churn: `sum(added + deleted)`.
- Test paths are excluded from churn aggregation.
- If git history cannot be read (for example partial clone lazy-fetch on read-only mount),
  the collector writes a `status=skipped` project row instead of failing the whole run.
