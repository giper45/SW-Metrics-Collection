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

## Output file pattern

`/results/software-metrics/jsonl/<project>-<timestamp>-test-coverage-jacoco-default.jsonl`

## Notes

- `value` is instruction coverage ratio in `[0,1]`.
- Modules without a `pom.xml` return `0.0`.
- Policy skipped uniforme: se un modulo non ha file sorgente o l'esecuzione Maven fallisce, viene emessa una riga `status=skipped`, `value=null`, `skip_reason` valorizzato.
