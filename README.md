# SW Metrics Collection

Container-based scaffold for software metric experiments, focused on Java projects.

## Metric Matrix

| Category | Metric | Tool / Variant |
|---|---|---|
| Size | LOC | `loc-cloc`, `loc-tokei`, `loc-scc` |
| Complexity | CC | `cc-lizard`, `cc-ckjm` (raw `wmc/nom`, normalized downstream) |
| Coupling | Ce/Ca | `ce-ca-jdepend`, `ce-ca-ck-cbo` (CK proxy) |
| Instability | I | `i-jdepend`, `i-ck-derived` |
| Cohesion | LCOM | `lcom-ck`, `lcom-ckjm` |
| Duplication | Duplication rate | `duplication-jscpd` |
| Maintainability | Maintainability Index (+ Halstead aggregates) | `mi-halstead-java` |
| Quality | Static warnings | `static-warnings-checkstyle` |
| Testing | Coverage ratio | `coverage-jacoco` |
| Evolution | Code churn | `churn-git` |

Implemented metric containers: **16**.

## Repository Structure

- `metrics/size/generic/`
- `metrics/complexity/generic/`, `metrics/complexity/java/`, `metrics/complexity/python/`
- `metrics/coupling/java/`
- `metrics/instability/java/`
- `metrics/cohesion/java/`
- `metrics/duplication/java/`
- `metrics/maintainability/java/`
- `metrics/quality/java/`
- `metrics/testing/java/`
- `metrics/evolution/generic/`
- `metrics/validate-results/generic/jsonl-schema-validator/`
- `metrics/generic/normalized-collector/`
- `src/` mounted as `/app` (read-only)
- `results/` mounted as `/results`

## Prerequisites

- Docker running (`docker version`)
- Python 3.11+
- `pytest`

```bash
python3 -m pip install pytest
```

## Quick Start (Java)

1. Put one or more Java repos under `src/`.
2. Run core Java metrics:

```bash
make collect-cc-lizard
make collect-cc-ckjm
make collect-ce-ca-jdepend
make collect-ce-ca-ck-cbo
make collect-i-jdepend
make collect-i-ck-derived
make collect-lcom-ck
make collect-lcom-ckjm
```

3. Run paper extras:

```bash
make collect-duplication-jscpd
make collect-mi-halstead-java
make collect-static-warnings-checkstyle
make collect-coverage-jacoco
make collect-churn-git
```

4. Validate outputs:

```bash
make validate-results
```

## One-Command Experiment Pipeline

Run full collection + manifest + normalization + dataset build + agreement:

```bash
make experiment
```

Equivalent step-by-step:

```bash
make collect-all
make manifest
make normalize
make dataset
make agreement
```

Output folders:

- `results/` raw JSONL from metric containers
  - `results/manifest-<run_id>.json`
- `results_normalized/` JSONL after semantic normalization (`analysis/normalize.py`)
- `analysis_out/` tabular datasets and agreement outputs
  - `analysis_out/repo_report.csv`
  - `analysis_out/repo_report.json`
  - `analysis_out/dataset_wide_<component_type>.csv`

Agreement scope (`analysis/agreement.py`):

- inter-tool
- intra-metrica (same metric only)
- no cross-metric correlation (e.g. not `LOC` vs `CC`)
- default `min_common=2` (`--min-common` to override)
- when `n_common<2`, `spearman_rho` is null-equivalent (blank in CSV export) and `notes=n_common<2`

## Single Repository Workflow

Use this when you want to analyze exactly one repository end-to-end.

1. Keep only one repository under `src/`:

```bash
rm -rf src results results_normalized analysis_out
mkdir -p src results results_normalized analysis_out
```

2. Clone or copy the target repository as a single top-level folder in `src/`:

```bash
git clone --depth 1 https://github.com/TheAlgorithms/Java src/thealgorithms-java
```

3. Run the full pipeline:

```bash
make experiment
```

4. (Optional) Validate raw JSONL schema:

```bash
make validate-results
```

5. Inspect outputs:

```bash
ls -1 results | head
ls -1 results_normalized | head
ls -1 analysis_out
```

Expected analysis artifacts:

- `analysis_out/dataset_long.csv`
- `analysis_out/dataset_wide.csv`
- `analysis_out/agreement.csv`

Notes:

- Inter-tool agreement is computed **within the same metric** only.
- If `src/` contains multiple repos, all of them are processed.
- Java experiment profile excludes non-Java metrics from `collect-all` (for example `cc-radon`).

## Java Example (TheAlgorithms/Java)

```bash
rm -rf src/thealgorithms-java
git clone --depth 1 https://github.com/TheAlgorithms/Java src/thealgorithms-java

make collect-all
make validate-results
```

Expected files in `results/` include:

- `thealgorithms-java-<timestamp>-loc-cloc-cloc-default.jsonl`
- `thealgorithms-java-<timestamp>-cc-lizard-lizard-default.jsonl`
- `thealgorithms-java-<timestamp>-wmc-ckjm-ckjm-raw.jsonl`
- `thealgorithms-java-<timestamp>-ce-ca-jdepend-jdepend-default.jsonl`
- `thealgorithms-java-<timestamp>-ce-ca-ck-ck-ce-ca-proxy.jsonl`
- `thealgorithms-java-<timestamp>-instability-jdepend-jdepend-default.jsonl`
- `thealgorithms-java-<timestamp>-lcom-ck-ck-default.jsonl`
- `thealgorithms-java-<timestamp>-lcom-ckjm-ckjm-default.jsonl`
- `thealgorithms-java-<timestamp>-duplication-rate-jscpd-jscpd-default.jsonl`
- `thealgorithms-java-<timestamp>-maintainability-index-java-halstead-analyzer-mi-halstead-default.jsonl`
- `thealgorithms-java-<timestamp>-static-warnings-checkstyle-checkstyle-default.jsonl`
- `thealgorithms-java-<timestamp>-test-coverage-jacoco-jacoco-default.jsonl`
- `thealgorithms-java-<timestamp>-code-churn-git-git-default.jsonl`

Timestamp format: UTC ISO8601 with seconds, example `2026-02-24T15:04:05Z`.

## Unified JSONL Output Format

Every metric container writes JSON Lines:

Path pattern:

- `/results/<project>-<timestamp>-<metric>-<tool>-<variant>.jsonl`

Row schema:

```json
{
  "schema_version": "1.0",
  "run_id": "uuid4-string",
  "project": "string",
  "metric": "string",
  "variant": "string",
  "component_type": "module|file|method|class|package|project|clone_block",
  "component": "string",
  "status": "ok|skipped",
  "skip_reason": "string-optional-when-skipped",
  "value": 0.0,
  "tool": "string",
  "tool_version": "string",
  "parameters": {},
  "timestamp_utc": "2026-02-24T15:04:05Z"
}
```

Field meaning:

- `project`: top-level repo folder under `/app`
- `component`: entity identifier at the selected granularity
- `status=ok`: metric measured and `value` is numeric
- `status=skipped`: metric not applicable/available and `value=null`
- `parameters`: collector configuration and metadata

## Metric Value Semantics

- `loc`: file-level code lines
- `cc`: method-level direct value from tool where applicable (for CKJM, comparable CC is still derived in `results_normalized/`)
- `wmc`/`nom`: raw CKJM complexity components used to derive `cc` proxy downstream
- `ce-ca`: two rows per module (`parameters.dimension=ce` and `ca`)
- `instability`: module-level instability ratio
- `lcom`: module mean LCOM
- `duplication-rate`: ratio `[0,1]`
- `maintainability-index`: score `[0,100]` (Halstead aggregates in `parameters`)
- `static-warnings`: file-level warning count
- `test-coverage`: file-level instruction coverage ratio `[0,1]` when available, otherwise skipped
- `code-churn`: file-level historical `added+deleted` count

## Normalized Collector (CSV + Manifest)

`metrics/generic/normalized-collector` writes:

- `/results/<project>/<run_id>/<metric_key>/<tool_key>/manifest.json`
- `/results/<project>/<run_id>/<metric_key>/<tool_key>/data.csv`

Run:

```bash
make collect-normalized-loc-cloc
```

## Testing

Unit tests:

```bash
make test-unit
```

Docker integration matrix (build + run all containers + schema, oracle and invariant assertions on fixtures):

```bash
make test-docker-matrix
```

The integration suite validates:

- schema compliance
- expected metric/variant outputs
- expected project/module coverage per fixture
- deterministic numeric checks for stable fixtures (LOC, CC, Ce/Ca)
- cross-tool consistency checks (LOC tool agreement; instability derived from Ce/Ca)
- numeric invariants (ratios in `[0,1]`, MI in `[0,100]`, finite non-negative counts)
- at least one positive value (`value > 0`) per targeted fixture for each metric container
- validator container execution


## Run experiment
To run the full experiment pipeline (collection + manifest + normalization + dataset build + agreement):

1. Download repositories using the `init_repositories.sh` script:   

```bash
bash init_repositories.sh
```
2. Run the experiment:

```bash 
run_experiment.sh
```
