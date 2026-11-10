#!/usr/bin/env bash
# main-push-guard.sh - PreToolUse (Bash): защита main при push (SPEC §9), без сети.
#
# Блокирует: force/delete/+/--all/--mirror; push в main из не-main; прямые (не-мерж)
# коммиты впереди <remote>/main; remote или его tracking main не проверить локально.
# Пуши feature/*, hotfix/* и тегов проходят. exit 2 = блокировка тул-колла.
# Без jq/python3 - fail-open (SPEC п.7); STRICT=off - не блокирует (решает python).
set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

input="$(cat 2>/dev/null)" || exit 0
[ -n "$input" ] || exit 0
cmd="$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null)" || exit 0
[ -n "$cmd" ] || exit 0

export GUARD_ORIG_PWD="$PWD"
cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}" || exit 0

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
printf '%s' "$cmd" | python3 "$DIR/strict-checks.py" push
