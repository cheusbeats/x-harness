#!/usr/bin/env bash
# Exercise a skill-manager copy without .git, with a local upstream Git fixture.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/xh-skill-bootstrap.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
export REAL_GIT="$(command -v git)"
export XH_SOURCE_FIXTURE="$scratch/source"
export XH_BOOTSTRAP_LOG="$scratch/clones.log"
export TMPDIR="$scratch/tmp"
mkdir -p "$XH_SOURCE_FIXTURE" "$scratch/fakebin" "$scratch/installed-skill/scripts" "$scratch/tmp"
# A real committed source fixture, not a fabricated installer response.
"$REAL_GIT" -C "$ROOT" archive HEAD | tar -x -C "$XH_SOURCE_FIXTURE"
"$REAL_GIT" -C "$XH_SOURCE_FIXTURE" init -q -b main
"$REAL_GIT" -C "$XH_SOURCE_FIXTURE" add .
"$REAL_GIT" -C "$XH_SOURCE_FIXTURE" -c user.name=Fixture -c user.email=fixture@example.invalid commit -qm fixture
cp "$ROOT/skills/x-harness/scripts/install-from-source" "$scratch/installed-skill/scripts/install-from-source"
# The installed skill has no harness, Git checkout, or sealed manifest.
cat > "$scratch/fakebin/git" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
is_clone=0
for arg in "$@"; do [ "$arg" != clone ] || is_clone=1; done
if [ "$is_clone" = 0 ]; then exec "$REAL_GIT" "$@"; fi
args=("$@")
source_url="${args[${#args[@]}-2]}"
destination="${args[${#args[@]}-1]}"
[ "$source_url" = https://github.com/cheusbeats/x-harness.git ] || exit 90
printf '%s\n' "$source_url" >> "$XH_BOOTSTRAP_LOG"
[ "${XH_BOOTSTRAP_FAIL:-0}" != 1 ] || exit 91
"$REAL_GIT" -c core.hooksPath=/dev/null clone --quiet -- "$XH_SOURCE_FIXTURE" "$destination"
WRAPPER
chmod 755 "$scratch/fakebin/git"
export PATH="$scratch/fakebin:$PATH"
bootstrap="$scratch/installed-skill/scripts/install-from-source"
mkdir "$scratch/dry" "$scratch/failed" "$scratch/project with spaces"
bash "$bootstrap" --project "$scratch/dry" --dry-run > "$scratch/dry.log"
bash "$bootstrap" --help > "$scratch/help.log"
test ! -e "$XH_BOOTSTRAP_LOG"
test -z "$(ls -A "$scratch/dry")"
if XH_BOOTSTRAP_FAIL=1 bash "$bootstrap" --project "$scratch/failed" --clients none --skills none > "$scratch/failure.log" 2>&1; then exit 1; fi
test -z "$(ls -A "$scratch/failed")"
test -z "$(find "$scratch/tmp" -maxdepth 1 -name 'xh-source.*' -print)"
# Preserve arguments containing spaces and honor the explicitly selected target.
bash "$bootstrap" --project "$scratch/project with spaces" --no-git --clients none --skills none > "$scratch/install.log" 2>&1
test -f "$scratch/project with spaces/.claude/settings.json"
test -f "$scratch/project with spaces/.ai/skills/laravel-clean-code/SKILL.md"
test ! -e "$scratch/installed-skill/.claude"
grep -Eq 'x-harness source: .* @ [0-9a-f]{40,64}' "$scratch/install.log"
test -z "$(find "$scratch/tmp" -maxdepth 1 -name 'xh-source.*' -print)"
# Refuse a conflicting target, leaving the old file and no extra payload.
mkdir -p "$scratch/conflict/.claude"
printf original > "$scratch/conflict/.claude/keep"
if bash "$bootstrap" --project "$scratch/conflict" --no-git --clients none --skills none > "$scratch/conflict.log" 2>&1; then exit 1; fi
test "$(cat "$scratch/conflict/.claude/keep")" = original
test ! -e "$scratch/conflict/planning"
test -z "$(find "$scratch/tmp" -maxdepth 1 -name 'xh-source.*' -print)"
echo 'acceptance-skill-bootstrap: OK'
