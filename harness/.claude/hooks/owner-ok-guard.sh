#!/usr/bin/env bash
# PreToolUse на Bash (PLAN-145, E10/E11, I7): агент не выдаёт слово владельца сам — не запускает
# owner-ok.sh и не пишет в .claude/state/owner-ok. Владелец работает в своём терминале, этот хук его не видит.
# exit 2 = блокировка тул-колла, stderr уходит модели как причина.
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
jq -r '.tool_input.command // empty' 2>/dev/null | python3 "$(dirname "$0")/owner_ok.py" guard
