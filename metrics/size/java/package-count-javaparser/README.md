# package-count-javaparser

Project-level Java package count using JavaParser.

## Build

```bash
docker build -t package-count-javaparser:latest metrics/size/java/package-count-javaparser
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  package-count-javaparser:latest
```

## Output file pattern

`/results/software-metrics/jsonl/<project>-<timestamp>-package-count-javaparser-javaparser-default.jsonl`

## Semantics

- counts unique named Java packages at repository level
- excludes test sources
- files in the unnamed/default package are tracked in `parameters.unnamed_package_files`
