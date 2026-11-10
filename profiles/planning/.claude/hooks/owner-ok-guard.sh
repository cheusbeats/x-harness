#!/usr/bin/env bash
# owner-ok-guard.sh — PreToolUse (Bash): слово владельца выдаёт ТОЛЬКО владелец в своём
# терминале. Агент не запускает planning-owner-ok.sh и не пишет маркеры в
# .claude/state/planning-owner-ok (SPEC п.6): exit 2, причина уходит модели в stderr.
#
# Без jq хук не блокирует (SPEC п.7: jq нужен только PreToolUse-хукам; его нет — fail-open).
set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0

input="$(cat 2>/dev/null)" || exit 0
[ -n "$input" ] || exit 0
# Команда, разрезанная на сегменты по ; & | и переводам строк: каждый сегмент проверяем отдельно,
# чтобы чтение маркеров (grep/cat/git) не блокировалось.
segments="$(printf '%s' "$input" | jq -r '.tool_input.command // empty | gsub("[;&|\\n]"; "\n")' 2>/dev/null)" || exit 0
[ -n "$segments" ] || exit 0

owner_re='planning-owner-ok(\.sh)?|\.claude/state/planning-owner-ok'
read_only=" grep rg cat ls head tail wc git stat diff find file sed awk "

blocked=0
while IFS= read -r seg; do
  [ -n "$seg" ] || continue
  printf '%s' "$seg" | grep -Eq "$owner_re" || continue
  first="$(printf '%s' "$seg" | awk '{print $1}')"
  case "$read_only" in
    *" $first "*)
      # Чтение разрешено, запись/перенаправление — нет.
      case "$seg" in *'>'*) blocked=1 ;; esac
      ;;
    *) blocked=1 ;;
  esac
done <<EOF
$segments
EOF

if [ "$blocked" -eq 1 ]; then
  echo "Слово владельца выдаёт только владелец в своём терминале: .claude/scripts/planning-owner-ok.sh." >&2
  echo "Агенту запрещено запускать planning-owner-ok.sh и писать в .claude/state/planning-owner-ok." >&2
  exit 2
fi
exit 0
