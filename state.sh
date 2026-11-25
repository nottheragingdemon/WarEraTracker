#!/bin/sh
# Save/restore the SQLite history through a `state` branch (one orphan commit, force-pushed, so the repo never grows).
#   sh state.sh restore   - download wartrack.sqlite from the state branch (if there is one)
#   sh state.sh save      - compress wartrack.sqlite and force-push it as the only commit of the state branch
set -e
cd "$(dirname "$0")"
case "$1" in
  restore)
    if git fetch -q --depth=1 origin state 2>/dev/null; then
      git show FETCH_HEAD:wartrack.sqlite.xz | xz -d > wartrack.sqlite
      echo "restored wartrack.sqlite ($(du -h wartrack.sqlite | cut -f1))"
    else
      echo "no state branch yet; starting with an empty database"
    fi ;;
  save)
    T=$(mktemp -d)
    python3 -I - "$T/clean.sqlite" <<'PY'
import sqlite3, sys
db = sqlite3.connect("wartrack.sqlite"); db.execute("VACUUM INTO ?", (sys.argv[1],)); db.close()
PY
    xz -9 -c "$T/clean.sqlite" > "$T/wartrack.sqlite.xz"
    # one parentless commit holding only the compressed database, force-pushed to `state` (uses this repo's own remote and credentials)
    BLOB=$(git hash-object -w "$T/wartrack.sqlite.xz")
    TREE=$(printf '100644 blob %s\twartrack.sqlite.xz\n' "$BLOB" | git mktree)
    COMMIT=$(GIT_AUTHOR_NAME=warera-tracker GIT_AUTHOR_EMAIL=noreply@example.com GIT_COMMITTER_NAME=warera-tracker GIT_COMMITTER_EMAIL=noreply@example.com \
      git commit-tree "$TREE" -m "state $(date -u +%FT%TZ)")
    git push -q --force origin "$COMMIT:refs/heads/state"
    echo "saved state ($(du -h "$T/wartrack.sqlite.xz" | cut -f1))"
    rm -rf "$T" ;;
  *) echo "usage: sh state.sh restore|save"; exit 1 ;;
esac
