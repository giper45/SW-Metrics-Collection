import os
import re
import sys
from datetime import datetime

src_dir = sys.argv[1]      # /app
results_dir = sys.argv[2]  # /results

C_EXTS = (".c", ".h")

project_name = None
for item in os.listdir(src_dir):
    if os.path.isdir(os.path.join(src_dir, item)) and not item.startswith('.'):
        project_name = item
        break
if not project_name:
    project_name = "project"

# Regex patterns for C
comment_single = re.compile(r'//.*$')
comment_multi_start = re.compile(r'/\*')
comment_multi_end = re.compile(r'\*/')

# Match function definitions: type name(...) { or type name(...);
func_def = re.compile(r'^\s*(?:static\s+)?(?:inline\s+)?(?:const\s+)?(?:volatile\s+)?(?:struct|union|enum)?\s*\w+[\s\*]+(\w+)\s*\([^)]*\)\s*(?:{|;)', re.MULTILINE)

# Match global/static declarations at file scope
# Pattern: type name; or type name = init;
global_pattern = re.compile(r'^\s*(?:static\s+)?(?:const\s+)?(?:volatile\s+)?(?:extern\s+)?[\w\s\*]+\s+(\w+)\s*(?:\[[^\]]*\])*\s*(?:=\s*[^;]+)?\s*;', re.MULTILINE)

file_stats = []
total_globals = 0
total_statics = 0
total_externs = 0

for root, dirs, files in os.walk(src_dir):
    for f in files:
        if not f.endswith(C_EXTS):
            continue
        filepath = os.path.join(root, f)
        try:
            with open(filepath, "r", errors="ignore") as fh:
                code = fh.read()
        except Exception:
            continue
        
        # Remove comments
        code = comment_single.sub('', code)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        
        # Find function definitions to determine scope
        func_matches = list(func_def.finditer(code))
        func_ranges = []
        for m in func_matches:
            # Find opening brace
            start = m.end()
            brace_count = 0
            in_func = False
            for i, ch in enumerate(code[start:]):
                if ch == '{':
                    brace_count += 1
                    in_func = True
                elif ch == '}':
                    brace_count -= 1
                    if in_func and brace_count == 0:
                        func_ranges.append((m.start(), start + i))
                        break
        
        # Extract globals/statics (outside function bodies)
        globals_list = []
        statics_list = []
        externs_list = []
        
        for match in global_pattern.finditer(code):
            pos = match.start()
            is_in_func = any(start <= pos <= end for start, end in func_ranges)
            
            if not is_in_func:
                var_name = match.group(1)
                full_match = match.group(0)
                
                if 'extern' in full_match:
                    externs_list.append(var_name)
                elif 'static' in full_match:
                    statics_list.append(var_name)
                else:
                    globals_list.append(var_name)
        
        num_globals = len(globals_list)
        num_statics = len(statics_list)
        num_externs = len(externs_list)
        total_scope_pollution = num_globals + num_statics  # namespace pollution
        
        if num_globals + num_statics + num_externs > 0:
            file_stats.append({
                'filepath': filepath,
                'globals': num_globals,
                'statics': num_statics,
                'externs': num_externs,
                'total': num_globals + num_statics + num_externs,
                'pollution': total_scope_pollution,
                'global_names': globals_list,
                'static_names': statics_list,
                'extern_names': externs_list
            })
            total_globals += num_globals
            total_statics += num_statics
            total_externs += num_externs

# Sort by pollution (globals + statics)
file_stats.sort(key=lambda x: x['pollution'], reverse=True)

report_lines = []
report_lines.append(f"Project: {project_name}")
report_lines.append(f"Files analyzed: {len(file_stats)}")
report_lines.append(f"Total global variables (non-static): {total_globals}")
report_lines.append(f"Total static variables: {total_statics}")
report_lines.append(f"Total extern declarations: {total_externs}")
report_lines.append(f"Total globals+statics (namespace pollution): {total_globals + total_statics}\n")

report_lines.append("Global Variable Complexity by File (sorted by pollution risk):")
for stat in file_stats:
    report_lines.append(
        f"  {stat['filepath']}: "
        f"globals={stat['globals']}, statics={stat['statics']}, "
        f"externs={stat['externs']}, pollution={stat['pollution']}")

report_lines.append("\nTop 20 files by namespace pollution (globals + statics):")
for stat in file_stats[:20]:
    report_lines.append(
        f"  Pollution={stat['pollution']:3d} (G={stat['globals']:2d} S={stat['statics']:2d} E={stat['externs']:2d}) | {stat['filepath']}")

report_lines.append("\nFiles with highest static variable count (data hiding):")
by_statics = sorted(file_stats, key=lambda x: x['statics'], reverse=True)
for stat in by_statics[:20]:
    if stat['statics'] > 0:
        report_lines.append(
            f"  Statics={stat['statics']:3d} | {stat['filepath']}")

report_lines.append("\nTop 20 files by global variable count (true globals - worst case):")
by_globals = sorted(file_stats, key=lambda x: x['globals'], reverse=True)
for stat in by_globals[:20]:
    if stat['globals'] > 0:
        report_lines.append(
            f"  Globals={stat['globals']:3d} | {stat['filepath']}")

report_lines.append("\nDetailed global variable listing (top 10 most polluted files):")
for stat in file_stats[:10]:
    if stat['globals'] + stat['statics'] > 0:
        report_lines.append(f"\n  {stat['filepath']}:")
        if stat['global_names']:
            report_lines.append(f"    Global: {', '.join(stat['global_names'][:10])}")
            if len(stat['global_names']) > 10:
                report_lines.append(f"             ... and {len(stat['global_names']) - 10} more")
        if stat['static_names']:
            report_lines.append(f"    Static: {', '.join(stat['static_names'][:10])}")
            if len(stat['static_names']) > 10:
                report_lines.append(f"             ... and {len(stat['static_names']) - 10} more")
        if stat['extern_names']:
            report_lines.append(f"    Extern: {', '.join(stat['extern_names'][:5])}")
            if len(stat['extern_names']) > 5:
                report_lines.append(f"             ... and {len(stat['extern_names']) - 5} more")

timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
output_file = os.path.join(results_dir, f"{project_name}-global-vars-{timestamp}.txt")
with open(output_file, "w") as out:
    out.write("\n".join(report_lines) + "\n")
