#!/usr/bin/env bash
# PreToolUse на Bash: агент не чистит рабочую БД (.claude/rules/working-rules.md). Логика и список форм - db_wipe_checks.py.
# exit 2 = блокировка тул-колла, stderr уходит модели как причина. Тесты: python3 .claude/hooks/test_db_wipe_guard.py
GUARD_HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
exec python3 "$GUARD_HOOK_DIR/db_wipe_checks.py"
