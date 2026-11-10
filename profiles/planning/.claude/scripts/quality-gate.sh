#!/usr/bin/env bash
# quality-gate.sh - портативный Quality Gate планировочного профиля (SPEC §9).
#
#   .claude/scripts/quality-gate.sh --fast    выполнить GATE_FAST перед коммитом
#   .claude/scripts/quality-gate.sh --merge   выполнить GATE_MERGE перед мержем и, при
#                                             чистом дереве, записать отметку
#                                             .claude/state/gates/<ветка>.merge-passed = HEAD
#
# Пустые GATE_FAST и GATE_MERGE при STRICT=on блокируют проверку (это не Laravel Quality Gate:
# профиль только исполняет команды проекта). exit 1 - команда гейта упала.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=planning-lib.sh
. "$SCRIPT_DIR/planning-lib.sh"
planning_load_conf
cd "$PLANNING_ROOT" || exit 1

[ $# -le 1 ] || { echo "Использование: quality-gate.sh --fast|--merge" >&2; exit 2; }
MODE="${1:-}"
case "$MODE" in
  --fast|--merge) ;;
  *) echo "Использование: quality-gate.sh --fast|--merge" >&2; exit 2 ;;
esac

record_stamp() {
  local branch sha gate_hash
  branch="$(git symbolic-ref --short -q HEAD || true)"
  if [ -z "$branch" ] || [ "$branch" = "HEAD" ]; then
    echo "[gate] отметка полного гейта НЕ записана: отсоединённый HEAD"
    return 0
  fi
  if git diff --quiet HEAD -- 2>/dev/null; then
    mkdir -p .claude/state/gates || return 1
    sha="$(git rev-parse HEAD)" || return 1
    gate_hash="$(python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest())' "$GATE_CMD")" || return 1
    printf '%s\n%s\n' "$sha" "$gate_hash" > ".claude/state/gates/$(printf '%s' "$branch" | tr '/' '_').merge-passed" || return 1
    echo "[gate] отметка полного гейта: $branch @ ${sha:0:7}"
  else
    echo "[gate] отметка полного гейта НЕ записана: есть незакоммиченные изменения"
  fi
}

if [ "$MODE" = "--fast" ]; then
  GATE_CMD="${GATE_FAST:-}"
  LABEL="GATE_FAST"
else
  GATE_CMD="${GATE_MERGE:-}"
  LABEL="GATE_MERGE"
  # Повторная проверка отменяет прошлый допуск, даже если команда теперь упадёт.
  branch="$(git symbolic-ref --short -q HEAD || true)"
  if [ -n "$branch" ]; then
    rm -f ".claude/state/gates/$(printf '%s' "$branch" | tr '/' '_').merge-passed" || exit 1
  fi
fi

if [ -z "${GATE_CMD//[[:space:]]/}" ]; then
  if planning_strict_on; then
    echo "[gate] $LABEL не задан: проверка не выполнена, отметка не записана" >&2
    exit 1
  fi
  echo "[gate] $LABEL не задан в .claude/planning.conf - шаг пропущен"
  exit 0
fi

echo "[gate] $LABEL: $GATE_CMD"
if ! bash -c "$GATE_CMD"; then
  echo "[gate] ПАДЕНИЕ: $LABEL - проверка не прошла" >&2
  exit 1
fi
echo "[gate] $LABEL зелёный"
if [ "$MODE" = "--merge" ]; then
  record_stamp || exit 1
fi
exit 0
