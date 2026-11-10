#!/usr/bin/env bash
# tests/acceptance-planning.sh — приёмка планировочного профиля x-harness.
#
# Сценарий — по profiles/planning/SPEC.md (разделы 3 и 8): ./install.sh --profile planning
# в чистый НЕ-Laravel git-репозиторий, затем состав установки, реестры, git-хуки,
# owner-ok, закрытие плана, drift, verify и повторная установка.
#
# Запуск: bash tests/acceptance-planning.sh   (из любого каталога)
# Все прогоны — во временном каталоге: HOME и TMPDIR подменяются, чтобы не задеть
# настоящие настройки; сеть не нужна. По умолчанию временный каталог удаляется,
# XH_ACCEPT_KEEP=1 — оставить его для разбора упавшего прогона.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/xh-accept-planning.XXXXXX")"
PROJECT="$TMP/project"
LOGS="$TMP/logs"
export HOME="$TMP/home"
export TMPDIR="$TMP/tmp"
mkdir -p "$HOME" "$TMPDIR" "$LOGS" "$PROJECT"
cleanup() {
  if [ "${XH_ACCEPT_KEEP:-0}" = 1 ]; then
    printf 'acceptance-planning: временный каталог сохранён: %s\n' "$TMP" >&2
  else
    rm -rf "$TMP"
  fi
}
trap cleanup EXIT

# Изоляция от окружения вызывающего: не наследуем чужие git-переменные и настройки.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_CEILING_DIRECTORIES 2>/dev/null || true
export GIT_TERMINAL_PROMPT=0
export GIT_CONFIG_NOSYSTEM=1

gitp() { git -C "$PROJECT" -c user.name=acceptance -c user.email=acceptance@example.invalid -c commit.gpgsign=false "$@"; }
in_project() { ( cd "$PROJECT" && "$@" ); }

STEP=0
TITLE=""
LAST_LOG=""

begin_step() { STEP="$1"; TITLE="$2"; printf '%d/8 %s\n' "$STEP" "$TITLE"; }
step_ok()    { printf '%d/8 %s OK\n' "$STEP" "$TITLE"; }
die() {
  printf 'FAIL: шаг %d/8 (%s): %s\n' "$STEP" "$TITLE" "$*" >&2
  if [ -n "$LAST_LOG" ] && [ -f "$LAST_LOG" ]; then
    printf -- '--- последние 30 строк лога: %s ---\n' "$LAST_LOG" >&2
    tail -n 30 "$LAST_LOG" >&2 || true
  fi
  printf 'подсказка: повтори с XH_ACCEPT_KEEP=1, чтобы сохранить %s\n' "$TMP" >&2
  exit 1
}

expect_ok() { # описание лог команда...
  local desc="$1" log="$2"
  shift 2
  LAST_LOG="$log"
  if "$@" >"$log" 2>&1; then
    return 0
  else
    local rc=$?
    die "$desc: rc=$rc"
  fi
}

expect_fail() { # описание лог команда... — ожидается ненулевой код
  local desc="$1" log="$2"
  shift 2
  LAST_LOG="$log"
  if "$@" >"$log" 2>&1; then
    die "$desc: ожидалась блокировка (ненулевой код), получен rc=0"
  fi
  return 0
}

need_file()   { [ -e "$PROJECT/$1" ] || die "нет обязательного файла: $1"; }
need_absent() { [ ! -e "$PROJECT/$1" ] || die "лишнее в planning-профиле (SPEC п.1): $1"; }

head_sha() { git -C "$PROJECT" rev-parse HEAD; }

index_hashes() { # контрольные суммы индексов реестров
  python3 - "$PROJECT" <<'PY'
import hashlib, os, sys
root = os.path.join(sys.argv[1], "planning")
for name in ("ROADMAP.md", "ACTIVE_PLANS.md", "PLANS.md", "HOTFIXES.md"):
    path = os.path.join(root, name)
    try:
        with open(path, "rb") as fh:
            print(name, hashlib.sha256(fh.read()).hexdigest())
    except OSError:
        print(name, "MISSING")
PY
}

# Токен как отдельный идентификатор: PLAN-2 не должен ловить PLAN-20 и PLAN-2.1.
has_token() { grep -Eq "(^|[^0-9A-Za-z._-])$2([^0-9.]|$)" "$1" 2>/dev/null; }

HOOK_RC=0
run_hook_json() { # hook json log
  local hook="$1" json="$2" log="$3"
  LAST_LOG="$log"
  if printf '%s\n' "$json" | ( cd "$PROJECT" && CLAUDE_PROJECT_DIR="$PROJECT" bash "$hook" ) >"$log" 2>&1; then
    HOOK_RC=0
  else
    HOOK_RC=$?
  fi
}
expect_hook_rc() { # описание hook json ожидаемый_rc
  local desc="$1" hook="$2" json="$3" expected="$4"
  run_hook_json "$hook" "$json" "$LOGS/hook.log"
  [ "$HOOK_RC" -eq "$expected" ] || die "$desc: ожидался rc=$expected, получен rc=$HOOK_RC"
}

HAVE_JQ=0
if command -v jq >/dev/null 2>&1; then HAVE_JQ=1; fi

# ---------------------------------------------------------------------------
# Шаг 1. Чистый НЕ-Laravel репозиторий + install --profile planning.
# ---------------------------------------------------------------------------
begin_step 1 "install.sh --profile planning в чистый НЕ-Laravel git-репозиторий"
LAST_LOG="$LOGS/01-git-init.log"
if git -C "$PROJECT" init -q -b main >"$LAST_LOG" 2>&1; then
  :
else
  git -C "$PROJECT" init -q >>"$LAST_LOG" 2>&1 || die "git init не удался"
  git -C "$PROJECT" symbolic-ref HEAD refs/heads/main >>"$LAST_LOG" 2>&1 || die "не удалось создать ветку main"
fi
mkdir -p "$PROJECT/src"   # чтобы автодетект CODE_ROOTS (SPEC п.4) увидел корень кода
expect_ok "пустой начальный коммит main" "$LOGS/01-git-init.log" gitp commit -q --allow-empty -m "chore: init"
expect_ok "install --profile planning" "$LOGS/01-install.log" \
  in_project bash "$ROOT/install.sh" --project "$PROJECT" --profile planning --clients none --skills none --no-verify
sed -i.bak "s/^GATE_FAST=.*/GATE_FAST=true/" "$PROJECT/.claude/planning.conf"
rm "$PROJECT/.claude/planning.conf.bak"

for rel in \
  AGENTS.md planning/README.md planning/ROADMAP.md planning/ACTIVE_PLANS.md planning/PLANS.md planning/HOTFIXES.md \
  .claude/settings.json .claude/planning.conf .claude/planning.conf.template \
  .claude/scripts/registry.sh .claude/scripts/install-githooks.sh .claude/scripts/planning-init.sh \
  .claude/scripts/planning-lib.sh .claude/scripts/planning-owner-ok.sh .claude/scripts/plan-code-refs.sh \
  .claude/hooks/plans-drift.sh .claude/hooks/registry-guard.sh .claude/hooks/owner-ok-guard.sh \
  .claude/hooks/planning-checks.py .githooks/commit-msg .githooks/pre-commit .githooks/pre-push; do
  need_file "$rel"
done
# Strict-слой ставит .claude/scripts/quality-gate.sh и strict-хуки (branch/commit/merge/main-push) —
# это ожидаемо; отсутствовать должны только Laravel/снапшот-части (SPEC п.1, п.9).
for rel in .ai CLAUDE.md .mcp.json boost.json .codex .agents .dsh \
  .claude/hooks/big-read-guard.sh; do
  need_absent "$rel"
done

hooks_path="$(git -C "$PROJECT" config --get core.hooksPath || true)"
[ "$hooks_path" = ".githooks" ] || die "core.hooksPath='$hooks_path', ожидалось .githooks"

# В установленном слое не должно быть констант Laravel-профиля и абсолютных путей хоста (SPEC п.9).
if grep -REq 'horizon-1|/var/www/html|app_dusk' \
     "$PROJECT/AGENTS.md" "$PROJECT/.claude" "$PROJECT/.githooks" "$PROJECT/planning" 2>/dev/null; then
  grep -REn 'horizon-1|/var/www/html|app_dusk' \
    "$PROJECT/AGENTS.md" "$PROJECT/.claude" "$PROJECT/.githooks" "$PROJECT/planning" >"$LOGS/01-profile-leak.log" 2>&1 || true
  LAST_LOG="$LOGS/01-profile-leak.log"
  die "в установленном профиле остались константы Laravel-профиля или абсолютные пути хоста"
fi
step_ok

# ---------------------------------------------------------------------------
# Шаг 2. Реестры: check чист, planning-init.sh идемпотентен.
# ---------------------------------------------------------------------------
begin_step 2 "реестры: registry.sh check и идемпотентность planning-init.sh"
expect_ok "registry.sh check --registry all" "$LOGS/02-check.log" \
  in_project bash .claude/scripts/registry.sh check --registry all
for dir in planning/plans planning/plans/closed planning/roadmap planning/hotfixes; do
  [ -d "$PROJECT/$dir" ] || die "planning-init.sh не создал каталог $dir"
done
before_hashes="$(index_hashes)"
expect_ok "planning-init.sh (повторный запуск)" "$LOGS/02-init.log" \
  in_project bash .claude/scripts/planning-init.sh
after_hashes="$(index_hashes)"
[ "$before_hashes" = "$after_hashes" ] || die "planning-init.sh изменил индексы реестров (не идемпотентен)"
step_ok

# ---------------------------------------------------------------------------
# Шаг 3. add PLAN/HF/RM, ветка feature/PLAN-1-test, токен в commit-msg.
# ---------------------------------------------------------------------------
begin_step 3 "реестры add PLAN/HF/RM, ветка feature/PLAN-1-test, токен в commit-msg"
expect_ok "ветка feature/PLAN-1-test" "$LOGS/03-branch.log" gitp checkout -q -b feature/PLAN-1-test
expect_ok "registry.sh add PLAN auto" "$LOGS/03-add-plan.log" \
  in_project bash .claude/scripts/registry.sh add PLAN auto "Acceptance plan"
expect_ok "registry.sh add HF auto" "$LOGS/03-add-hf.log" \
  in_project bash .claude/scripts/registry.sh add HF auto "Acceptance hotfix"
expect_ok "registry.sh add RM auto" "$LOGS/03-add-rm.log" \
  in_project bash .claude/scripts/registry.sh add RM auto "Acceptance idea"

grep -q 'PLAN-1' "$PROJECT/planning/ACTIVE_PLANS.md" || die "в ACTIVE_PLANS.md нет строки PLAN-1"
grep -q 'HF-1' "$PROJECT/planning/HOTFIXES.md" || die "в HOTFIXES.md нет строки HF-1"
grep -q 'RM-1' "$PROJECT/planning/ROADMAP.md" || die "в ROADMAP.md нет строки RM-1"

plan_glob=("$PROJECT"/planning/plans/PLAN-1-*.md)
[ -e "${plan_glob[0]}" ] || die "add PLAN не создал planning/plans/PLAN-1-*.md"
PLAN_FILE_REL="planning/plans/$(basename "${plan_glob[0]}")"
# Содержание резюме пишет автор (E7 в planning-checks.py требует раздел «Резюме»).
printf '\nЦель: приёмка planning-профиля на не-Laravel репозитории.\n' >> "$PROJECT/$PLAN_FILE_REL"

expect_ok "git add плана PLAN-1" "$LOGS/03-git-add.log" gitp add planning/ACTIVE_PLANS.md planning/plans
expect_ok "коммит с токеном PLAN-1" "$LOGS/03-commit-ok.log" gitp commit -q -m "docs(PLAN-1): add acceptance plan"

printf 'chore: no plan token\n' > "$TMP/msg-no-token.txt"
if in_project bash .githooks/commit-msg "$TMP/msg-no-token.txt" >"$LOGS/03-msg-direct.log" 2>&1; then
  LAST_LOG="$LOGS/03-msg-direct.log"
  die "commit-msg не заблокировал сообщение без токена PLAN-N/HF-N"
fi
printf 'probe\n' > "$PROJECT/src/main.txt"
expect_ok "git add src/main.txt" "$LOGS/03-git-add-src.log" gitp add src/main.txt
before_head="$(head_sha)"
expect_fail "коммит без токена" "$LOGS/03-commit-blocked.log" gitp commit -q -m "chore: no plan token"
[ "$(head_sha)" = "$before_head" ] || die "заблокированный коммит всё-таки создан"
gitp reset -q
rm -f "$PROJECT/src/main.txt"
step_ok

# ---------------------------------------------------------------------------
# Шаг 4. registry-guard: прямые Edit/Write по индексам блокируются.
# ---------------------------------------------------------------------------
begin_step 4 "registry-guard: прямые правки индексов блокируются"
INDEX_JSON='{"tool_input":{"file_path":"planning/ACTIVE_PLANS.md"}}'
PLAN_JSON="$(printf '{"tool_input":{"file_path":"%s"}}' "$PLAN_FILE_REL")"
if [ "$HAVE_JQ" = 1 ]; then
  expect_hook_rc "registry-guard на индексе" ".claude/hooks/registry-guard.sh" "$INDEX_JSON" 2
else
  printf '  jq не найден: по SPEC п.7 guard обязан не блокировать (fail-open)\n'
  expect_hook_rc "registry-guard на индексе без jq (fail-open)" ".claude/hooks/registry-guard.sh" "$INDEX_JSON" 0
fi
expect_hook_rc "registry-guard на теле плана" ".claude/hooks/registry-guard.sh" "$PLAN_JSON" 0
step_ok

# ---------------------------------------------------------------------------
# Шаг 5. owner-ok: новая идея RM без маркера — блок, с маркером — проходит.
# ---------------------------------------------------------------------------
begin_step 5 "owner-ok: идея RM только со словом владельца"
expect_ok "registry.sh add RM auto (RM-2)" "$LOGS/05-add-rm2.log" \
  in_project bash .claude/scripts/registry.sh add RM auto "Second acceptance idea"
grep -q 'RM-2' "$PROJECT/planning/ROADMAP.md" || die "в ROADMAP.md нет строки RM-2"

expect_ok "git add ROADMAP/roadmap" "$LOGS/05-git-add.log" gitp add planning/ROADMAP.md planning/roadmap
before_head="$(head_sha)"
expect_fail "коммит RM без маркера owner-ok" "$LOGS/05-commit-blocked.log" \
  gitp commit -q -m "docs(PLAN-1): add roadmap ideas"
[ "$(head_sha)" = "$before_head" ] || die "коммит RM без маркера всё-таки создан"

# RM-1 заведён ещё в шаге 3 и уходит в этом же коммите, поэтому маркер нужен и на него.
expect_ok "planning-owner-ok.sh rm-add RM-1" "$LOGS/05-owner-ok-1.log" \
  in_project bash .claude/scripts/planning-owner-ok.sh rm-add RM-1
expect_ok "planning-owner-ok.sh rm-add RM-2" "$LOGS/05-owner-ok-2.log" \
  in_project bash .claude/scripts/planning-owner-ok.sh rm-add RM-2
expect_ok "коммит RM с маркером" "$LOGS/05-commit-ok.log" gitp commit -q -m "docs(PLAN-1): add roadmap ideas"

OWNER_JSON='{"tool_name":"Bash","tool_input":{"command":"bash .claude/scripts/planning-owner-ok.sh rm-add RM-3"}}'
if [ "$HAVE_JQ" = 1 ]; then
  expect_hook_rc "owner-ok-guard на запуске скрипта" ".claude/hooks/owner-ok-guard.sh" "$OWNER_JSON" 2
else
  expect_hook_rc "owner-ok-guard без jq (fail-open)" ".claude/hooks/owner-ok-guard.sh" "$OWNER_JSON" 0
fi
step_ok

# ---------------------------------------------------------------------------
# Шаг 6. Закрытие плана: без маркера — блок, с close-plan — проходит.
# ---------------------------------------------------------------------------
begin_step 6 "закрытие плана: plans/closed + owner-ok close-plan"
mkdir -p "$PROJECT/planning/plans/closed"
cat > "$PROJECT/planning/plans/closed/PLAN-1.md" <<'EOF'
# PLAN-1 — Acceptance plan (закрыт)

**Статус:** закрыт

## Резюме

План создан и закрыт в приёмочном сценарии planning-профиля.
EOF
expect_ok "registry.sh set-status PLAN-1 закрыт" "$LOGS/06-set-status.log" \
  in_project bash .claude/scripts/registry.sh set-status PLAN-1 закрыт
grep -q 'PLAN-1' "$PROJECT/planning/PLANS.md" || die "после закрытия PLAN-1 нет строки в PLANS.md"
expect_ok "git add planning/" "$LOGS/06-git-add.log" gitp add planning
before_head="$(head_sha)"
expect_fail "коммит закрытия без маркера" "$LOGS/06-commit-blocked.log" \
  gitp commit -q -m "docs(PLAN-1): close plan"
[ "$(head_sha)" = "$before_head" ] || die "коммит закрытия без close-plan маркера всё-таки создан"
expect_ok "planning-owner-ok.sh close-plan PLAN-1" "$LOGS/06-owner-ok.log" \
  in_project bash .claude/scripts/planning-owner-ok.sh close-plan PLAN-1
expect_ok "коммит закрытия с маркером" "$LOGS/06-commit-ok.log" gitp commit -q -m "docs(PLAN-1): close plan"
expect_ok "registry.sh check после закрытия" "$LOGS/06-check.log" \
  in_project bash .claude/scripts/registry.sh check --registry all
step_ok

# ---------------------------------------------------------------------------
# Шаг 7. plans-drift: видит код-коммит PLAN-2, забывает после правки индекса.
# ---------------------------------------------------------------------------
begin_step 7 "plans-drift: код с токеном PLAN-2 виден, после индекса — нет"
expect_ok "ветка feature/PLAN-2-test" "$LOGS/07-branch.log" gitp checkout -q -b feature/PLAN-2-test
expect_ok "registry.sh add PLAN auto (PLAN-2)" "$LOGS/07-add-plan.log" \
  in_project bash .claude/scripts/registry.sh add PLAN auto "Drift probe plan"
grep -q 'PLAN-2' "$PROJECT/planning/ACTIVE_PLANS.md" || die "в ACTIVE_PLANS.md нет строки PLAN-2"
plan2_glob=("$PROJECT"/planning/plans/PLAN-2-*.md)
[ -e "${plan2_glob[0]}" ] || die "add PLAN не создал planning/plans/PLAN-2-*.md"
printf '\nЦель: проверить, что plans-drift замечает код-коммит по плану.\n' >> "${plan2_glob[0]}"

expect_ok "git add плана PLAN-2" "$LOGS/07-git-add-plan.log" gitp add planning/ACTIVE_PLANS.md planning/plans
expect_ok "коммит строки индекса PLAN-2" "$LOGS/07-commit-plan.log" \
  gitp commit -q -m "docs(PLAN-2): add drift probe plan"

# git-время хранится в секундах: раздвигаем коммиты, чтобы «новее» было однозначным.
sleep 1
printf 'drift probe\n' > "$PROJECT/src/main.txt"
expect_ok "git add src/main.txt" "$LOGS/07-git-add-src.log" gitp add src/main.txt
expect_ok "код-коммит feat(PLAN-2)" "$LOGS/07-commit-code.log" \
  gitp commit -q -m "feat(PLAN-2): drift probe code"

expect_ok "plans-drift.sh (информатор)" "$LOGS/07-drift-before.log" \
  in_project bash .claude/hooks/plans-drift.sh
has_token "$LOGS/07-drift-before.log" "PLAN-2" \
  || die "plans-drift.sh не увидел код-коммит с токеном PLAN-2"

sleep 1
expect_ok "registry.sh set-status PLAN-2 в работе" "$LOGS/07-set-status.log" \
  in_project bash .claude/scripts/registry.sh set-status PLAN-2 "в работе"
expect_ok "git add индекса PLAN-2" "$LOGS/07-git-add-idx.log" gitp add planning/ACTIVE_PLANS.md
expect_ok "коммит обновления индекса" "$LOGS/07-commit-idx.log" \
  gitp commit -q -m "docs(PLAN-2): mark plan in progress"

expect_ok "plans-drift.sh после обновления индекса" "$LOGS/07-drift-after.log" \
  in_project bash .claude/hooks/plans-drift.sh
if has_token "$LOGS/07-drift-after.log" "PLAN-2"; then
  LAST_LOG="$LOGS/07-drift-after.log"
  die "plans-drift.sh всё ещё показывает PLAN-2 после обновления индекса"
fi
step_ok

# ---------------------------------------------------------------------------
# Шаг 8. verify --profile planning; повторная установка: без --force ошибка, с --force backup.
# ---------------------------------------------------------------------------
begin_step 8 "verify --profile planning, повторная установка и backup"
expect_ok "verify.sh --profile planning" "$LOGS/08-verify.log" \
  bash "$ROOT/verify.sh" --project "$PROJECT" --profile planning
expect_fail "повторная установка без --force" "$LOGS/08-reinstall-conflict.log" \
  in_project bash "$ROOT/install.sh" --project "$PROJECT" --profile planning --clients none --skills none --no-verify
expect_ok "повторная установка с --force" "$LOGS/08-reinstall-force.log" \
  in_project bash "$ROOT/install.sh" --project "$PROJECT" --profile planning --clients none --skills none --force
backups=("$PROJECT"/.x-harness-backup.*)
[ -e "${backups[0]}" ] || die "после --force нет каталога .x-harness-backup.*"
[ -f "${backups[0]}/AGENTS.md" ] || die "backup после --force не содержит AGENTS.md"
step_ok

echo "acceptance-planning: OK"
