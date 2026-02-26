#!/usr/bin/env python3
import json
import os
import re
import sys

RESULTS_DIR = "/results"
REQUIRED_KEYS = {
    "schema_version",
    "run_id",
    "project",
    "metric",
    "variant",
    "component_type",
    "component",
    "value",
    "tool",
    "tool_version",
    "parameters",
    "timestamp_utc",
    "status",
}
OPTIONAL_KEYS = {"submetric", "skip_reason"}
ALLOWED_COMPONENT_TYPES = {"module", "file", "method", "class", "package", "project", "clone_block"}
ALLOWED_STATUSES = {"ok", "skipped"}
TIMESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_row(row):
    errors = []

    if not isinstance(row, dict):
        return ["row is not a JSON object"]

    keys = set(row.keys())
    missing = sorted(REQUIRED_KEYS - keys)
    extra = sorted(keys - REQUIRED_KEYS - OPTIONAL_KEYS)
    if missing:
        errors.append(f"missing keys: {missing}")
    if extra:
        errors.append(f"unexpected keys: {extra}")

    if "schema_version" in row and not isinstance(row["schema_version"], str):
        errors.append("schema_version must be string")
    if "run_id" in row and not isinstance(row["run_id"], str):
        errors.append("run_id must be string")
    if "project" in row and not isinstance(row["project"], str):
        errors.append("project must be string")
    if "metric" in row and not isinstance(row["metric"], str):
        errors.append("metric must be string")
    if "variant" in row and not isinstance(row["variant"], str):
        errors.append("variant must be string")
    if "component" in row and not isinstance(row["component"], str):
        errors.append("component must be string")
    if "tool" in row and not isinstance(row["tool"], str):
        errors.append("tool must be string")
    if "tool_version" in row and not isinstance(row["tool_version"], str):
        errors.append("tool_version must be string")
    if "submetric" in row and not isinstance(row["submetric"], str):
        errors.append("submetric must be string")
    if "skip_reason" in row and not isinstance(row["skip_reason"], str):
        errors.append("skip_reason must be string")
    if "parameters" in row and not isinstance(row["parameters"], dict):
        errors.append("parameters must be object")

    status = row.get("status")
    if "status" in row:
        if not isinstance(status, str):
            errors.append("status must be string")
        elif status not in ALLOWED_STATUSES:
            errors.append(f"status must be one of {sorted(ALLOWED_STATUSES)}")

    if "component_type" in row:
        component_type = row["component_type"]
        if not isinstance(component_type, str):
            errors.append("component_type must be string")
        elif component_type not in ALLOWED_COMPONENT_TYPES:
            errors.append(f"component_type must be one of {sorted(ALLOWED_COMPONENT_TYPES)}")

    if "value" in row and not is_number(row["value"]):
        if status == "skipped":
            if row["value"] is not None:
                errors.append("value must be null when status=skipped")
        else:
            errors.append("value must be number")

    if "timestamp_utc" in row:
        value = row["timestamp_utc"]
        if not isinstance(value, str):
            errors.append("timestamp_utc must be string")
        elif not TIMESTAMP_PATTERN.match(value):
            errors.append("timestamp_utc must match YYYY-MM-DDTHH:MM:SSZ")

    return errors


def collect_jsonl_files(root_dir):
    matches = []
    for walk_root, _, files in os.walk(root_dir):
        for filename in sorted(files):
            if filename.endswith(".jsonl"):
                matches.append(os.path.join(walk_root, filename))
    return sorted(matches)


def main():
    files = collect_jsonl_files(RESULTS_DIR)
    if not files:
        print("No .jsonl files found in /results")
        print("Summary: files=0 rows=0 invalid_rows=0")
        return 0

    total_rows = 0
    invalid_rows = 0

    for path in files:
        with open(path, "r", encoding="utf-8") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue

                total_rows += 1
                try:
                    row = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    invalid_rows += 1
                    print(f"INVALID {path}:{line_no}: invalid json: {exc}")
                    continue

                errors = validate_row(row)
                if errors:
                    invalid_rows += 1
                    print(f"INVALID {path}:{line_no}: {'; '.join(errors)}")

    print(f"Summary: files={len(files)} rows={total_rows} invalid_rows={invalid_rows}")
    return 1 if invalid_rows > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
