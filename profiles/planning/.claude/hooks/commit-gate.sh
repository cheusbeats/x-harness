#!/usr/bin/env bash
# commit-gate.sh - PreToolUse (Bash): E16 (обходы хуков), ветка коммита (E2),
# ранние planning-checks.py staged + registry.sh check. Мерж и пуш делегированы
# merge-gate.sh и main-push-guard.sh (они висят на том же событии).
#
# Это чокпоинт, который не обойти правкой через Bash: любой коммит идёт через него.
# exit 2 = блокировка тул-колла, stderr уходит модели как причина.
# Без jq/python3 - fail-open (SPEC п.7); STRICT=off - не блокирует (решает python).
set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

input="$(cat 2>/dev/null)" || exit 0
[ -n "$input" ] || exit 0
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)" || exit 0
[ -n "$cmd" ] || exit 0

# Каталог вызова нужен разбору "cd ... && git ..." / "git -C ..."; проект - из CLAUDE_PROJECT_DIR.
export GUARD_ORIG_PWD="$PWD"
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}" || exit 0

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
printf '%s' "$cmd" | python3 "$DIR/strict-checks.py" commit
