#!/usr/bin/env bash
# planning-owner-ok.sh — маркер «слово владельца» (SPEC п.6, §9).
#
# Запускает ТОЛЬКО владелец в своём терминале. Агент этот скрипт не запускает и
# маркеры в .claude/state/planning-owner-ok/ не пишет — это блокирует
# .claude/hooks/owner-ok-guard.sh; событийный commit-gate не даёт обойти git-хуки.
#
#   planning-owner-ok.sh close-plan PLAN-N [ветка]   разрешить закрытие плана N
#   planning-owner-ok.sh rm-add     RM-N   [ветка]   разрешить новую идею RM-N
#   planning-owner-ok.sh hooks-edit <ветка>          E18: правка защищённых путей (хуки/настройки/AGENTS.md)
#   planning-owner-ok.sh merge      <ветка>          мерж этой ветки в MAIN_BRANCH
#
# Маркер: .claude/state/planning-owner-ok/<kind>-<enc(id)>@<enc(branch)>,
# строки key=value: kind, id, branch, sha (вершина ветки в момент выдачи), ttl_until, target.
# Для hooks-edit и merge id = имя ветки (в имени файла оно повторяется в id и branch).
# Маркер живёт OWNER_OK_TTL_HOURS часов и привязан к вершине ветки: новый коммит
# в ветку его аннулирует — тогда владелец выдаёт маркер заново.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=planning-lib.sh
. "$SCRIPT_DIR/planning-lib.sh"
planning_load_conf
cd "$PLANNING_ROOT" || exit 2

usage() {
  echo "Использование: planning-owner-ok.sh close-plan PLAN-N [ветка] | rm-add RM-N [ветка] | hooks-edit <ветка> | merge <ветка>" >&2
  exit 2
}

die() { echo "$*" >&2; exit 2; }

kind="${1:-}"
id=""
branch=""
sha=""

case "$kind" in
  close-plan)
    id="${2:-}"
    [ -n "$id" ] || usage
    [[ "$id" =~ ^PLAN-[0-9]+(\.[0-9]+)*$ ]] || die "Неверный id '$id': для close-plan ожидается PLAN-N."
    branch="${3:-}"
    [ -n "$branch" ] || branch="$(git symbolic-ref --short -q HEAD || true)"
    [ -n "$branch" ] || die "Не удалось определить ветку: укажи её аргументом."
    ;;
  rm-add)
    id="${2:-}"
    [ -n "$id" ] || usage
    [[ "$id" =~ ^RM-[0-9]+$ ]] || die "Неверный id '$id': для rm-add ожидается RM-N."
    branch="${3:-}"
    [ -n "$branch" ] || branch="$(git symbolic-ref --short -q HEAD || true)"
    [ -n "$branch" ] || die "Не удалось определить ветку: укажи её аргументом."
    ;;
  hooks-edit|merge)
    branch="${2:-}"
    [ -n "$branch" ] || usage
    git check-ref-format --branch "$branch" >/dev/null 2>&1 || die "Неверное имя ветки '$branch'."
    id="$branch"
    ;;
  *) usage ;;
esac

sha="$(git rev-parse --verify --quiet "refs/heads/$branch^{commit}" || true)"
[ -n "$sha" ] || die "Ветка '$branch' не найдена в этом репозитории (нужен хотя бы один коммит в ней)."

# Имя маркера однозначно: % / _ @ кодируются, поэтому feature/a/b и feature/a_b не сталкиваются.
enc() {
  printf '%s' "$1" | sed -e 's/%/%25/g' -e 's#/#%2F#g' -e 's/_/%5F/g' -e 's/@/%40/g'
}

dir=".claude/state/planning-owner-ok"
mkdir -p "$dir"
ttl_until=$(( $(date +%s) + OWNER_OK_TTL_HOURS * 3600 ))
file="$dir/${kind}-$(enc "$id")@$(enc "$branch")"
printf 'kind=%s\nid=%s\nbranch=%s\nsha=%s\nttl_until=%s\ntarget=%s\n' \
  "$kind" "$id" "$branch" "$sha" "$ttl_until" "$MAIN_BRANCH" > "$file"

case "$kind" in
  close-plan) echo "Разрешение выдано: закрытие плана $id на ветке '$branch' (вершина ${sha:0:7}), действует ${OWNER_OK_TTL_HOURS} ч." ;;
  rm-add)     echo "Разрешение выдано: новая идея $id на ветке '$branch' (вершина ${sha:0:7}), действует ${OWNER_OK_TTL_HOURS} ч." ;;
  hooks-edit) echo "Разрешение выдано: правка защищённых путей (E18) на ветке '$branch' (вершина ${sha:0:7}), действует ${OWNER_OK_TTL_HOURS} ч." ;;
  merge)      echo "Разрешение выдано: мерж ветки '$branch' в '$MAIN_BRANCH' (вершина ${sha:0:7}), действует ${OWNER_OK_TTL_HOURS} ч." ;;
esac
echo "Маркер: $file"
echo "Целевая ветка: $MAIN_BRANCH. Новый коммит в ветку после выдачи отменяет разрешение — выдай заново."
