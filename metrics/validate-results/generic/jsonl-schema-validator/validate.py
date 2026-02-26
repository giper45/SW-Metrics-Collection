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

    for key in ("schema_version", "run_id", "project", "metric", "variant", "component", "tool", "tool_version"):
        if key in row and not isinstance(row[key], str):
            errors.append(f"{key} must be string")
    if "submetric" in row and not isinstance(row["submetric"], str):
        errors.append("submetric must be string")
    if "skip_reason" in row and not isinstance(row["skip_reason"], str):
        errors.append("skip_reason must be string")

    status = row.get("status")
    if "status" in row:
        if not isinstance(status, str):
            errors.append("status must be string")
        elif status not in ALLOWED_STATUSES:
            errors.append(f"status must be one of {sorted(ALLOWED_STATUSES)}")

    if "component_type" in row:
        if not isinstance(row["component_type"], str):
            errors.append("component_type must be string")
        elif row["component_type"] not in ALLOWED_COMPONENT_TYPES:
            errors.append(f"component_type must be one of {sorted(ALLOWED_COMPONENT_TYPES)}")

    if "value" in row:
        if status == "skipped":
            if row["value"] is not None:
                errors.append("value must be null when status=skipped")
        elif not is_number(row["value"]):
            errors.append("value must be number")

    if "parameters" in row and not isinstance(row["parameters"], dict):
        errors.append("parameters must be object")

    if "timestamp_utc" in row:
        ts_value = row["timestamp_utc"]
        if not isinstance(ts_value, str):
            errors.append("timestamp_utc must be string")
        elif not TIMESTAMP_PATTERN.match(ts_value):
            errors.append("timestamp_utc must match YYYY-MM-DDTHH:MM:SSZ")

    return errors


def collect_jsonl_files(root_dir):
    files = []
    for walk_root, _, names in os.walk(root_dir):
        for name in sorted(names):
            if name.endswith(".jsonl"):
                files.append(os.path.join(walk_root, name))
    return sorted(files)


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
                line = raw_line.strip()
                if not line:
                    continue

                total_rows += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    invalid_rows += 1
                    print(f"INVALID {path}:{line_no}: invalid json: {exc}")
                    continue

                row_errors = validate_row(row)
                if row_errors:
                    invalid_rows += 1
                    print(f"INVALID {path}:{line_no}: {'; '.join(row_errors)}")

    print(f"Summary: files={len(files)} rows={total_rows} invalid_rows={invalid_rows}")
    return 1 if invalid_rows > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
