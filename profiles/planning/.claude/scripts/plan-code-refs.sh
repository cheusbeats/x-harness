#!/usr/bin/env bash
# plan-code-refs.sh — сверка ССЫЛОК ВНУТРИ плана с кодом по CODE_ROOTS (портативная версия).
#
# Зачем отдельно от plans-drift.sh: drift сверяет индекс с гитом («план числится
# не начатым, а код влит»), но не заглядывает внутрь документа. А гниёт как раз
# содержимое: план утверждает «вызывается X», а вызова нет.
#
# Проверяет ровно две однозначные вещи, чтобы не шуметь:
#   1. пути файлов в обратных кавычках — файл существует;
#   2. ссылки «Имя::член» — имя члена встречается в коде CODE_ROOTS.
#
# ЧЕГО НЕ УМЕЕТ (на это нельзя полагаться): проверять ИСПОЛЬЗОВАНИЕ — сущность
# существует, но производственного вызова нет; не понимает синтаксис языков и
# ищет текст; при пустом CODE_ROOTS проверка членов выключена.
# Ненайденное — НЕ ошибка сама по себе: у открытого плана это будущий код.
# Смысл появляется ПЕРЕД ЗАКРЫТИЕМ плана: тогда список обязан быть пустым.
# Признать расхождение можно в разделе «Поправка по факту реализации».
#
# Запуск: .claude/scripts/plan-code-refs.sh planning/plans/PLAN-N-*.md
# Информационный скрипт: exit 0 всегда (exit 2 — только на неверный вызов).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=planning-lib.sh
. "$SCRIPT_DIR/planning-lib.sh"
planning_load_conf
cd "$PLANNING_ROOT" || exit 1

BT="$(printf '\x60')"   # обратная кавычка: в исходнике её не держим

[ $# -eq 0 ] && { echo "нужен путь к плану: $0 planning/plans/PLAN-N-*.md" >&2; exit 2; }

roots=()
while IFS= read -r r; do roots+=("$r"); done < <(planning_code_roots)

# Признано ли расхождение в разделе «Поправка по факту реализации»? Закрытый план
# не переписываем, но расхождение можно назвать.
acknowledged() { # $1 план, $2 имя
  local plan="$1" name="$2" short
  short="${name##*/}"
  short="${short##*\\}"
  awk '/^## Поправка по факту реализации/{f=1} f' "$plan" 2>/dev/null | grep -qF -e "$name" -e "$short"
}

missing=0

for plan in "$@"; do
  [ -f "$plan" ] || { echo "нет файла: $plan" >&2; exit 2; }
  echo "── $plan"
  before=$missing

  # 1. Пути файлов в обратных кавычках (только с каталогом и известным расширением).
  while IFS= read -r ref; do
    [ -n "$ref" ] || continue
    case "$ref" in
      */*) ;;
      *) continue ;;
    esac
    ext="${ref##*.}"
    case "$ext" in
      php|py|js|mjs|cjs|ts|tsx|jsx|vue|svelte|rb|go|rs|java|kt|kts|cs|swift|c|h|cc|cpp|hpp|sh|bash|zsh|ps1|sql|lua|pl|ex|exs|clj|scala|dart|json|yml|yaml|toml|ini|cfg|conf|md|txt|xml|html|css|scss|sass|less) ;;
      *) continue ;;
    esac
    [ -e "$ref" ] && continue
    found=0
    if [ ${#roots[@]} -gt 0 ]; then
      for r in "${roots[@]}"; do
        [ -d "$r" ] || continue
        if [ -n "$(find "$r" -path "*/$ref" -type f -print -quit 2>/dev/null)" ]; then
          found=1
          break
        fi
      done
    fi
    if [ "$found" -eq 0 ]; then
      acknowledged "$plan" "$ref" || { echo "  ✗ файла нет: $ref"; missing=$((missing + 1)); }
    fi
  done < <(grep -oE "$BT[A-Za-z0-9_./@+%-]+$BT" "$plan" 2>/dev/null | tr -d "$BT" | sort -u)

  # 2. Ссылки «Имя::член» — ищем имя члена текстом в CODE_ROOTS.
  if [ ${#roots[@]} -eq 0 ]; then
    echo "  (CODE_ROOTS пуст — ссылки «Имя::член» не проверялись: не умеем без корней кода)"
  else
    while IFS= read -r ref; do
      [ -n "$ref" ] || continue
      member="${ref##*::}"
      case "$member" in
        new|init|main|__init__|constructor|toString|to_s|create|update|delete|save|find|get|set|run|call|apply|equals|hashCode) continue ;;
      esac
      hit=0
      for r in "${roots[@]}"; do
        [ -d "$r" ] || continue
        if grep -rqI -E "(^|[^A-Za-z0-9_])${member}([^A-Za-z0-9_]|\$)" "$r" 2>/dev/null; then
          hit=1
          break
        fi
      done
      if [ "$hit" -eq 0 ]; then
        acknowledged "$plan" "$ref" || { echo "  ✗ члена нет в коде: $ref"; missing=$((missing + 1)); }
      fi
    done < <(grep -oE "$BT[A-Za-z0-9_.]+::[A-Za-z_][A-Za-z0-9_]*$BT" "$plan" 2>/dev/null | tr -d "$BT" | sort -u)
  fi

  if [ "$missing" -eq "$before" ]; then
    echo "  ✓ ссылки плана резолвятся"
  fi
done

echo
if [ "$missing" -eq 0 ]; then
  echo "plan-code-refs: все ссылки найдены (проверка существования, не использования)."
else
  echo "plan-code-refs: не найдено ссылок: $missing. У ОТКРЫТОГО плана это, вероятно, будущий код — норма;"
  echo "перед закрытием плана список обязан быть пустым (признанные расхождения — в разделе «Поправка по факту реализации»)."
fi
echo "Не умеет: проверять использование сущностей и понимать синтаксис языков — только «существует ли»."
exit 0
