#!/usr/bin/env python3
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
FIXTURES_DIR = os.path.join(SCRIPT_DIR, "fixtures")
PROJECT_NAME = "known-project"

METRIC_SCRIPTS = {
    "loc": os.path.join(REPO_ROOT, "metrics", "generic", "lines-of-code", "collect-loc.py"),
    "comment-ratio": os.path.join(REPO_ROOT, "metrics", "generic", "comment-ratio", "collect-comment-ratio.py"),
    "global-vars": os.path.join(REPO_ROOT, "metrics", "c", "global-vars", "collect-global-vars.py"),
    "cyclomatic": os.path.join(REPO_ROOT, "metrics", "generic", "cyclomatic-complexity", "collect-cyclomatic.py"),
    "faninout": os.path.join(REPO_ROOT, "metrics", "generic", "fan-in-out", "collect-fan-in-out.py"),
}

EXPECTED = {
    "loc": {
        "total_loc": 34,
        "sloc": 27,
        "comment_lines": 3,
        "blank_lines": 4,
    },
    "comment-ratio": {
        "total_lines": 34,
        "comment_lines": 3,
        "code_lines": 27,
        "blank_lines": 4,
        "overall_ratio": 8.82,
    },
    "global-vars": {
        "total_globals": 3,
        "total_statics": 2,
        "total_externs": 2,
        "total_pollution": 5,
    },
    "cyclomatic": {
        "functions": 3,
        "total_cc": 5,
        "avg_cc": 1.67,
        "max_cc": 2,
    },
    "faninout": {
        "functions": 3,
        "total_fan_out": 1,
        "avg_fan_out": 0.33,
        "max_fan_out": 1,
        "total_fan_in": 1,
        "avg_fan_in": 0.33,
        "max_fan_in": 1,
    },
}


def ensure_lizard_available():
    try:
        import lizard  # noqa: F401
    except Exception:
        print("ERROR: lizard is required for cyclomatic/fan-in/out tests.")
        print("Install with: pip install lizard")
        return False
    return True


def run_metric(script_path, src_dir, results_dir):
    subprocess.check_call([sys.executable, script_path, src_dir, results_dir])


def find_result_file(results_dir, key):
    pattern = os.path.join(results_dir, f"{PROJECT_NAME}-{key}-*.txt")
    matches = glob.glob(pattern)
    if not matches:
        raise AssertionError(f"No result file found for key={key} using pattern {pattern}")
    return max(matches, key=os.path.getmtime)


def extract_int(label, text):
    match = re.search(rf"{re.escape(label)}\s*(\d+)", text)
    if not match:
        raise AssertionError(f"Missing integer label: {label}")
    return int(match.group(1))


def extract_float(label, text):
    match = re.search(rf"{re.escape(label)}\s*([0-9]+\.[0-9]+)", text)
    if not match:
        raise AssertionError(f"Missing float label: {label}")
    return float(match.group(1))


def assert_close(actual, expected, tolerance=0.01):
    if abs(actual - expected) > tolerance:
        raise AssertionError(f"Expected {expected} but got {actual}")


def test_loc(results_dir):
    path = find_result_file(results_dir, "loc")
    text = open(path, "r", encoding="utf-8", errors="ignore").read()
    total_loc = extract_int("Total lines (LOC):", text)
    sloc = extract_int("Source lines of code (SLOC):", text)
    comment_lines = extract_int("Comment lines:", text)
    blank_lines = extract_int("Blank lines:", text)

    exp = EXPECTED["loc"]
    assert total_loc == exp["total_loc"], f"Total LOC mismatch: {total_loc}"
    assert sloc == exp["sloc"], f"SLOC mismatch: {sloc}"
    assert comment_lines == exp["comment_lines"], f"Comment lines mismatch: {comment_lines}"
    assert blank_lines == exp["blank_lines"], f"Blank lines mismatch: {blank_lines}"


def test_comment_ratio(results_dir):
    path = find_result_file(results_dir, "comment-ratio")
    text = open(path, "r", encoding="utf-8", errors="ignore").read()
    total_lines = extract_int("Total lines:", text)
    comment_lines = extract_int("Comment lines:", text)
    code_lines = extract_int("Code lines:", text)
    blank_lines = extract_int("Blank lines:", text)
    overall_ratio = extract_float("Overall comment ratio:", text)

    exp = EXPECTED["comment-ratio"]
    assert total_lines == exp["total_lines"], f"Total lines mismatch: {total_lines}"
    assert comment_lines == exp["comment_lines"], f"Comment lines mismatch: {comment_lines}"
    assert code_lines == exp["code_lines"], f"Code lines mismatch: {code_lines}"
    assert blank_lines == exp["blank_lines"], f"Blank lines mismatch: {blank_lines}"
    assert_close(overall_ratio, exp["overall_ratio"], tolerance=0.01)


def test_global_vars(results_dir):
    path = find_result_file(results_dir, "global-vars")
    text = open(path, "r", encoding="utf-8", errors="ignore").read()
    total_globals = extract_int("Total global variables (non-static):", text)
    total_statics = extract_int("Total static variables:", text)
    total_externs = extract_int("Total extern declarations:", text)
    total_pollution = extract_int("Total globals+statics (namespace pollution):", text)

    exp = EXPECTED["global-vars"]
    assert total_globals == exp["total_globals"], f"Globals mismatch: {total_globals}"
    assert total_statics == exp["total_statics"], f"Statics mismatch: {total_statics}"
    assert total_externs == exp["total_externs"], f"Externs mismatch: {total_externs}"
    assert total_pollution == exp["total_pollution"], f"Pollution mismatch: {total_pollution}"


def test_cyclomatic(results_dir):
    path = find_result_file(results_dir, "cyclomatic")
    text = open(path, "r", encoding="utf-8", errors="ignore").read()
    functions = extract_int("Functions analyzed:", text)
    total_cc = extract_int("Total cyclomatic complexity:", text)
    avg_cc = extract_float("Average per function:", text)
    max_cc = extract_int("Max function complexity:", text)

    exp = EXPECTED["cyclomatic"]
    assert functions == exp["functions"], f"Function count mismatch: {functions}"
    assert total_cc == exp["total_cc"], f"Total CC mismatch: {total_cc}"
    assert_close(avg_cc, exp["avg_cc"], tolerance=0.01)
    assert max_cc == exp["max_cc"], f"Max CC mismatch: {max_cc}"


def test_faninout(results_dir):
    path = find_result_file(results_dir, "faninout")
    text = open(path, "r", encoding="utf-8", errors="ignore").read()
    functions = extract_int("Functions analyzed:", text)
    total_fan_out = extract_int("Total fan-out:", text)
    avg_fan_out = extract_float("Average fan-out per function:", text)
    max_fan_out = extract_int("Max fan-out:", text)
    total_fan_in = extract_int("Total fan-in:", text)
    avg_fan_in = extract_float("Average fan-in per function:", text)
    max_fan_in = extract_int("Max fan-in:", text)

    exp = EXPECTED["faninout"]
    assert functions == exp["functions"], f"Function count mismatch: {functions}"
    assert total_fan_out == exp["total_fan_out"], f"Total fan-out mismatch: {total_fan_out}"
    assert_close(avg_fan_out, exp["avg_fan_out"], tolerance=0.01)
    assert max_fan_out == exp["max_fan_out"], f"Max fan-out mismatch: {max_fan_out}"
    assert total_fan_in == exp["total_fan_in"], f"Total fan-in mismatch: {total_fan_in}"
    assert_close(avg_fan_in, exp["avg_fan_in"], tolerance=0.01)
    assert max_fan_in == exp["max_fan_in"], f"Max fan-in mismatch: {max_fan_in}"


def main():
    if not os.path.isdir(FIXTURES_DIR):
        print(f"Fixtures not found at {FIXTURES_DIR}")
        return 1

    results_dir = tempfile.mkdtemp(prefix="metrics-results-")
    try:
        run_metric(METRIC_SCRIPTS["loc"], FIXTURES_DIR, results_dir)
        run_metric(METRIC_SCRIPTS["comment-ratio"], FIXTURES_DIR, results_dir)
        run_metric(METRIC_SCRIPTS["global-vars"], FIXTURES_DIR, results_dir)

        if not ensure_lizard_available():
            return 2

        run_metric(METRIC_SCRIPTS["cyclomatic"], FIXTURES_DIR, results_dir)
        run_metric(METRIC_SCRIPTS["faninout"], FIXTURES_DIR, results_dir)

        test_loc(results_dir)
        test_comment_ratio(results_dir)
        test_global_vars(results_dir)
        test_cyclomatic(results_dir)
        test_faninout(results_dir)

        print("All metric tests passed.")
        return 0
    finally:
        shutil.rmtree(results_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
