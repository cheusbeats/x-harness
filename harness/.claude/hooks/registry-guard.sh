#!/usr/bin/env bash
# PreToolUse на Edit/Write/NotebookEdit (Codex: apply_patch): индексы планирования правятся только
# через .claude/scripts/registry.sh (PLAN-145, E6). Список защищаемых файлов — `guard` в paths.conf;
# строки `guard-stage4` включатся на этапе 4 (пока registry.sh не умеет менять их формат).
#
# Запись через registry.sh идёт из Bash/python, не из Edit/Write, поэтому не блокируется;
# вручную записанную через Bash строку отсекает только `registry.sh check` по форме.
#
# exit 2 = блокировка тул-колла, stderr уходит модели как причина.

file="$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)"
[ -n "$file" ] || exit 0

if python3 "$(dirname "$0")/paths.py" guarded "$file"; then
  echo "$(basename "$file") — индекс реестра, прямая правка Edit/Write запрещена (E6)." >&2
  echo "Используй .claude/scripts/registry.sh: next-id | add | set-status <id> <статус> | show <id> | check." >&2
  exit 2
fi
exit 0
