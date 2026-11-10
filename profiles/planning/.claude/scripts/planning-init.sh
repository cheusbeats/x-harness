#!/usr/bin/env bash
# planning-init.sh — идемпотентно создаёт реестры и каталоги planning/ (SPEC п.5).
#
# Создаёт недостающие индексы ROADMAP.md / ACTIVE_PLANS.md / PLANS.md / HOTFIXES.md
# с шапками таблиц, которые понимает .claude/scripts/registry.sh, каталоги
# roadmap/ plans/ plans/closed/ hotfixes/ и .gitkeep в пустых. Существующее
# НЕ перезаписывает. В конце — registry.sh check по реестрам.
#
# Каталог plans/closed/ важен: пока его нет, registry.sh check молча пропускает PLAN.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=planning-lib.sh
. "$SCRIPT_DIR/planning-lib.sh"
planning_load_conf
cd "$PLANNING_ROOT"

created=0
kept=0

make_dir() { # $1 каталог
  mkdir -p "$1"
  # .gitkeep только в пустом каталоге: git не хранит пустые.
  if ! find "$1" -mindepth 1 -maxdepth 1 -type f -print -quit | grep -q .; then
    : > "$1/.gitkeep"
  fi
}

write_index() { # $1 путь, остальное — содержимое (строки)
  local path="$1"; shift
  if [ -e "$path" ]; then
    echo "  сохранено (уже есть): $path"
    kept=$((kept + 1))
    return 0
  fi
  printf '%s\n' "$@" > "$path"
  echo "  создан: $path"
  created=$((created + 1))
}

echo "planning-init: $PLANNING_ROOT"

for dir in planning/roadmap planning/plans planning/plans/closed planning/hotfixes; do
  make_dir "$dir"
done

write_index planning/ROADMAP.md \
  "# RM — реестр идей" \
  "" \
  "Идеи «потом». Тела — roadmap/RM-N-*.md; строка индекса добавляется только" \
  "через .claude/scripts/registry.sh add RM ... (новая идея — при маркере владельца" \
  ".claude/scripts/planning-owner-ok.sh rm-add RM-N)." \
  "" \
  "| RM | Название | Статус | Дата | Триггер / → PLAN-N |" \
  "|---|---|---|---|---|"

write_index planning/ACTIVE_PLANS.md \
  "# Планы в работе — реестр" \
  "" \
  "Активные планы. Тела — plans/PLAN-N-*.md; при закрытии строка уходит в PLANS.md," \
  "а запись о закрытии — plans/closed/PLAN-N.md. Правка строки — только" \
  ".claude/scripts/registry.sh (set-status и т.п.)." \
  "" \
  "| PLAN | Название | Статус | Дата | Влит-в | Автор |" \
  "|---|---|---|---|---|---|"

write_index planning/PLANS.md \
  "# Закрытые планы — реестр" \
  "" \
  "Закрытые и аннулированные планы. Тела — plans/closed/PLAN-N.md (не переписывать)." \
  "Активные — ACTIVE_PLANS.md. Правка строки — только .claude/scripts/registry.sh." \
  "" \
  "| PLAN | Название | Статус | Дата | Влит-в | Автор |" \
  "|---|---|---|---|---|---|"

write_index planning/HOTFIXES.md \
  "# Хотфиксы — реестр" \
  "" \
  "Правки, для которых план избыточен. Тела — hotfixes/HF-N-*.md; строка индекса" \
  "добавляется только через .claude/scripts/registry.sh add HF ..." \
  "" \
  "| HF | Название | Статус | Дата | Влит-в | Автор |" \
  "|---|---|---|---|---|---|"

echo "planning-init: создано файлов $created, уже было $kept"

registry="$PLANNING_ROOT/.claude/scripts/registry.sh"
if [ ! -f "$registry" ]; then
  echo "planning-init: нет .claude/scripts/registry.sh — проверка реестров пропущена (установи профиль целиком)" >&2
  exit 0
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "planning-init: python3 не найден — проверка реестров пропущена" >&2
  exit 0
fi
if bash "$registry" check --registry all --root "$PLANNING_ROOT"; then
  echo "planning-init: реестры чистые (registry.sh check)"
else
  echo "planning-init: registry.sh check нашёл нарушения (см. выше); правь индексы через registry.sh" >&2
  exit 1
fi
