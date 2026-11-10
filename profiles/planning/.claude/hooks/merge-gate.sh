#!/usr/bin/env bash
# merge-gate.sh - PreToolUse (Bash): мерж в MAIN_BRANCH по SPEC §9.
#
# Требует: источник - feature/PLAN-N-* или hotfix/*; каждый не-мерж коммит ветки несёт
# свой токен; реестры RM/PLAN/HF чисты на дереве результата слияния; GATE_MERGE задан и зелёный на вершине; маркер владельца "merge <ветка>". Иначе exit 2.
# Мерж не в main и git pull в main разбираются в strict-checks.py.
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
printf '%s' "$cmd" | python3 "$DIR/strict-checks.py" merge
