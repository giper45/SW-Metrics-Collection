# Test Suite

Two layers are provided:

1. `tests/unit` for parsers, validator rules, and layout checks.
2. `tests/integration` for full Docker build/run matrix.

## Fixtures

- `fixtures/java-multi-repo/`: core Java metrics fixture
- `fixtures/java-coupling-repo/`: coupling/instability non-zero fixture
- `fixtures/java-extended-repo/`: duplication, maintainability, warnings, coverage fixture
- `fixtures/python-multi-repo/`: Python CC fixture
- `fixtures/normalized-app/`: normalized collector fixture
- dynamic git fixture: created at runtime by integration test for churn

## Unit Tests

```bash
python3 -m pip install pytest
python3 -m pytest tests/unit -q
```

## Docker Matrix Tests

```bash
python3 tests/integration/run_docker_matrix_tests.py
```

Checks performed:

- image build for all metric containers
- runtime with `/app` and `/results` mounts
- JSONL schema validity
- `schema_version=1.0` + `run_id` presence in each row
- expected metric/variant presence
- expected component coverage per fixture (no missing module rows)
- metric invariants:
  - ratios in `[0,1]` where expected (`duplication-rate`, `test-coverage`, `instability`)
  - maintainability index in `[0,100]`
  - non-negative finite values for count-like metrics
- deterministic numeric checks on controlled fixtures:
  - LOC oracle values for `loc-cloc`
  - CC oracle values for `cc-lizard` and `cc-radon`
  - Ce/Ca oracle values for `ce-ca-jdepend`
- cross-tool consistency checks:
  - LOC agreement (`cloc`/`tokei`/`scc`) within tolerance
  - instability formula consistency via normalization (`ce-ca` -> `*-derived`)
- anti-regression assertions to avoid all-zero outputs (`any(value > 0)` on controlled fixtures)
- validator container execution
