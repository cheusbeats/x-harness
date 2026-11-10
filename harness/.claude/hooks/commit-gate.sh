#!/usr/bin/env bash
# PreToolUse на Bash: если команда — git commit, проверить ветку и прогнать Quality Gate.
# Правило CLAUDE.md: «не коммитить, если Larastan падает». Здесь оно исполняется,
# а не декларируется.
#
# Это НАСТОЯЩИЙ чокпоинт воркфлоу: branch-guard.sh висит только на Edit/Write и
# обходится правкой через Bash (sed -i, cat >, tee). Коммит обойти нечем — сюда
# сходятся все пути, как бы файл ни был изменён.
#
# Гейт висит на коммите, а не на Stop: phpstan + полный прогон тестов на каждый
# конец хода — минуты впустую, а коммит редок и это ровно та точка, где правило требует.
#
# exit 2 = блокировка тул-колла, stderr уходит модели как причина.

# Каталог вызова нужен разбору `git -C d …` / `cd d && git …` / workdir Codex (как в main-push-guard.sh).
GUARD_ORIG_PWD="$PWD"
export GUARD_ORIG_PWD
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

payload="$(cat)"
cmd="$(printf '%s' "$payload" | jq -r '.tool_input.command // empty' 2>/dev/null)"
# Из worktree хук стартует в основном чекауте, а `cd <cwd> &&` до него не доходит: база разбора — cwd команды (HF-174).
payload_cwd="$(printf '%s' "$payload" | jq -r '.cwd // empty' 2>/dev/null)"
[ -d "$payload_cwd" ] && GUARD_ORIG_PWD="$payload_cwd"

# E16: хуки не обходятся флагом. `git commit|push --no-verify` и `git commit -n` (у git это тот же
# флаг) блокируются; проверка идёт ДО определения «это коммит», потому что касается и push.
# Обход остаётся только владельцу в его собственном терминале (хук видит лишь тул-колл агента).
checks="$(dirname "$0")/commit_checks.py"
if [ -f "$checks" ]; then
  printf '%s' "$cmd" | python3 "$checks" noverify || exit 2
fi

# Репозиторий и ветка берутся из каталога, где пойдёт КОММИТ (`git -C`, `cd`), а не из проекта хука.
# «Есть ли вызов git commit» решает argv-парсер (строки-данные вроде `echo "git commit"` не в счёт).
# mode: staged — индекс уже final; dirty — команда сама меняет индекс (`git add && commit`, `commit -a`,
# `commit <пути>`), проверяем суперсет грязного дерева.
mode=staged
if [ -f "$checks" ]; then
  { read -r target; read -r mode; read -r has_commit; } < <(printf '%s' "$cmd" | python3 "$checks" inspect)
  [ "${has_commit:-1}" = "0" ] && exit 0
  [ -n "$target" ] && [ -d "$target" ] && cd "$target"
else
  # без парсера — старый regex: флаги и `-C <path>` между `git` и `commit` учтены.
  printf '%s' "$cmd" \
    | grep -qE '(^|[;&|[:space:]])git[[:space:]]+((-[^[:space:]]+|-C[[:space:]]+[^[:space:]]+)[[:space:]]+)*commit([[:space:]]|$)' \
    || exit 0
fi

# 1. Ветка. Ловим и тот случай, когда правка прошла мимо branch-guard через Bash.
# symbolic-ref, а не rev-parse --abbrev-ref: при одноимённом теге (refs/tags/main) тот даёт «heads/main».
branch="$(git symbolic-ref -q HEAD 2>/dev/null)"
if [ -n "$branch" ]; then branch="${branch#refs/heads/}"; else branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"; fi
case "$branch" in
  feature/*|hotfix/*) ;;
  *)
    echo "Коммит в ветку '$branch' заблокирован (CLAUDE.md → Git workflow)." >&2
    echo "Допустимы только feature/* и hotfix/*. Правки сохранятся: git checkout -b feature/PLAN-N-slug" >&2
    exit 2
    ;;
esac

# 2. Дешёвые проверки планирования (< 1 с) — ПЕРЕД долгим гейтом, чтобы отказ был быстрым.
#   E2/E9/E7/E8 и fail-closed по paths.conf — commit_checks.py; E4/E5 — registry.sh check.
#   E3 (токен PLAN-N/HF-N в сообщении КАЖДОГО коммита) тут НЕ делается: PreToolUse не видит
#   сообщение при heredoc/-F. Это git-хук commit-msg (PLAN-145, этап 2b).
if [ -f "$checks" ]; then
  python3 "$checks" staged "$branch" "${mode:-staged}" || exit 2
fi
registry="$CLAUDE_PROJECT_DIR/.claude/scripts/registry.sh"
if [ -x "$registry" ] && { git diff --cached --name-only; git status --porcelain | cut -c4-; } | grep -q '^planning/'; then
  # Проверка по РАБОЧЕМУ дереву; по staged-дереву её гоняет git-хук pre-commit (этап 2b).
  if ! reg_out="$("$registry" check --registry all 2>&1)"; then
    echo "registry.sh check нашёл нарушения реестров — коммит заблокирован (E4/E5):" >&2
    printf '%s\n' "$reg_out" | head -15 >&2
    exit 2
  fi
fi

# 3. Секреты в том, что собрались коммитить.
# Логика в отдельном скрипте: у неё есть самотест (`scan-secrets.sh --self-test`,
# 15 проб), потому что первая инлайн-версия ловила 1 находку из 4 и это вскрылось
# только прогоном сценариев.
scanner="$CLAUDE_PROJECT_DIR/.claude/scripts/scan-secrets.sh"
if [ -x "$scanner" ]; then
  if ! secrets="$(git diff --cached -U0 2>/dev/null | "$scanner" 2>&1)"; then
    echo "В staged-диффе похоже на секрет — коммит заблокирован." >&2
    printf '%s\n' "$secrets" | head -5 >&2
    echo "Ложное срабатывание — убери фрагмент из диффа или попроси владельца закоммитить в своём терминале." >&2
    exit 2
  fi
fi

# 4. Quality Gate в быстром режиме: Larastan + Pint + eslint + синк копий скиллов.
#
# Полный прогон тестов сюда НЕ входит осознанно. Две причины:
#  — правило CLAUDE.md требует перед коммитом именно Larastan, а не весь прогон;
#  — замер 2026-08-06: полный прогон 392 с. Шесть с половиной минут на каждый
#    коммит — это не гейт, а паралич; плюс при росте набора упрётся в timeout хука.
# Полный прогон и Dusk живут в merge-чеклисте: quality-gate.sh --merge.
gate="$CLAUDE_PROJECT_DIR/.claude/scripts/quality-gate.sh"
[ -x "$gate" ] || exit 0

# Скрипт — из чекаута хука, а не из дерева коммита; проверяет он дерево коммита (HF-174).
if output="$(CLAUDE_PROJECT_DIR="$PWD" "$gate" --fast 2>&1)"; then
  exit 0
fi

echo "Quality Gate упал — коммит заблокирован (CLAUDE.md → Git workflow)." >&2
printf '%s\n' "$output" | tail -30 >&2
exit 2
