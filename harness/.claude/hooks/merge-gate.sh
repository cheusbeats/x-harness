#!/usr/bin/env bash
# PreToolUse на Bash: мерж пускаем, только если выполнено всё из .claude/hooks/merge_checks.py:
#   T16  ссылки `git merge` резолвятся в SHA, правила путей paths.conf — по диффу, не по имени ветки;
#   гейт  зелёный полный гейт на вершине (`quality-gate.sh --merge` пишет в основной чекаут .claude/state/gates/<ветка>.merge-passed);
#   E12  ревью на вершине (`mark-reviewed.sh --by opus|codex`): деньги (money-paths.txt) — обе отметки, иначе одна;
#   E3   hotfix/* добавляет запись хотфикса, feature/PLAN-N-* — план N есть в реестре;
#   E17  номера RM/PLAN/HF уникальны на дереве результата слияния (registry.sh check);
#   E10/E11 слово владельца (owner_ok.py): маркер сверяется по SHA вершины и забирается атомарно.
#
# Правила владельца 2026-10-01: до мержа — проверить всё, но не жечь токены дважды: полное ревью один раз
# на план, исправления после него — ревью только разницы. Ревьюер денег — opus И Codex.
#
# exit 2 = блокировка тул-колла, stderr уходит модели как причина.

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

payload="$(cat)"
# дешёвый префильтр: почти все Bash-команды не про мерж
printf '%s' "$payload" | grep -qE 'merge|pull|cherry-pick|rebase|reset|update-ref|symbolic-ref|branch|push|fetch|checkout|switch|tag' || exit 0

printf '%s' "$payload" | python3 "$(dirname "$0")/merge_checks.py"
