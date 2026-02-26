import os
import re
import sys
from datetime import datetime
import lizard

src_dir = sys.argv[1]      # /app
results_dir = sys.argv[2]  # /results

# Extensions we consider as source files
VALID_EXTS = (".c", ".h", ".cpp", ".cc", ".hpp", ".py", ".java", ".js", ".ts", ".go", ".rs")

call_pattern = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
keywords = {
    "if", "for", "while", "switch", "catch", "return", "sizeof",
    "new", "delete", "case", "else", "typeof", "throw", "typedef",
    "struct", "class", "enum"
}

project_name = None
for item in os.listdir(src_dir):
    if os.path.isdir(os.path.join(src_dir, item)) and not item.startswith('.'):
        project_name = item
        break
if not project_name:
    project_name = "project"

# Analyze code to get function boundaries
files = list(lizard.analyze([src_dir]))

# Build map: filename -> lines for later slicing
file_cache = {}
for file_info in files:
    if not file_info.filename.endswith(VALID_EXTS):
        continue
    try:
        with open(file_info.filename, "r", errors="ignore") as fh:
            file_cache[file_info.filename] = fh.readlines()
    except Exception:
        file_cache[file_info.filename] = []

# Gather declared function names
defined_names = set()
for file_info in files:
    for func in file_info.function_list:
        defined_names.add(func.name)

# Compute fan-out per function by scanning its body for call sites
function_metrics = []  # (fan_out, name, filename, start_line, end_line)
call_counts = {}       # name -> number of times it is called

for file_info in files:
    lines = file_cache.get(file_info.filename, [])
    for func in file_info.function_list:
        start = max(func.start_line - 1, 0)
        end = func.end_line if getattr(func, "end_line", None) else start + func.length
        if lines:
            end = min(end, len(lines))
            func_lines = lines[start:end]
            # Skip the function signature (first line) to avoid counting parameters
            if len(func_lines) > 1:
                # Find the opening brace and start from the line after
                for i, line in enumerate(func_lines):
                    if '{' in line:
                        func_lines = func_lines[i+1:]
                        break
            snippet = "".join(func_lines)
        else:
            snippet = ""
        fan_out = 0
        for match in call_pattern.finditer(snippet):
            name = match.group(1)
            if name in keywords:
                continue
            if name in defined_names:
                fan_out += 1
                call_counts[name] = call_counts.get(name, 0) + 1
        function_metrics.append((fan_out, func.name, file_info.filename, func.start_line, func.end_line or func.start_line))

# Derive fan-in from aggregated call counts
with_fan = []  # (fan_out, fan_in, func, file)
for fan_out, name, filename, start_line, end_line in function_metrics:
    fan_in = call_counts.get(name, 0)
    with_fan.append((fan_out, fan_in, name, filename, start_line, end_line))

# Aggregate totals
function_count = len(with_fan)
sum_fan_out = sum(item[0] for item in with_fan)
sum_fan_in = sum(item[1] for item in with_fan)
max_fan_out = max((item[0] for item in with_fan), default=0)
max_fan_in = max((item[1] for item in with_fan), default=0)

# Per-file summary
per_file = {}
for fan_out, fan_in, name, filename, start_line, end_line in with_fan:
    stats = per_file.setdefault(filename, {"fout": 0, "fin": 0, "count": 0, "max_out": 0, "max_in": 0})
    stats["fout"] += fan_out
    stats["fin"] += fan_in
    stats["count"] += 1
    stats["max_out"] = max(stats["max_out"], fan_out)
    stats["max_in"] = max(stats["max_in"], fan_in)

avg_fan_out = sum_fan_out / function_count if function_count else 0
avg_fan_in = sum_fan_in / function_count if function_count else 0

# Sort files by fan-out totals
file_rows = sorted(per_file.items(), key=lambda x: x[1]["fout"], reverse=True)

report_lines = []
report_lines.append(f"Project: {project_name}")
report_lines.append(f"Files analyzed: {len(files)}")
report_lines.append(f"Functions analyzed: {function_count}")
report_lines.append(f"Total fan-out: {sum_fan_out}")
report_lines.append(f"Average fan-out per function: {avg_fan_out:.2f}")
report_lines.append(f"Max fan-out: {max_fan_out}")
report_lines.append(f"Total fan-in: {sum_fan_in}")
report_lines.append(f"Average fan-in per function: {avg_fan_in:.2f}")
report_lines.append(f"Max fan-in: {max_fan_in}\n")

report_lines.append("Per-file summary (sorted by total fan-out):")
for filename, stats in file_rows:
    report_lines.append(
        f"  {filename}: fan-out={stats['fout']}, fan-in={stats['fin']}, functions={stats['count']}, max-out={stats['max_out']}, max-in={stats['max_in']}")

# Top 20 by fan-out
report_lines.append("\nTop 20 functions by fan-out:")
by_fan_out = sorted(with_fan, key=lambda x: x[0], reverse=True)
for fan_out, fan_in, name, filename, start_line, end_line in by_fan_out[:20]:
    report_lines.append(f"  FanOut={fan_out:3d} FanIn={fan_in:3d} | {name} ({filename}:{start_line})")

# Top 20 by fan-in
report_lines.append("\nTop 20 functions by fan-in:")
by_fan_in = sorted(with_fan, key=lambda x: x[1], reverse=True)
for fan_out, fan_in, name, filename, start_line, end_line in by_fan_in[:20]:
    report_lines.append(f"  FanIn={fan_in:3d} FanOut={fan_out:3d} | {name} ({filename}:{start_line})")

timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
output_file = os.path.join(results_dir, f"{project_name}-faninout-{timestamp}.txt")
with open(output_file, "w") as out:
    out.write("\n".join(report_lines) + "\n")
