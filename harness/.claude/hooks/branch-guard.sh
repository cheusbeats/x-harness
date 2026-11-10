#!/usr/bin/env bash
# PreToolUse на Edit/Write: не давать править файлы, сидя в main или в ветке
# с самодельным префиксом. Правило — CLAUDE.md → «Git workflow»:
# база только main, ветки feature/* и hotfix/*.
#
# Ветку определяем по КАТАЛОГУ РЕДАКТИРУЕМОГО ФАЙЛА, а не по $CLAUDE_PROJECT_DIR:
# в git worktree (.claude/worktrees/*) у файла своя ветка, а CLAUDE_PROJECT_DIR
# смотрит на основной чекаут — проверка ветки корня там дала бы ложный вердикт.
#
# Это ранняя сигнализация, а не единственный заслон: правку можно внести и через
# Bash (sed -i, cat >, tee), куда этот хук не подключён. Настоящий чокпоинт —
# проверка ветки внутри commit-gate.sh перед коммитом.
#
# exit 2 = блокировка тул-колла, stderr уходит модели как причина.

payload="$(cat)"
file="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty' 2>/dev/null)"

if [ -n "$file" ]; then
  dir="$(dirname "$file")"
else
  dir="${CLAUDE_PROJECT_DIR:-.}"
fi
[ -d "$dir" ] || dir="${CLAUDE_PROJECT_DIR:-.}"

cd "$dir" 2>/dev/null || exit 0

# symbolic-ref, а не rev-parse --abbrev-ref: при одноимённом теге (refs/tags/main) тот даёт «heads/main».
branch="$(git symbolic-ref -q HEAD 2>/dev/null)"
if [ -n "$branch" ]; then branch="${branch#refs/heads/}"; else branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" || exit 0; fi

# E18: защищённые пути (хуки, настройки, инструкции) правятся только под маркером владельца hooks-edit
case "$branch" in
  feature/*|hotfix/*)
    if [ -n "$file" ]; then
      python3 "$(dirname "$0")/owner_ok.py" edit-guard "$file" "$branch" || exit 2
    fi
    ;;
esac

case "$branch" in
  feature/PLAN-[0-9]*|hotfix/*|HEAD)
    exit 0
    ;;
  feature/*)
    # E2: ветка без PLAN-токена (например feature/RM-9-x) может править planning/, но не код.
    # Путь классифицирует paths.py по paths.conf; неклассифицированное тут пропускаем —
    # fail-closed срабатывает на коммите (commit-gate).
    paths="$(dirname "$0")/paths.py"
    if [ -n "$file" ] && [ -f "$paths" ]; then
      top="$(git rev-parse --show-toplevel 2>/dev/null)"
      kind="$(python3 "$paths" classify --root "$top" "$file" 2>/dev/null | cut -f1)"
      if [ "$kind" = "code" ]; then
        echo "Ветка '$branch' без PLAN-токена: код правится только на feature/PLAN-<N>-* или hotfix/* (E2)." >&2
        echo "Файл $file — код. Допустимы только planning/ (RM-N права на код не даёт)." >&2
        exit 2
      fi
    fi
    exit 0
    ;;
  main)
    echo "Ветка main. Нетривиальные правки запрещены напрямую в main (CLAUDE.md → Git workflow)." >&2
    echo "Создай ветку: git checkout -b feature/PLAN-N-slug (N = максимум в planning/plans/ + 1) или hotfix/slug." >&2
    exit 2
    ;;
  *)
    echo "Ветка '$branch' не по конвенции. Допустимы только feature/* и hotfix/*." >&2
    echo "Переименуй: git branch -m feature/PLAN-N-slug" >&2
    exit 2
    ;;
esac
