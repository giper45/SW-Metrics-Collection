import os
import re
import sys
from datetime import datetime

src_dir = sys.argv[1]      # /app
results_dir = sys.argv[2]  # /results

VALID_EXTS = (".c", ".h", ".cpp", ".cc", ".hpp", ".py", ".java", ".js", ".ts", ".go", ".rs")

project_name = None
for item in os.listdir(src_dir):
    if os.path.isdir(os.path.join(src_dir, item)) and not item.startswith('.'):
        project_name = item
        break
if not project_name:
    project_name = "project"

# Regex patterns for comments
c_single = re.compile(r'//.*$')
c_multi_start = re.compile(r'/\*')
c_multi_end = re.compile(r'\*/')
py_single = re.compile(r'#.*$')

file_stats = []
total_comment_lines = 0
total_code_lines = 0
total_blank_lines = 0

for root, dirs, files in os.walk(src_dir):
    for f in files:
        if not f.endswith(VALID_EXTS):
            continue
        filepath = os.path.join(root, f)
        try:
            with open(filepath, "r", errors="ignore") as fh:
                lines = fh.readlines()
        except Exception:
            continue
        
        comment_count = 0
        code_count = 0
        blank_count = 0
        in_multiline = False
        
        for line in lines:
            stripped = line.strip()
            
            # Skip blank lines
            if not stripped:
                blank_count += 1
                continue
            
            # Handle multi-line comments
            if f.endswith((".c", ".h", ".cpp", ".cc", ".hpp", ".java", ".js", ".ts", ".go", ".rs")):
                if in_multiline:
                    comment_count += 1
                    if c_multi_end.search(line):
                        in_multiline = False
                    continue
                if c_multi_start.search(line):
                    comment_count += 1
                    if not c_multi_end.search(line):
                        in_multiline = True
                    continue
                if c_single.search(line):
                    comment_count += 1
                    continue
            
            # Handle Python comments
            if f.endswith(".py"):
                if py_single.search(line):
                    comment_count += 1
                    continue
            
            # Count as code
            code_count += 1
        
        if lines:
            ratio = (comment_count / len(lines) * 100) if len(lines) > 0 else 0
            file_stats.append((filepath, comment_count, code_count, blank_count, len(lines), ratio))
            total_comment_lines += comment_count
            total_code_lines += code_count
            total_blank_lines += blank_count

total_lines = total_comment_lines + total_code_lines + total_blank_lines
overall_ratio = (total_comment_lines / total_lines * 100) if total_lines > 0 else 0

# Sort by ratio descending
file_stats.sort(key=lambda x: x[5], reverse=True)

report_lines = []
report_lines.append(f"Project: {project_name}")
report_lines.append(f"Files analyzed: {len(file_stats)}")
report_lines.append(f"Total lines: {total_lines}")
report_lines.append(f"Comment lines: {total_comment_lines}")
report_lines.append(f"Code lines: {total_code_lines}")
report_lines.append(f"Blank lines: {total_blank_lines}")
report_lines.append(f"Overall comment ratio: {overall_ratio:.2f}%\n")

report_lines.append("Per-file summary (sorted by comment ratio):")
for filepath, cmt, code, blank, total, ratio in file_stats:
    report_lines.append(f"  {filepath}: comments={cmt}, code={code}, blank={blank}, total={total}, ratio={ratio:.2f}%")

report_lines.append("\nTop 20 files by comment ratio:")
for filepath, cmt, code, blank, total, ratio in file_stats[:20]:
    report_lines.append(f"  {ratio:6.2f}% | {filepath} (cmt={cmt}, code={code})")

report_lines.append("\nBottom 20 files by comment ratio (least commented):")
for filepath, cmt, code, blank, total, ratio in file_stats[-20:]:
    report_lines.append(f"  {ratio:6.2f}% | {filepath} (cmt={cmt}, code={code})")

timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
output_file = os.path.join(results_dir, f"{project_name}-comment-ratio-{timestamp}.txt")
with open(output_file, "w") as out:
    out.write("\n".join(report_lines) + "\n")
