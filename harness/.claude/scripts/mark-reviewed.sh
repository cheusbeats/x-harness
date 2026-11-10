#!/usr/bin/env bash
# Отметки ревью для merge-gate.sh. Второй пропуск (полный гейт) пишет сам
# `.claude/scripts/quality-gate.sh --merge` при зелёном прогоне на вершине ветки.
#
#   mark-reviewed.sh --full  --by opus|codex <branch> "итог"   # ПОЛНОЕ ревью итоговой ветки
#   mark-reviewed.sh --delta --by opus|codex <branch> "итог"   # ревью ТОЛЬКО правок после полного ревью
#   mark-reviewed.sh --full --by codex --at <sha> <branch> "итог"  # полное ревью шло на более раннем коммите
#
# E12 (PLAN-145): отметки независимы по ревьюеру — <ветка>.full.<by> / .delta.<by>. Деньги (money-paths.txt)
# требуют ОБЕ (opus и codex), остальное — хотя бы одну. --by обязателен: отметка пишет сам ревьюер.
#
# Экономия токенов (решение владельца 2026-10-01): полное ревью — ОДИН раз на план.
#   --full  = весь дифф ветки против main + стыки с остальным проектом (потребители изменённого
#             общего кода) + сверка с планом; без БЛОКЕРов.
#   --delta = правки, сделанные ПОСЛЕ полного ревью (`git diff <full-sha>..<branch>`) + потребители
#             изменённых в них символов (blast-radius.sh). Ставится только поверх действующей --full.
# Ревьюер и для --full, и для --delta — ВСЕГДА opus (deep-reasoner). DeepSeek-воркер — только
# ПАРАЛЛЕЛЬНО как второе мнение, никогда вместо opus (решение владельца 2026-10-01).
# Новый коммит после --delta — снова --delta (от той же --full базы), полное ревью не повторяем.
set -euo pipefail

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"

mode="${1:-}"
case "$mode" in
  --full|--delta) shift ;;
  *)
    echo "Использование: mark-reviewed.sh --full|--delta --by opus|codex <branch> [итог]" >&2
    echo "  --full  — полное ревью итоговой ветки (весь дифф + стыки с проектом + план)" >&2
    echo "  --delta — ревью правок после полного ревью (поверх действующей --full отметки)" >&2
    exit 1
    ;;
esac

by=""
if [ "${1:-}" = "--by" ]; then by="${2:-}"; shift 2; fi
case "$by" in
  opus|codex) ;;
  *) echo "Нужно --by opus|codex (кто провёл ревью) сразу после --full/--delta." >&2; exit 1 ;;
esac

at=""
if [ "${1:-}" = "--at" ]; then at="${2:?--at <коммит>}"; shift 2; fi

branch="${1:?Укажи ветку}"
summary="${2:-}"

# --at <коммит>: ревью шло на более раннем коммите ветки (вершина ушла вперёд служебными
# коммитами) — отметка ставится на него, а разницу до вершины закрывает --delta.
ref="${at:-$branch}"
if [ -n "$at" ] && ! git merge-base --is-ancestor "$at" "$branch"; then
  echo "Коммит $at не принадлежит ветке $branch." >&2; exit 1
fi
sha="$(git rev-parse --verify --quiet "$ref^{commit}")" || {
  echo "Ветка '$branch' не найдена." >&2
  exit 1
}

# Общая на репозиторий: merge-gate читает отметки из основного чекаута, откуда бы ни шло ревью (HF-177).
common="$(git rev-parse --path-format=absolute --git-common-dir)"
dir="$(dirname "$common")/.claude/state/reviews"
mkdir -p "$dir"
key="$(printf '%s' "$branch" | tr '/' '_')"
now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [ "$mode" = "--full" ]; then
  printf '%s\n%s\n%s\n' "$sha" "$now" "$summary" > "$dir/$key.full.$by"
  rm -f "$dir/$key.delta.$by"
  echo "Полное ревью ($by) отмечено: $branch @ ${sha:0:7}"
  exit 0
fi

full_file="$dir/$key.full.$by"
[ -f "$full_file" ] || { echo "Нет полной отметки для '$branch' — сначала полное ревью (--full)." >&2; exit 1; }
full_sha="$(head -n1 "$full_file")"
git merge-base --is-ancestor "$full_sha" "$sha" || {
  echo "Полная отметка ${full_sha:0:7} не предок вершины ${sha:0:7} (история переписана) — нужно полное ревью." >&2
  exit 1
}
printf '%s\n%s\n%s\n%s\n' "$sha" "$full_sha" "$now" "$summary" > "$dir/$key.delta.$by"
echo "Ревью правок ($by) отмечено: $branch ${full_sha:0:7}..${sha:0:7}"
