# duplication-jscpd

Module-level duplication rate for Java code using jscpd.

## Build

```bash
docker build -t duplication-jscpd:latest metrics/duplication/java/duplication-jscpd
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  duplication-jscpd:latest
```

## Output file pattern

`/results/software-metrics/jsonl/<project>-<timestamp>-duplication-rate-jscpd-default.jsonl`

## Notes

- `value` is duplication ratio in `[0,1]` for each module.
- Test and vendor directories are excluded (`scope_filter=no_tests`).
- Policy skipped uniforme: se un modulo non contiene file Java validi o `jscpd` fallisce, viene emessa una riga `status=skipped`, `value=null`, `skip_reason` valorizzato.
