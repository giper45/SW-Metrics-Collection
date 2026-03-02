
# Change Log
All notable changes to this project will be documented in this file.
 
The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).
 
## [0.6] - 2026-03-02

### Changed
- Refactor some code in the agreement module. 
- Fix compilation guava bugs in the preprocess-bytecode. 


## [0.5] - 2026-03-02

### Changed
- Frozen the commits in the repository list.

## [0.4] - 2026-03-01

### Changed
- Refactor analysis for lcom and make inputs coherent across collectors and analysis.



## [0.3] - 2026-03-01

### Added
- `make print-experiment` now prints Docker image tag, metric path, and metric type for the experiment set.
- Regression tests for bytecode discovery filtering (`tests/unit/test_input_manager.py`).

### Changed
- `JAVA_BUILD_BYTECODE` is enabled by default in `Makefile`.
- `make experiment` no longer includes `code-churn` in `collect-paper-extras` and in manifest expected metrics.
- Java bytecode preparation now includes sparse-checkout artifact fallback for `junit5:junit-jupiter-engine` and `spring-framework:spring-core`.
- Complete refactoring of logic for bytecode, input discovery, numpy, input handling, and output data structures using data managers and data classes for improved maintainability and clarity.

### Fixed
- CKJM bytecode input discovery now excludes non-`.class` files (e.g. `META-INF/LICENSE`) to prevent collector crashes.
- Bytecode preparation fallback reporting now correctly marks modules with existing class files as successful.

## [0.2] - 2026-03-01
The first release of the project.
 
 
### Added
- Container-based metric collection scaffold for software metrics experiments, focused on Java repositories.
- 14 metric containers across size, complexity, coupling, cohesion, duplication, maintainability, quality, testing, and evolution categories.
- End-to-end experiment workflow via `make experiment` (collection, manifest generation, normalization, dataset build, agreement, and report generation).
- Semantic normalization and dataset exports (`dataset_long.csv`, `dataset_wide.csv`, and component-specific wide datasets).
- Agreement and repository reporting outputs (`agreement.csv`, `agreement_final_*`, `repo_report.csv`, `repo_report.json`).
- Optional runtime resource telemetry for metric container runs and optional Java bytecode preparation pipeline.
 
### Changed
- Standardized project structure for reproducible experiments (`metrics/`, `analysis/`, `results/`, `results_normalized/`, `analysis_out/`).
 
### Fixed
- Excluded runtime telemetry files (`metric-runtime-*.jsonl`) from normalization/dataset/manifest inputs.
 
