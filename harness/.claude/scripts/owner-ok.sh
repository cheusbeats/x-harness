#!/usr/bin/env bash
# Слово владельца (PLAN-145, E10/E11/E18): владелец выдаёт разрешение в СВОЁМ терминале.
#
#   owner-ok.sh close-plan PLAN-N [ветка]   закрыть/аннулировать план N (E10)
#   owner-ok.sh rm-add     RM-N   [ветка]   добавить идею в roadmap (E11)
#   owner-ok.sh hooks-edit <ветка> [ветка]  править защищённые хуки (E18, этап 3c)
#
# Ветка — аргумент или текущая. Маркер: .claude/state/owner-ok/<вид>-<id>@<ветка с / → _>,
# строки key=value (kind, id, branch, sha вершины ветки на момент выдачи, target=main, issued epoch).
# Правила приёма (срок 24 ч, одноразовость на merge-gate) — .claude/hooks/owner_ok.py.
# Агент этот скрипт не запускает: маркер — слово владельца.
set -uo pipefail

cd "$(dirname "$0")/../.." || exit 2

usage() { echo "Использование: owner-ok.sh close-plan PLAN-N [ветка] | rm-add RM-N [ветка] | hooks-edit <ветка> [ветка]" >&2; exit 2; }

kind="${1:-}"; id="${2:-}"; branch="${3:-}"
[ -n "$id" ] || usage
case "$kind" in
  close-plan) [[ "$id" =~ ^PLAN-[0-9]+(\.[0-9]+)*$ ]] || { echo "Неверный id '$id' (ожидается PLAN-N)." >&2; exit 2; } ;;
  rm-add)     [[ "$id" =~ ^RM-[0-9]+$ ]] || { echo "Неверный id '$id' (ожидается RM-N)." >&2; exit 2; } ;;
  hooks-edit) git check-ref-format --branch "$id" >/dev/null 2>&1 || { echo "Неверный id '$id' (ожидается имя ветки)." >&2; exit 2; } ;;
  *) usage ;;
esac

[ -n "$branch" ] || branch="$(git symbolic-ref --short -q HEAD || true)"
sha="$(git rev-parse --verify --quiet "refs/heads/$branch^{commit}" || true)"
[ -n "$branch" ] && [ -n "$sha" ] || { echo "Ветка '$branch' не найдена." >&2; exit 2; }

dir=".claude/state/owner-ok"
mkdir -p "$dir"
# имя однозначно (owner_ok.py enc): % / _ @ кодируются, ветки feature/a/b и feature/a_b не сталкиваются
enc() { printf '%s' "$1" | sed -e 's/%/%25/g' -e 's#/#%2F#g' -e 's/_/%5F/g' -e 's/@/%40/g'; }
file="$dir/${kind}-$(enc "$id")@$(enc "$branch")"
printf 'kind=%s\nid=%s\nbranch=%s\nsha=%s\ntarget=main\nissued=%s\n' "$kind" "$id" "$branch" "$sha" "$(date +%s)" > "$file"
echo "Разрешение выдано: $kind $id на ветке $branch (вершина ${sha:0:7}), действует 24 ч."
echo "Новый коммит в ветку после выдачи отменяет разрешение для мержа — тогда выдай заново."
