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
  if [ "$name" = "junit5" ]; then
    git clone --depth 1 --filter=blob:none --sparse "$url" "src/$name"
    git -C "src/$name" sparse-checkout set junit-jupiter-engine
  elif [ "$name" = "spring-framework" ]; then
    git clone --depth 1 --filter=blob:none --sparse "$url" "src/$name"
    git -C "src/$name" sparse-checkout set spring-core
  else
    git clone --depth 1 "$url" "src/$name"
  fi
done < repos_10.txt

# Save analyzed commits (reproducibility)
echo "repository,scope_path,commit,origin_url" > analysis_out/repo_commits.csv
for d in src/*; do
  [ -d "$d/.git" ] || continue
  name="$(basename "$d")"
  scope_path="/"
  out_name="$name"

  if [ "$name" = "junit5" ]; then
    scope_path="/junit-jupiter-engine"
  elif [ "$name" = "spring-framework" ]; then
    scope_path="/spring-core"
  elif [ "$name" = "Java" ]; then
    out_name="thealgorithms-java"
  fi

  commit="$(git -C "$d" rev-parse HEAD)"
  origin="$(git -C "$d" remote get-url origin)"
  echo "$out_name,$scope_path,$commit,$origin" >> analysis_out/repo_commits.csv
done

echo "Done."
echo "Repos list: $ROOT/repos_10.txt"
echo "Commits:    $ROOT/analysis_out/repo_commits.csv"
