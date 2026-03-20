from pathlib import Path

from webapp.services.makefile import discover_make_targets, group_targets, parse_env_overrides


def test_discover_make_targets_skips_assignments(tmp_path: Path):
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        "\n".join(
            [
                "SRC_DIR := $(PWD)/src",
                "",
                ".PHONY: clean collect-all",
                "collect-all: collect-a collect-b",
                "\t@echo collect-all",
                "clean:",
                "\trm -rf src",
                "archive:",
                "\t@echo archive",
            ]
        ),
        encoding="utf-8",
    )

    targets = discover_make_targets(makefile_path)

    assert [target.name for target in targets] == ["collect-all", "clean", "archive"]


def test_discover_make_targets_reads_recipe_comments_as_description(tmp_path: Path):
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        "\n".join(
            [
                "prepare-java-bytecode:",
                "\t@# Compile Java repositories into bytecode before bytecode-based metrics run.",
                "\tpython3 -m analysis.prepare_java_bytecode",
                "",
                "validate-results: prepare-java-bytecode",
                "\t# Build the JSONL schema validator image.",
                "\tdocker build -t validator .",
                "\t@# Validate the collected result files against the schema.",
                "\tdocker run --rm validator",
            ]
        ),
        encoding="utf-8",
    )

    targets = discover_make_targets(makefile_path)

    assert [(target.name, target.description) for target in targets] == [
        (
            "prepare-java-bytecode",
            "Compile Java repositories into bytecode before bytecode-based metrics run.",
        ),
        (
            "validate-results",
            "Build the JSONL schema validator image. Validate the collected result files against the schema.",
        ),
    ]
    assert targets[1].dependencies == ("prepare-java-bytecode",)


def test_discover_make_targets_splits_software_metrics_and_vulnerabilities(tmp_path: Path):
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        "\n".join(
            [
                "collect-loc-cloc:",
                "\t@echo loc",
                "",
                "collect-vulnerability-pmd-security:",
                "\t@echo vuln",
                "",
                "collect-all:",
                "\t@echo all",
            ]
        ),
        encoding="utf-8",
    )

    targets = {target.name: target.category for target in discover_make_targets(makefile_path)}

    assert targets["collect-loc-cloc"] == "Software Metrics"
    assert targets["collect-vulnerability-pmd-security"] == "Vulnerabilities"
    assert targets["collect-all"] == "Pipelines"


def test_group_targets_places_preparation_first(tmp_path: Path):
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        "\n".join(
            [
                "collect-loc-cloc:",
                "\t@echo loc",
                "",
                "prepare-java-bytecode:",
                "\t@echo prep",
                "",
                "clean:",
                "\t@echo clean",
            ]
        ),
        encoding="utf-8",
    )

    grouped = group_targets(discover_make_targets(makefile_path))

    assert [category for category, _ in grouped] == ["Preparation", "Software Metrics", "Maintenance"]


def test_parse_env_overrides_accepts_comments():
    overrides = parse_env_overrides(
        """
        # comment
        JAVA_BUILD_BYTECODE=1
        METRIC_RESOURCE_TRACKING=1
        """
    )

    assert overrides == {
        "JAVA_BUILD_BYTECODE": "1",
        "METRIC_RESOURCE_TRACKING": "1",
    }
