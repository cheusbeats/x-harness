#!/usr/bin/env bash
# Upstream installation contracts, with local Git fixtures instead of network access.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
scratch="$(mktemp -d "${TMPDIR:-/tmp}/xh-upstream.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
export REAL_GIT="$(command -v git)"
export XH_FIXTURES="$scratch/fixtures"
export XH_CLONE_LOG="$scratch/clones.log"
export HOME="$scratch/home"
export GIT_CONFIG_NOSYSTEM=1
mkdir -p "$XH_FIXTURES" "$scratch/fakebin" "$HOME"

for name in make-interfaces-feel-better impeccable; do
  repo="$XH_FIXTURES/$name"
  case "$name" in
    make-interfaces-feel-better) skill_path=skills/$name ;;
    impeccable) skill_path=.agents/skills/$name ;;
  esac
  mkdir -p "$repo/$skill_path/reference" "$repo/$skill_path/scripts"
  printf -- '---\nname: %s\ndescription: upstream fixture\n---\n' "$name" > "$repo/$skill_path/SKILL.md"
  printf '%s support\n' "$name" > "$repo/$skill_path/reference/guide.md"
  printf '#!/bin/sh\nexit 99\n' > "$repo/$skill_path/scripts/do-not-execute"
  chmod +x "$repo/$skill_path/scripts/do-not-execute"
  ln -s guide.md "$repo/$skill_path/reference/alias.md"
  printf private > "$repo/$skill_path/.env"
  printf unrelated > "$repo/outside.txt"
  "$REAL_GIT" -C "$repo" init -q
  "$REAL_GIT" -C "$repo" add .
  "$REAL_GIT" -C "$repo" -c user.name=Fixture -c user.email=fixture@example.invalid commit -qm fixture
  printf untracked > "$repo/$skill_path/untracked-secret.txt"
done

cat > "$scratch/fakebin/git" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
is_clone=0
for arg in "$@"; do [ "$arg" != clone ] || is_clone=1; done
if [ "$is_clone" = 0 ]; then exec "$REAL_GIT" "$@"; fi
args=("$@")
url="${args[${#args[@]}-2]}"
destination="${args[${#args[@]}-1]}"
case "$url" in
  https://github.com/jakubkrehel/make-interfaces-feel-better.git) name=make-interfaces-feel-better; skill_path=skills/$name ;;
  https://github.com/pbakaus/impeccable.git) name=impeccable; skill_path=.agents/skills/$name ;;
  *) echo "unexpected clone: $url" >&2; exit 90 ;;
esac
printf '%s\n' "$url" >> "$XH_CLONE_LOG"
[ "${XH_FAIL_UPSTREAM:-}" != "$name" ] || exit 91
"$REAL_GIT" clone -q -- "$XH_FIXTURES/$name" "$destination"
printf untracked > "$destination/$skill_path/untracked-secret.txt"
if [ "${XH_BAD_LINK:-}" = "$name" ]; then
  ln -s ../../../outside.txt "$destination/$skill_path/reference/escape"
  "$REAL_GIT" -C "$destination" add "$skill_path/reference/escape"
fi
WRAPPER
chmod +x "$scratch/fakebin/git"
export PATH="$scratch/fakebin:$PATH"

install_to() {
  local project="$1"; shift
  bash "$ROOT/install.sh" --project "$project" --no-git --clients none --skills project --no-verify "$@"
}
assert_empty() { test -z "$(ls -A "$1")"; }
mkdir "$scratch/dry" "$scratch/offline" "$scratch/none" "$scratch/failure" "$scratch/escape" "$scratch/project"
install_to "$scratch/dry" --dry-run > "$scratch/dry.log" 2>&1
assert_empty "$scratch/dry"
test ! -e "$XH_CLONE_LOG"
grep -q 'jakubkrehel/make-interfaces-feel-better.git' "$scratch/dry.log"
grep -q 'pbakaus/impeccable.git' "$scratch/dry.log"
install_to "$scratch/offline" --no-upstream-skills > "$scratch/offline.log" 2>&1
test -f "$scratch/offline/.ai/skills/laravel-clean-code/SKILL.md"
test ! -e "$scratch/offline/.ai/skills/impeccable"
install_to "$scratch/none" --skills global > "$scratch/none.log" 2>&1
test ! -e "$XH_CLONE_LOG"
if XH_FAIL_UPSTREAM=impeccable install_to "$scratch/failure" > "$scratch/failure.log" 2>&1; then exit 1; fi
assert_empty "$scratch/failure"
if XH_BAD_LINK=make-interfaces-feel-better install_to "$scratch/escape" > "$scratch/escape.log" 2>&1; then exit 1; fi
assert_empty "$scratch/escape"

install_to "$scratch/project" > "$scratch/project.log" 2>&1
for name in make-interfaces-feel-better impeccable; do
  for client in .ai .claude .agents .dsh; do
    skill="$scratch/project/$client/skills/$name"
    test -f "$skill/SKILL.md"
    test "$(cat "$skill/reference/guide.md")" = "$name support"
    test "$(readlink "$skill/reference/alias.md")" = guide.md
    test -x "$skill/scripts/do-not-execute"
    test ! -e "$skill/.git"
    test ! -e "$skill/.env"
    test ! -e "$skill/untracked-secret.txt"
  done
  grep -Eq "upstream $name: .* @ [0-9a-f]{40,64}" "$scratch/project.log"
done
printf original > "$scratch/project/.ai/skills/impeccable/keep"
rm "$scratch/project/.agents/skills/impeccable"
mkdir "$scratch/project/.agents/skills/impeccable"
printf custom > "$scratch/project/.agents/skills/impeccable/keep"
if install_to "$scratch/project" > "$scratch/conflict.log" 2>&1; then exit 1; fi
test "$(cat "$scratch/project/.ai/skills/impeccable/keep")" = original
install_to "$scratch/project" --force > "$scratch/force.log" 2>&1
backup="$(find "$scratch/project" -path '*/.ai/skills/impeccable/keep' | head -1)"
test -n "$backup"
test "$(cat "$backup")" = original
backup="$(find "$scratch/project/.agents/skills" -path '*/impeccable/keep' | head -1)"
test -n "$backup"
test "$(cat "$backup")" = custom
test -L "$scratch/project/.agents/skills/impeccable"

# Global copies also use upstream content, and force preserves existing skills.
mkdir "$scratch/global-project"
mkdir -p "$HOME/.agents/skills/impeccable"
printf original > "$HOME/.agents/skills/impeccable/keep"
bash "$ROOT/install.sh" --project "$scratch/global-project" --no-git --clients generic --skills global --no-verify > "$scratch/global.log" 2>&1
test "$(cat "$HOME/.agents/skills/impeccable/keep")" = original
test -f "$HOME/.agents/skills/make-interfaces-feel-better/reference/guide.md"
bash "$ROOT/install.sh" --project "$scratch/global-project" --no-git --clients generic --skills global --force --no-verify > "$scratch/global-force.log" 2>&1
test -f "$HOME/.agents/skills/impeccable/reference/guide.md"
backup="$(find "$HOME/.agents/skills" -path '*/impeccable/keep' | head -1)"
test -n "$backup"
test "$(cat "$backup")" = original
printf 'acceptance-upstream-skills: OK\n'
