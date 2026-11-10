#!/usr/bin/env bash
# branch-guard.sh - PreToolUse (Edit|Write|NotebookEdit): E2 (ветки) и E18 (защищённые пути).
#
# Ранняя блокировка; авторитетная - git-хук pre-commit (planning-checks.py staged).
# Правка в main запрещена, кроме идущих merge/rebase/cherry-pick; PROTECTED_PATHS -
# только с маркером владельца hooks-edit текущей ветки. STRICT=off - не блокирует.
# Без jq хук не блокирует (SPEC п.7: jq только PreToolUse-хукам; нет - fail-open).
# exit 2 = блокировка тул-колла, stderr уходит модели как причина.
set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

input="$(cat 2>/dev/null)" || exit 0
[ -n "$input" ] || exit 0
file="$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)" || exit 0
[ -n "$file" ] || exit 0

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/strict-checks.py" branch-guard-file "$file"
