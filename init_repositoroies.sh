#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/gx1/Git/Unina/Software/SW-Metrics-Collection"

cd "$ROOT"

# Clean + folders
rm -rf src results results_normalized analysis_out
mkdir -p src results results_normalized analysis_out

# 10 GitHub URLs (uno per riga)
cat > repos_10.txt <<'EOF'
https://github.com/square/retrofit.git
https://github.com/square/okio.git
https://github.com/apache/commons-lang.git
https://github.com/apache/commons-io.git
https://github.com/apache/commons-collections.git
https://github.com/google/guava.git
https://github.com/junit-team/junit5.git
https://github.com/spring-projects/spring-framework.git
https://github.com/google/gson.git
https://github.com/TheAlgorithms/Java.git
EOF

# Clone
while read -r url; do
  [ -z "$url" ] && continue
  name=$(basename "$url" .git)
  echo "Cloning $name ..."
  git clone --depth 1 "$url" "src/$name"
done < repos_10.txt

# Save analyzed commits (reproducibility)
echo "project,commit" > analysis_out/repo_commits.csv
for d in src/*; do
  [ -d "$d/.git" ] || continue
  echo "$(basename "$d"),$(git -C "$d" rev-parse HEAD)" >> analysis_out/repo_commits.csv
done

echo "Done."
echo "Repos list: $ROOT/repos_10.txt"
echo "Commits:    $ROOT/analysis_out/repo_commits.csv"