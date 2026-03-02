#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$ROOT"

# Clean + folders
rm -rf src results results_normalized analysis_out
mkdir -p src results results_normalized analysis_out

# Repositories frozen to the snapshots listed in paper/main.tex (Table repo-panel).
# CSV columns: repository,url,scope_path,commit
cat > repos_10.txt <<'EOF'
repository,url,scope_path,commit
retrofit,https://github.com/square/retrofit.git,/,bda19026d991878d5ead4b1ad0c606bfdf4e25b9
okio,https://github.com/square/okio.git,/,fc7aecb7f6f7a123f2024ab6397da04311546bf2
commons-lang,https://github.com/apache/commons-lang.git,/,a4dd12fb8f1d22077a20f4d63046572ebb92bf7b
commons-io,https://github.com/apache/commons-io.git,/,2dd12489df2dd9cfd387dea6360d8e3cb7117c36
commons-collections,https://github.com/apache/commons-collections.git,/,f42a7af2662546b4a7f8a7166c1c0cbd2b638980
guava,https://github.com/google/guava.git,/,166a675f454c1009de9968f3ede95c73aa2798dc
junit5,https://github.com/junit-team/junit5.git,/junit-jupiter-engine,4d034a78bb64f870c1236457c3a50b79155da00b
spring-framework,https://github.com/spring-projects/spring-framework.git,/spring-core,0dc44f79d5f83d0fc1f45abe9d46b398e2c1cf3f
gson,https://github.com/google/gson.git,/,a8e6c962ea4f0eed90a3e81f406fb27ed2f4298d
Java,https://github.com/TheAlgorithms/Java.git,/,7e5d9d469d8d2deb7309a1003dafdeb884c7dd84
EOF

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
