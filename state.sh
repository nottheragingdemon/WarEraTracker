#!/bin/sh
# Save/restore the SQLite history through a `state` branch (one orphan commit, force-pushed, so the repo never grows).
#   sh state.sh restore   - download wartrack.sqlite from the state branch (if there is one)
#   sh state.sh save      - compress wartrack.sqlite and force-push it as the only commit of the state branch
#   sh state.sh backup    - copy the state commit to backup/state-YYYY-MM-DD (weekly workflow), keeping the newest 4
set -e
cd "$(dirname "$0")"
case "$1" in
  restore)
    # the state branch first; if it is missing or damaged, the newest weekly backup (backup/state-YYYY-MM-DD)
    for REF in state $(git ls-remote --heads origin 'backup/state-*' 2>/dev/null | sed 's#.*refs/heads/##' | sort -r); do
      if git fetch -q --depth=1 origin "$REF" 2>/dev/null && git show FETCH_HEAD:wartrack.sqlite.xz | xz -d > wartrack.sqlite.tmp 2>/dev/null \
         && python3 -I -c "import sqlite3,sys; d=sqlite3.connect(sys.argv[1]); sys.exit(d.execute('PRAGMA integrity_check').fetchone()[0]!='ok')" wartrack.sqlite.tmp; then
        mv wartrack.sqlite.tmp wartrack.sqlite
        echo "restored wartrack.sqlite from $REF ($(du -h wartrack.sqlite | cut -f1))"
        [ "$REF" = state ] || echo "WARNING: the state branch was missing or damaged; restored the backup $REF"
        exit 0
      fi
      echo "could not restore from $REF, trying the next copy"
    done
    rm -f wartrack.sqlite.tmp
    echo "no state branch or backup yet; starting with an empty database" ;;
  backup)
    # copy the current state commit to a dated backup branch (no new data in the repo: same commit), keep the newest 4
    git fetch -q --depth=1 origin state
    NAME="backup/state-$(date -u +%F)"
    git push -q --force origin "FETCH_HEAD:refs/heads/$NAME"
    echo "backed up state to $NAME"
    git ls-remote --heads origin 'backup/state-*' | sed 's#.*refs/heads/##' | sort -r | tail -n +5 | while read -r OLD; do
      git push -q origin --delete "$OLD" && echo "removed old backup $OLD"
    done ;;
  save)
    # refuse to overwrite the history with a damaged or emptied database
    python3 -I - <<'PY'
import sqlite3, sys
d = sqlite3.connect("wartrack.sqlite")
if d.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
    sys.exit("state.sh: wartrack.sqlite failed its integrity check; not saving")
tables = {r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
if "battles" in tables and d.execute("SELECT COUNT(*) FROM battles").fetchone()[0] == 0 and \
   "player_snap" in tables and d.execute("SELECT COUNT(*) FROM player_snap").fetchone()[0] == 0:
    sys.exit("state.sh: wartrack.sqlite has no battles and no player history; not saving over the stored state")
PY
    T=$(mktemp -d)
    python3 -I - "$T/clean.sqlite" <<'PY'
import sqlite3, sys
db = sqlite3.connect("wartrack.sqlite"); db.execute("VACUUM INTO ?", (sys.argv[1],)); db.close()
PY
    # all CPU cores, level 6: about 3x faster than single-threaded -9 for ~15% more bytes; restore reads it the same way
    xz -T0 -6 -c "$T/clean.sqlite" > "$T/wartrack.sqlite.xz"
    # one parentless commit holding only the compressed database, force-pushed to `state` (uses this repo's own remote and credentials)
    BLOB=$(git hash-object -w "$T/wartrack.sqlite.xz")
    TREE=$(printf '100644 blob %s\twartrack.sqlite.xz\n' "$BLOB" | git mktree)
    COMMIT=$(GIT_AUTHOR_NAME=warera-tracker GIT_AUTHOR_EMAIL=noreply@example.com GIT_COMMITTER_NAME=warera-tracker GIT_COMMITTER_EMAIL=noreply@example.com \
      git commit-tree "$TREE" -m "state $(date -u +%FT%TZ)")
    git push -q --force origin "$COMMIT:refs/heads/state"
    echo "saved state ($(du -h "$T/wartrack.sqlite.xz" | cut -f1))"
    rm -rf "$T" ;;
  *) echo "usage: sh state.sh restore|save|backup"; exit 1 ;;
esac
