
# Change Log
All notable changes to this project will be documented in this file.
 
The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).
 
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
 