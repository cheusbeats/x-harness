#!/usr/bin/env bash
# registry-guard.sh — PreToolUse (Edit|Write|NotebookEdit): индексы реестров планирования
# правит только .claude/scripts/registry.sh (SPEC п.5). Прямая правка через Edit/Write
# запрещена — exit 2, причина уходит модели в stderr.
#
# Без jq хук не блокирует (SPEC п.7: jq нужен только PreToolUse-хукам; его нет — fail-open).
set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0

input="$(cat 2>/dev/null)" || exit 0
[ -n "$input" ] || exit 0
file="$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)" || exit 0
[ -n "$file" ] || exit 0

# Корень проекта: git-корень, иначе CLAUDE_PROJECT_DIR/текущий каталог.
root="$(git rev-parse --show-toplevel 2>/dev/null || printf '%s' "${CLAUDE_PROJECT_DIR:-$PWD}")"
real_root="$(cd "$root" 2>/dev/null && pwd -P)" || real_root="$root"

# Абсолютный путь -> путь относительно корня. Путь может прийти через симлинк
# (на macOS /tmp -> /private/tmp), поэтому сверяем и логический, и физический корень.
normalize() { # $1 путь
  local f="$1" d basef
  case "$f" in
    "$root"/*) printf '%s' "${f#"$root"/}"; return ;;
    "$real_root"/*) printf '%s' "${f#"$real_root"/}"; return ;;
  esac
  case "$f" in
    /*)
      d="$(dirname "$f")"
      basef="$(basename "$f")"
      if [ -d "$d" ]; then
        d="$(cd "$d" 2>/dev/null && pwd -P)" || d=""
        case "$d" in
          "$real_root") printf '%s' "$basef"; return ;;
          "$real_root"/*) printf '%s' "${d#"$real_root"/}/$basef"; return ;;
        esac
      fi
      printf '%s' "$f"
      ;;
    ./*) printf '%s' "${f#./}" ;;
    *) printf '%s' "$f" ;;
  esac
}

rel="$(normalize "$file")"
dir="${rel%/*}"
base="${rel##*/}"
lower="$(printf '%s' "$base" | tr '[:upper:]' '[:lower:]')"

# Защищены только индексы. Имя сверяем без регистра: на macOS регистронезависимая
# ФС, plans.md и PLANS.md — один файл.
case "$lower" in
  roadmap.md|active_plans.md|plans.md|hotfixes.md) ;;
  *) exit 0 ;;
esac
if [ "$dir" != "planning" ]; then
  # normalize не сработал (например, путь пришёл через ещё один симлинк), но хвост
  # пути всё равно указывает на индекс planning/ — блокируем, это дешевле пропуска.
  case "$file" in
    */planning/"$base") ;;
    *) exit 0 ;;
  esac
fi

echo "$file — индекс реестра, прямая правка Edit/Write запрещена." >&2
echo "Используй .claude/scripts/registry.sh: next-id | add <RM|HF|PLAN> <id|auto> \"название\" | set-status <id> <статус> | show <id> | check." >&2
exit 2
