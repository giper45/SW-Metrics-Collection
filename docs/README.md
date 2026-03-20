# Docs & Diagrams

This folder contains proposed architectural documentation for **MAVIS (Metric And Vulnerability Integrated Suite)**, with **PlantUML** diagrams.

## Suggested structure

- `docs/diagrams/`
- `01_system_context.puml` – context + macro-components
- `02_pipeline_sequence.puml` – `make experiment` pipeline sequence
- `docs/modules/`
- `analysis_overview.puml` – map of the `analysis/` package
- `metrics_overview.puml` – map of containers in `metrics/`
- `analysis/*.puml` – diagrams of main Python modules
- `metrics/**/module.puml` – one diagram for each container (directory with `Dockerfile`)

## How to render PlantUML

Typical options:

1. **PlantUML CLI** (jar) + Java:
- `java -jar plantuml.jar docs/diagrams/*.puml`
2. **VS Code**: PlantUML extension (preview/export).
3. **GitHub**: with plugin/build action that exports PNG/SVG.

Practical tip:
- Export to **SVG** to maintain sharpness.
- Version the generated `.puml` and (optionally) `.svg` files.

## Conventions used in diagrams

- **Docker containers** are treated as *components* that read `/app` and write to `/results`.
- Python modules in `analysis/` are components that read/write between `results/`, `results_normalised/`, `analysis_out/`.
- The diagrams for containers are deliberately “templates” (they do not go into detail about the tool's commands), but they are complete in terms of I/O and responsibilities.
*
