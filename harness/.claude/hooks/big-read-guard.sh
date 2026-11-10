#!/usr/bin/env bash
# PreToolUse на Read и Bash(cat/head/tail/less/more): полный read файла
# длиннее порога — блок, редирект на локальный worker deepseek-worker
# (mcp__local-workers__run_worker), а если тот недоступен — на субагента с
# model:haiku. В основной контекст попадает выжимка, не сырой файл.
#
# Портировано из shunt (spotify/portal-ai-plugins), backend заменён:
# там AiKA (Portal CLI, недоступен без Spotify-доступа), тут Agent tool
# с параметром model:"haiku" — то же самое дешевле-модель-делегирование,
# без внешней зависимости.
#
# Targeted read (offset/limit, cat в пайпе/редиректе) пропускаем всегда —
# модель уже знает, что ей нужно, экономить нечего.
#
# exit 2 = блокировка тул-колла, stderr уходит модели как причина.

MIN_LINES="${BIG_READ_MIN_LINES:-300}"
case "$MIN_LINES" in ''|*[!0-9]*) MIN_LINES=300 ;; esac

# E14: порог и по БАЙТАМ — после сжатия индексов строк мало, а КБ много. 40 КБ ≈ 11k токенов.
MAX_BYTES="${BIG_READ_MAX_BYTES:-40960}"
case "$MAX_BYTES" in ''|*[!0-9]*) MAX_BYTES=40960 ;; esac

payload="$(cat)"
tool="$(printf '%s' "$payload" | jq -r '.tool_name // empty' 2>/dev/null)"

block() {
  echo "Файл $1 строк, $2 байт (порог: $MIN_LINES строк или $MAX_BYTES байт)." >&2
  echo "Не читай целиком. Реестр — не читай тела: .claude/scripts/registry.sh show <id> (RM-N, PLAN-N, HF-N)." >&2
  echo "Иначе по порядку:" >&2
  echo "1) mcp__local-workers__run_worker с worker_id \"deepseek-worker\" — первый выбор, узкий bounded-вопрос к файлу." >&2
  echo "   Воркер отсутствует в mcp__local-workers__list_workers или сервер недоступен — переходи к п.2." >&2
  echo "2) Agent(subagent_type: general-purpose, model: \"haiku\") — запасной, если воркера нет или вопрос шире одного файла." >&2
  echo "3) Read с offset/limit на нужный диапазон, если знаешь где искать." >&2
  exit 2
}

# Большой ли файл: строк > порога ИЛИ байт > порога → block.
too_big() {
  local lines bytes
  # Не читаются людьми и не лечатся диапазоном: lock-файлы, зависимости, минифицированное, бинарное.
  case "$1" in
    */composer.lock|*/package-lock.json|composer.lock|package-lock.json) return 0 ;;
    */vendor/*|*/node_modules/*|vendor/*|node_modules/*) return 0 ;;
    *.min.js|*.min.css) return 0 ;;
    *.png|*.jpg|*.jpeg|*.gif|*.webp|*.ico|*.woff|*.woff2|*.pdf|*.zip) return 0 ;;
  esac
  lines="$(wc -l < "$1" 2>/dev/null | tr -d ' ')"
  bytes="$(wc -c < "$1" 2>/dev/null | tr -d ' ')"
  if { [ -n "$lines" ] && [ "$lines" -gt "$MIN_LINES" ]; } || { [ -n "$bytes" ] && [ "$bytes" -gt "$MAX_BYTES" ]; }; then
    block "$lines" "$bytes"
  fi
}

if [ "$tool" = "Read" ]; then
  file_path="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty' 2>/dev/null)"
  offset="$(printf '%s' "$payload" | jq -r '.tool_input.offset // empty' 2>/dev/null)"
  limit="$(printf '%s' "$payload" | jq -r '.tool_input.limit // empty' 2>/dev/null)"
  { [ -n "$offset" ] || [ -n "$limit" ]; } && exit 0
  [ -n "$file_path" ] && [ -f "$file_path" ] || exit 0
  too_big "$file_path"
  exit 0
fi

if [ "$tool" = "Bash" ]; then
  command="$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null)"
  [ -z "$command" ] && exit 0
  echo "$command" | grep -qE '\||>' && exit 0
  echo "$command" | grep -qE '^(cat|head|tail|less|more)[[:space:]]' || exit 0

  file_path=""
  args="$(printf '%s' "$command" | sed -E 's/^(cat|head|tail|less|more) +//')"
  for arg in $args; do
    case "$arg" in
      -*) continue ;;
      *) file_path="$(printf '%s' "$arg" | tr -d "\"'")"; break ;;
    esac
  done
  [ -n "$file_path" ] && [ -f "$file_path" ] || exit 0
  too_big "$file_path"
  exit 0
fi

exit 0
