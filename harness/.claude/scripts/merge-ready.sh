#!/usr/bin/env bash
# merge-ready.sh <ветка> — сухой прогон merge-gate перед вопросом владельцу о мерже (PLAN-145). Ничего не мержит и не
# расходует маркеры владельца. Печатает READY (всё, кроме слов владельца, пройдено) либо NOT READY + список недостающего
# (гейт, ревью, отставание от main, грязное дерево, слова владельца с точной командой owner-ok.sh).
# Правило: владельца спрашивают о мерже ТОЛЬКО когда вывод — READY; гейты и ревью после его ответа не гоняют.
set -euo pipefail
[ $# -eq 1 ] || { echo "usage: merge-ready.sh <ветка>" >&2; exit 2; }
cd "$(git rev-parse --show-toplevel)"
exec python3 .claude/hooks/merge_checks.py --preflight "$1"
