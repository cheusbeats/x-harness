#!/bin/bash
set -euo pipefail
scratch="$(mktemp -d "${TMPDIR:-/tmp}/xh-installer.XXXXXX")"
scratch="$(cd "$scratch" && pwd -P)"
trap 'rm -rf "$scratch"' EXIT
installer="$(cd "$(dirname "$0")/.." && pwd)/install.sh"
cd "$scratch"
name='case$(touch${IFS}XH_INJECTED)'
mkdir "$name"
for profile in full planning; do
  bash "$installer" --project "$scratch/$name" --profile "$profile" --no-git --clients none --skills none --no-verify --dry-run > "$scratch/dry-$profile.log" 2>&1
  test ! -e "$scratch/$name/planning"
  test ! -e "$scratch/XH_INJECTED"
done
bash "$installer" --project "$scratch/$name" --profile full --no-git --clients none --skills none --no-verify > "$scratch/apply.log" 2>&1
test -f "$scratch/$name/planning/README.md"
test ! -e "$scratch/XH_INJECTED"
mkdir conflict
mkdir conflict/.claude
printf original > conflict/.claude/keep
if bash "$installer" --project "$scratch/conflict" --profile full --no-git --clients none --skills none --no-verify > "$scratch/conflict.log" 2>&1; then exit 1; fi
test "$(cat conflict/.claude/keep)" = original
test ! -e conflict/planning
bash "$installer" --project "$scratch/conflict" --profile full --no-git --clients none --skills none --force --no-verify > "$scratch/force.log" 2>&1
test -f conflict/.claude/settings.json
test "$(cat conflict/.x-harness-backup.*/.claude/keep)" = original
# A pre-existing Git hooksPath must survive without a partial installation.
git init -q hooks-project
git -C hooks-project config core.hooksPath /private/tmp/other-user-hooks
if bash "$installer" --project "$scratch/hooks-project" --profile planning --clients none --skills none --no-verify > "$scratch/hooks-conflict.log" 2>&1; then exit 1; fi
test "$(git -C hooks-project config --get core.hooksPath)" = /private/tmp/other-user-hooks
test ! -e hooks-project/planning
test ! -e hooks-project/.claude
for hooks_path in .githooks "$scratch/hooks-project/.githooks"; do
  git -C hooks-project config core.hooksPath "$hooks_path"
  bash "$installer" --project "$scratch/hooks-project" --profile planning --clients none --skills none --no-verify --dry-run > "$scratch/hooks-equivalent.log" 2>&1
done
test ! -e hooks-project/planning

# Refuse destination symlinks escaping the target, before any project writes.
mkdir outside
printf untouched > outside/sentinel
for item in planning codex agents nested; do
  mkdir "project-$item"
  case "$item" in
    planning) ln -s "$scratch/outside" "project-$item/planning" ;;
    codex) ln -s "$scratch/outside" "project-$item/.codex" ;;
    agents) mkdir "project-$item/.agents"; ln -s "$scratch/outside" "project-$item/.agents/skills" ;;
    nested) mkdir "project-$item/planning"; ln -s "$scratch/outside" "project-$item/planning/plans" ;;
  esac
  if bash "$installer" --project "$scratch/project-$item" --profile planning --no-git --clients codex --skills project --force --no-verify > "$scratch/symlink-$item.log" 2>&1; then exit 1; fi
  test "$(cat "$scratch/outside/sentinel")" = untouched
  test ! -e "project-$item/.claude"
done
# DSH output files must not follow external symlinks.
mkdir -p project-dsh/.dsh
ln -s "$scratch/outside/sentinel" project-dsh/.dsh/hooks.json
if bash "$installer" --project "$scratch/project-dsh" --profile planning --no-git --clients none --skills none --dsh-hooks community --force --no-verify > "$scratch/dsh-symlink.log" 2>&1; then exit 1; fi
test "$(cat "$scratch/outside/sentinel")" = untouched
test ! -e project-dsh/.claude
# Generated shell configuration must quote directory names before planning-init sources it.
mkdir -p 'project-conf/case$(touch${IFS}XH_CONF_INJECTED)'
bash "$installer" --project "$scratch/project-conf" --profile planning --no-git --clients none --skills none --no-verify > "$scratch/conf.log" 2>&1
test ! -e project-conf/XH_CONF_INJECTED
# Path repair must preserve TOML quoting and literal backslashes.
mkdir -p 'project-"quoted\path/.codex'
printf 'cwd = "old"\n' > 'project-"quoted\path/.codex/config.toml'
bash "$installer" --project "$scratch/project-\"quoted\path" --profile planning --no-git --clients none --skills none --fix-paths --no-verify > "$scratch/quoted.log" 2>&1
python3 - "$scratch/project-\"quoted\path" <<'PY_QUOTED'
import json, sys
from pathlib import Path
project = Path(sys.argv[1])
value = (project / '.codex/config.toml').read_text().split('=', 1)[1].strip()
assert json.loads(value) == str(project)
PY_QUOTED
# An existing internal skills symlink remains supported and links resolve correctly.
mkdir -p project-internal/.agents project-internal/shared
ln -s ../shared project-internal/.agents/skills
bash "$installer" --project "$scratch/project-internal" --profile full --no-git --clients none --skills project --no-upstream-skills --no-verify > "$scratch/internal.log" 2>&1
test -f project-internal/.agents/skills/laravel-best-practices/SKILL.md

# Exercise the actual global-copy functions with an isolated destination without altering HOME.
repo="$scratch/source"
mkdir -p "$repo/harness/.ai/skills/laravel-best-practices" "$repo/skills/x-harness/scripts"
printf 'skill fixture\n' > "$repo/skills/x-harness/SKILL.md"
printf '#!/bin/sh\n' > "$repo/skills/x-harness/scripts/install-from-source"
printf 'skill fixture\n' > "$repo/harness/.ai/skills/laravel-best-practices/SKILL.md"
cp "$installer" "$repo/install.sh"
git init -q "$repo"
git -C "$repo" add skills install.sh harness
printf private > "$repo/untracked-secret.txt"
printf private > "$repo/harness/.ai/skills/laravel-best-practices/untracked-secret.txt"
printf private > "$repo/harness/.ai/skills/laravel-best-practices/.env"
python3 - "$installer" "$scratch/functions.sh" <<'PY_FUNCTIONS'
from pathlib import Path
import sys
s = Path(sys.argv[1]).read_text()
managed_start = s.index('managed_copy()')
managed_end = s.index('\n# Codex-адаптер:', managed_start)
start = s.index('install_skill_copy()')
end = s.index('\nif [ "$PROFILE" = full ]; then\n  install_project_skills()', start)
Path(sys.argv[2]).write_text(s[managed_start:managed_end] + s[start:end])
PY_FUNCTIONS
bash -c 'set -euo pipefail; ROOT="$1"; DRY=0; FORCE=0; run() { "$@"; }; source "$2"; install_tracked_skill "$ROOT/skills/x-harness" x-harness "$3"; install_tracked_skill "$ROOT/harness/.ai/skills/laravel-best-practices" laravel-best-practices "$3"' _ "$repo" "$scratch/functions.sh" "$scratch/global"
test -f "$scratch/global/x-harness/SKILL.md"
test -f "$scratch/global/x-harness/scripts/install-from-source"
test -f "$scratch/global/laravel-best-practices/SKILL.md"
test ! -e "$scratch/global/x-harness/.git"
test ! -e "$scratch/global/x-harness/untracked-secret.txt"
test ! -e "$scratch/global/x-harness/harness"
test ! -e "$scratch/global/laravel-best-practices/untracked-secret.txt"
test ! -e "$scratch/global/laravel-best-practices/.env"
# Check global destination parents using a synthetic home, without altering HOME.
mkdir -p "$scratch/synthetic-home/.codex"
ln -s "$scratch/outside" "$scratch/synthetic-home/.codex/skills"
if bash -c 'set -euo pipefail; source "$1"; check_destination_parents "$2" .codex/skills' _ "$scratch/functions.sh" "$scratch/synthetic-home" > "$scratch/global-symlink.log" 2>&1; then exit 1; fi
test "$(cat "$scratch/outside/sentinel")" = untouched
# A tracked source file whose parent becomes an outside symlink is rejected.
mkdir -p "$scratch/bad-source/harness/sub" "$scratch/bad-source/skills/x-harness" "$scratch/external-source"
printf fixture > "$scratch/bad-source/skills/x-harness/SKILL.md"
printf fixture > "$scratch/bad-source/harness/sub/file"
printf external > "$scratch/external-source/file"
git init -q "$scratch/bad-source"
git -C "$scratch/bad-source" add skills harness
mv "$scratch/bad-source/harness/sub" "$scratch/bad-source/harness/old-sub"
ln -s "$scratch/external-source" "$scratch/bad-source/harness/sub"
if bash -c 'set -euo pipefail; ROOT="$1"; DRY=0; source "$2"; managed_copy --check' _ "$scratch/bad-source" "$scratch/functions.sh" > "$scratch/source-symlink.log" 2>&1; then exit 1; fi
test "$(cat "$scratch/external-source/file")" = external
# Manifest entries missing from Git's managed catalog must fail, not silently drop roles.
mkdir -p "$scratch/untracked-role/harness/.codex/agents" "$scratch/untracked-role/skills/x-harness"
printf fixture > "$scratch/untracked-role/skills/x-harness/SKILL.md"
printf fixture > "$scratch/untracked-role/harness/.codex/agents/test-writer.toml"
python3 - "$scratch/untracked-role" <<'PY_MANIFEST_TEST'
from pathlib import Path
import hashlib, sys
root = Path(sys.argv[1]); f = root / 'harness/.codex/agents/test-writer.toml'
(root / 'MANIFEST.sha256').write_text('H 644 ' + hashlib.sha256(f.read_bytes()).hexdigest() + ' .codex/agents/test-writer.toml\n')
PY_MANIFEST_TEST
git init -q "$scratch/untracked-role"
git -C "$scratch/untracked-role" add skills MANIFEST.sha256
if bash -c 'set -euo pipefail; ROOT="$1"; DRY=0; source "$2"; managed_copy --check' _ "$scratch/untracked-role" "$scratch/functions.sh" > "$scratch/untracked-role.log" 2>&1; then exit 1; fi
grep -q 'test-writer.toml' "$scratch/untracked-role.log"
# Full bundle produced from Git works without .git; untracked source files never enter project.
package="$(cd "$(dirname "$installer")" && pwd)"
bash -c 'set -euo pipefail; ROOT="$1"; DRY=0; source "$2"; managed_copy "$ROOT" "$3"' _ "$package" "$scratch/functions.sh" "$scratch/offline"
test -f "$scratch/offline/.x-harness-package.json"
test ! -e "$scratch/offline/.git"
printf private > "$scratch/offline/harness/.ai/skills/laravel-best-practices/untracked-secret.txt"
printf private > "$scratch/offline/harness/.ai/skills/laravel-best-practices/.env"
mkdir "$scratch/offline-project"
bash "$scratch/offline/install.sh" --project "$scratch/offline-project" --profile full --no-git --clients none --skills project --no-upstream-skills --no-verify > "$scratch/offline-install.log" 2>&1
test -f "$scratch/offline-project/.ai/skills/laravel-best-practices/SKILL.md"
test -f "$scratch/offline-project/.agents/skills/laravel-best-practices/SKILL.md"
test ! -e "$scratch/offline-project/.ai/skills/laravel-best-practices/untracked-secret.txt"
test ! -e "$scratch/offline-project/.ai/skills/laravel-best-practices/.env"
printf tampered >> "$scratch/offline/harness/CLAUDE.md"
mkdir "$scratch/tampered-project"
if bash "$scratch/offline/install.sh" --project "$scratch/tampered-project" --profile full --no-git --clients none --skills none --no-verify > "$scratch/tampered.log" 2>&1; then exit 1; fi
test ! -e "$scratch/tampered-project/planning"
echo 'PASS dry-run, injection, conflicts, hooksPath, symlink boundaries, tracked-only bundles, offline installation and tamper detection'
