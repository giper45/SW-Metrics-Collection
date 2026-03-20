# class-count-javaparser

Project-level Java class count using JavaParser.

## Build

```bash
docker build -t class-count-javaparser:latest metrics/size/java/class-count-javaparser
```

## Run

```bash
docker run --rm \
  -v "$(pwd)/src:/app:ro" \
  -v "$(pwd)/results:/results" \
  class-count-javaparser:latest
```

## Output file pattern

`/results/software-metrics/jsonl/<project>-<timestamp>-class-count-javaparser-javaparser-default.jsonl`

## Semantics

- counts non-test Java class declarations at repository level
- counts nested classes as well
- excludes interfaces and enums from the metric value
- records are reported separately in `parameters.records_found`
