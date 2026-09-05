#!/usr/bin/env bash
# Run `make check` before every push.
#
# This repository's first two commits with CI attached went to main red,
# and both were things ruff names in under a second. There was no local
# gate: no venv, no Makefile, nothing to run. The tools were borrowed
# from another repository's virtualenv, after CI had already said so.
#
# The hook runs `make check` -- the same target CI runs -- so it cannot
# drift from CI: if the hook passes, the push passes.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK_DIR="$(git rev-parse --git-path hooks)"
case "$HOOK_DIR" in /*) ;; *) HOOK_DIR="$REPO_ROOT/$HOOK_DIR" ;; esac
mkdir -p "$HOOK_DIR"
HOOK="$HOOK_DIR/pre-push"

cat > "$HOOK" <<'HOOK_BODY'
#!/usr/bin/env bash
# Everything CI runs, before the push rather than after it.
# Regenerate with ./scripts/setup-hooks.sh
set -uo pipefail

# A branch DELETION has nothing to check. pre-push receives one line per
# refspec on stdin -- "<local_ref> <local_sha> <remote_ref> <remote_sha>"
# -- and a deletion's local_sha is all zeros. Without this, deleting a
# remote branch ran the whole suite to push nothing.
ZERO=0000000000000000000000000000000000000000
saw_refspec=""
has_commits=""
while read -r _local_ref local_sha _remote_ref _remote_sha; do
    saw_refspec=yes
    [ "$local_sha" != "$ZERO" ] || continue
    has_commits=yes
done
# Only skip when git said so. Run by hand, with nothing on stdin, the
# checks still run: an empty read must not be a way past them.
if [ -n "$saw_refspec" ] && [ -z "$has_commits" ]; then
    echo "Nothing to check: branch deletion(s) only."
    exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

echo "Running everything CI runs (make check)..."
if make check; then
  echo "All checks passed. Pushing..."
  exit 0
fi

cat >&2 <<'MSG'

The push is refused: `make check` failed.

Fix it, or push with --no-verify if you have a reason to. A red main in
this repository breaks the builds of every service that imports it.
MSG
exit 1
HOOK_BODY

chmod +x "$HOOK"
echo "pre-push hook installed at $HOOK"
echo "It runs 'make check' -- the same commands as .github/workflows/ci.yml."
