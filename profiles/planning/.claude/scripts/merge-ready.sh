#!/usr/bin/env bash
# merge-ready.sh <ветка> - сухой прогон merge-gate перед вопросом владельцу о мерже (SPEC §9).
#
# Ничего не мержит, маркеры владельца не захватывает и не расходует. Печатает
# READY / READY (кроме слов владельца) / NOT READY + причины. exit 0 - готово
# (слова владельца перечислены отдельно), exit 1 - есть нерешённые проблемы.
set -euo pipefail

[ $# -eq 1 ] || { echo "Использование: merge-ready.sh <ветка>" >&2; exit 2; }
cd "$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "merge-ready: не git-репозиторий" >&2; exit 2; }
exec python3 .claude/hooks/strict-checks.py --preflight "$1"
