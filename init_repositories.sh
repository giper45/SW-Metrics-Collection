#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$ROOT"

# Clean + folders
rm -rf src results results_normalized analysis_out
mkdir -p src results results_normalized analysis_out

if [ ! -f repos_10.txt ]; then
  echo "Missing repos_10.txt (CSV: repository,url,scope_path,commit)" >&2
  exit 1
fi

# Clone + checkout frozen commit
tail -n +2 repos_10.txt | while IFS=, read -r name url scope_path commit; do
  [ -z "$name" ] && continue
  echo "Cloning $name @ ${commit:0:12} ..."

  if [ "$name" = "junit5" ] || [ "$name" = "spring-framework" ]; then
    git clone --depth 1 --filter=blob:none --sparse "$url" "src/$name"
    git -C "src/$name" sparse-checkout set "${scope_path#/}"
  else
    git clone --depth 1 "$url" "src/$name"
  fi

  if ! git -C "src/$name" cat-file -e "${commit}^{commit}" 2>/dev/null; then
    git -C "src/$name" fetch --depth 1 origin "$commit"
  fi
  git -C "src/$name" checkout --detach "$commit"
done

# Save analyzed commits (reproducibility)
echo "repository,scope_path,commit,origin_url" > analysis_out/repo_commits.csv
tail -n +2 repos_10.txt | while IFS=, read -r name url scope_path commit; do
  [ -z "$name" ] && continue
  out_name="$name"
  if [ "$name" = "Java" ]; then
    out_name="thealgorithms-java"
  fi

  resolved_commit="$(git -C "src/$name" rev-parse HEAD)"
  origin="$(git -C "src/$name" remote get-url origin)"
  echo "$out_name,$scope_path,$resolved_commit,$origin" >> analysis_out/repo_commits.csv
done

echo "Done."
echo "Repos list: $ROOT/repos_10.txt (frozen snapshots)"
echo "Commits:    $ROOT/analysis_out/repo_commits.csv"
