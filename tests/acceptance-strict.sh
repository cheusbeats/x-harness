#!/usr/bin/env bash
# tests/acceptance-strict.sh — приёмка СТРОГОГО планировочного профиля x-harness (SPEC §9).
#
# Проверяет, что strict-слой переносится между агентами и реально блокирует нарушения:
#  1. install --profile planning ставит strict-файлы и ключи planning.conf;
#  2. branch-guard: E2 (main/feature) и E18 (защищённые пути);
#  3. commit-gate: E16 (--no-verify, core.hooksPath) и запрет коммита на main;
#  4. E18: коммит protected path без hooks-edit блокируется, с маркером — проходит;
#  5. merge-gate: мерж в main только с merge-маркером и зелёным GATE_MERGE;
#  6. main-push-guard + git pre-push: прямой коммит в main и force push блокируются,
#     push feature-ветки проходит;
#  7. кросс-агентные конфиги: .codex/hooks.json и .dsh/hooks(-bridge).json содержат strict-хуки;
#  8. bin/xh gate --fast и merge-ready (generic-агент).
#
# Запуск: bash tests/acceptance-strict.sh   (из любого каталога)
# Всё — во временном каталоге; HOME/TMPDIR изолированы. XH_ACCEPT_KEEP=1 — оставить каталог.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/xh-accept-strict.XXXXXX")"
PROJECT="$TMP/project"
LOGS="$TMP/logs"
CONF_ORIG="$TMP/planning.conf.orig"
FAKEBIN="$TMP/fakebin"
export FAKE_DSH_LOG="$TMP/fake-dsh.log"
export HOME="$TMP/home"
export TMPDIR="$TMP/tmp"
mkdir -p "$HOME" "$TMPDIR" "$LOGS" "$PROJECT" "$FAKEBIN"
export PATH="$FAKEBIN:$PATH"
cleanup() {
  if [ "${XH_ACCEPT_KEEP:-0}" = 1 ]; then
    printf 'acceptance-strict: временный каталог сохранён: %s\n' "$TMP" >&2
  else
    rm -rf "$TMP"
  fi
}
trap cleanup EXIT

# Фейковый dsh: install.sh вызывает dsh plugin ... для community/bridge.
cat > "$FAKEBIN/dsh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$FAKE_DSH_LOG"
exit 0
EOF
chmod +x "$FAKEBIN/dsh"

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_CEILING_DIRECTORIES 2>/dev/null || true
export GIT_TERMINAL_PROMPT=0
export GIT_CONFIG_NOSYSTEM=1

GIT_OPTS=(-c user.name=acceptance -c user.email=acceptance@example.invalid -c commit.gpgsign=false)
gitp() { git -C "$PROJECT" "${GIT_OPTS[@]}" "$@"; }
git_at() { local dir="$1"; shift; git -C "$dir" "${GIT_OPTS[@]}" "$@"; }
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
expect_fail() { # описание лог команда... — ожидается любой ненулевой код
  local desc="$1" log="$2"
  shift 2
  LAST_LOG="$log"
  if "$@" >"$log" 2>&1; then
    die "$desc: ожидалась блокировка (ненулевой код), получен rc=0"
  fi
  return 0
}
expect_rc() { # описание ожидаемый_rc лог команда...
  local desc="$1" expected="$2" log="$3"
  shift 3
  LAST_LOG="$log"
  local rc=0
  if "$@" >"$log" 2>&1; then rc=0; else rc=$?; fi
  [ "$rc" -eq "$expected" ] || die "$desc: ожидался rc=$expected, получен rc=$rc"
}

need_file() { [ -e "$PROJECT/$1" ] || die "нет обязательного файла: $1"; }
need_exec() { [ -x "$PROJECT/$1" ] || die "файл не исполняемый: $1"; }

head_sha() { git -C "$PROJECT" rev-parse HEAD; }
remote_sha() { git -C "$TMP/remote.git" rev-parse --verify "refs/heads/$1" 2>/dev/null || true; }

HAVE_JQ=0
NOJQ_NOTED=0
if command -v jq >/dev/null 2>&1; then HAVE_JQ=1; fi

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
expect_guard_rc() { # описание hook json ожидаемый_rc (без jq PreToolUse-хуки обязаны fail-open)
  local desc="$1" hook="$2" json="$3" expected="$4"
  if [ "$HAVE_JQ" = 0 ]; then
    if [ "$NOJQ_NOTED" = 0 ]; then
      printf '  jq не найден: PreToolUse-хуки по SPEC п.7 не блокируют (fail-open)\n'
      NOJQ_NOTED=1
    fi
    expected=0
  fi
  run_hook_json "$hook" "$json" "$LOGS/hook.log"
  [ "$HOOK_RC" -eq "$expected" ] || die "$desc: ожидался rc=$expected, получен rc=$HOOK_RC"
}

set_conf() { # KEY VALUE
  python3 - "$PROJECT/.claude/planning.conf" "$1" "$2" <<'PY'
import sys
path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
lines = open(path, encoding="utf-8").read().splitlines()
for i, line in enumerate(lines):
    if line.startswith(key + "="):
        lines[i] = key + "=" + value
        break
else:
    lines.append(key + "=" + value)
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
PY
}

make_repo() { # dir — пустой НЕ-Laravel git-репозиторий на main
  local dir="$1"
  mkdir -p "$dir/src"
  if ! git -C "$dir" init -q -b main >/dev/null 2>&1; then
    git -C "$dir" init -q >/dev/null 2>&1 || die "git init: $dir"
    git -C "$dir" symbolic-ref HEAD refs/heads/main
  fi
  git_at "$dir" commit -q --allow-empty -m "chore: init"
}

check_hook_names() { # file label
  local file="$1" label="$2" name
  [ -f "$file" ] || die "$label: нет файла $file"
  for name in branch-guard commit-gate merge-gate main-push-guard owner-ok-guard registry-guard; do
    grep -q "$name" "$file" || die "$label: в $file нет хука $name"
  done
}

check_dsh_adapter() { # repo config label — DSH config dispatches through .dsh/agent-hook.py; prove it blocks
  local repo="$1" file="$2" label="$3" rc=0
  [ -f "$file" ] || die "$label: нет файла $file"
  grep -q 'agent-hook.py dsh PreToolUse' "$file" || die "$label: PreToolUse не ведёт в .dsh/agent-hook.py"
  [ -f "$repo/.dsh/agent-hook.py" ] || die "$label: нет .dsh/agent-hook.py"
  printf '{"cwd":"%s","tool_name":"edit","tool_input":{"path":"src/x.py"}}' "$repo" \
    | python3 "$repo/.dsh/agent-hook.py" dsh PreToolUse >/dev/null 2>&1 || rc=$?
  [ "$rc" = 2 ] || die "$label: правка кода на main через DSH-payload не заблокирована (rc=$rc)"
}

# ---------------------------------------------------------------------------
# Шаг 1. install --profile planning: strict-файлы и conf-ключи.
# ---------------------------------------------------------------------------
begin_step 1 "install --profile planning: strict-файлы и conf-ключи"
LAST_LOG="$LOGS/01-git-init.log"
if git -C "$PROJECT" init -q -b main >"$LAST_LOG" 2>&1; then
  :
else
  git -C "$PROJECT" init -q >>"$LAST_LOG" 2>&1 || die "git init не удался"
  git -C "$PROJECT" symbolic-ref HEAD refs/heads/main >>"$LAST_LOG" 2>&1 || die "не удалось создать main"
fi
mkdir -p "$PROJECT/src"   # автодетект CODE_ROOTS должен увидеть src
expect_ok "пустой начальный коммит main" "$LOGS/01-git-init.log" gitp commit -q --allow-empty -m "chore: init"
expect_ok "install --profile planning" "$LOGS/01-install.log" \
  bash "$ROOT/install.sh" --project "$PROJECT" --profile planning --clients none --skills none --no-verify

for rel in \
  AGENTS.md planning/README.md .claude/planning.conf .claude/settings.json \
  .claude/scripts/registry.sh .claude/scripts/install-githooks.sh .claude/scripts/planning-init.sh \
  .claude/scripts/planning-lib.sh .claude/scripts/planning-owner-ok.sh .claude/scripts/plan-code-refs.sh \
  .claude/scripts/quality-gate.sh .claude/scripts/merge-ready.sh \
  .claude/hooks/plans-drift.sh .claude/hooks/registry-guard.sh .claude/hooks/owner-ok-guard.sh \
  .claude/hooks/planning-checks.py .claude/hooks/strict-checks.py \
  .claude/hooks/branch-guard.sh .claude/hooks/commit-gate.sh .claude/hooks/merge-gate.sh \
  .claude/hooks/main-push-guard.sh \
  .githooks/commit-msg .githooks/pre-commit .githooks/pre-push \
  .claude/state/.gitignore; do
  need_file "$rel"
done
for rel in \
  .claude/hooks/branch-guard.sh .claude/hooks/commit-gate.sh .claude/hooks/merge-gate.sh \
  .claude/hooks/main-push-guard.sh .claude/hooks/owner-ok-guard.sh .claude/hooks/registry-guard.sh \
  .claude/hooks/plans-drift.sh .claude/scripts/quality-gate.sh .claude/scripts/merge-ready.sh \
  .claude/scripts/registry.sh .claude/scripts/planning-owner-ok.sh .githooks/commit-msg \
  .githooks/pre-commit .githooks/pre-push; do
  need_exec "$rel"
done

for key in MAIN_BRANCH CODE_ROOTS STRICT PROTECTED_PATHS CODE_FILES GATE_FAST GATE_MERGE; do
  grep -qE "^$key=" "$PROJECT/.claude/planning.conf" || die "в planning.conf нет ключа $key"
done
grep -qE '^STRICT=on' "$PROJECT/.claude/planning.conf" || die "STRICT по умолчанию должен быть on"
grep -q '.claude/hooks/' "$PROJECT/.claude/planning.conf" || die "PROTECTED_PATHS без .claude/hooks/"
grep -q 'Makefile' "$PROJECT/.claude/planning.conf" || die "CODE_FILES без Makefile"
for name in branch-guard commit-gate merge-gate main-push-guard owner-ok-guard registry-guard plans-drift; do
  grep -q "$name" "$PROJECT/.claude/settings.json" || die "settings.json без хука $name"
done
grep -q '^\*' "$PROJECT/.claude/state/.gitignore" || die ".claude/state/.gitignore не игнорирует состояние"
set_conf GATE_FAST true
cp "$PROJECT/.claude/planning.conf" "$CONF_ORIG"
step_ok

# ---------------------------------------------------------------------------
# Шаг 2. branch-guard: E2 (ветки) и E18 (защищённые пути).
# ---------------------------------------------------------------------------
begin_step 2 "branch-guard: E2 (main/feature) и защищённые пути"
EDIT_SRC='{"tool_name":"Edit","tool_input":{"file_path":"src/main.txt"}}'
EDIT_PLANNING='{"tool_name":"Edit","tool_input":{"file_path":"planning/ACTIVE_PLANS.md"}}'
EDIT_PROTECTED='{"tool_name":"Edit","tool_input":{"file_path":".claude/hooks/registry-guard.sh"}}'
expect_guard_rc "branch-guard: правка src на main" ".claude/hooks/branch-guard.sh" "$EDIT_SRC" 2
expect_guard_rc "branch-guard: правка индекса planning на main" ".claude/hooks/branch-guard.sh" "$EDIT_PLANNING" 2
expect_ok "ветка feature/PLAN-1-test" "$LOGS/02-branch.log" gitp checkout -q -b feature/PLAN-1-test
expect_guard_rc "branch-guard: правка src на feature/PLAN-1-test" ".claude/hooks/branch-guard.sh" "$EDIT_SRC" 0
expect_guard_rc "branch-guard: защищённый путь без hooks-edit" ".claude/hooks/branch-guard.sh" "$EDIT_PROTECTED" 2
step_ok

# ---------------------------------------------------------------------------
# Шаг 3. commit-gate: E16 и запрет коммита на main.
# ---------------------------------------------------------------------------
begin_step 3 "commit-gate: E16 (обход хуков) и коммит на main"
gitp checkout -q main
JSON_COMMIT='{"tool_name":"Bash","tool_input":{"command":"git commit -m \"docs: acceptance\""}}'
JSON_NO_VERIFY='{"tool_name":"Bash","tool_input":{"command":"git commit --no-verify -m \"feat(PLAN-1): bypass\""}}'
JSON_HOOKSPATH='{"tool_name":"Bash","tool_input":{"command":"git config core.hooksPath ."}}'
JSON_INLINE='{"tool_name":"Bash","tool_input":{"command":"git -c core.hooksPath=/tmp commit -m \"feat(PLAN-1): bypass\""}}'
expect_guard_rc "commit-gate: git commit на main" ".claude/hooks/commit-gate.sh" "$JSON_COMMIT" 2
expect_guard_rc "commit-gate: git commit --no-verify" ".claude/hooks/commit-gate.sh" "$JSON_NO_VERIFY" 2
expect_guard_rc "commit-gate: git config core.hooksPath ." ".claude/hooks/commit-gate.sh" "$JSON_HOOKSPATH" 2
expect_guard_rc "commit-gate: -c core.hooksPath=..." ".claude/hooks/commit-gate.sh" "$JSON_INLINE" 2
expect_ok "ветка feature/PLAN-1-test (повторно)" "$LOGS/03-branch.log" gitp checkout -q feature/PLAN-1-test
set_conf GATE_FAST ""
expect_fail "pre-commit: пустой GATE_FAST блокирует коммит" "$LOGS/03-pre-commit-empty.log" in_project bash .githooks/pre-commit
JSON_EMPTY_FAST='{"tool_name":"Bash","tool_input":{"command":"git commit -m \"feat(PLAN-1): acceptance\""}}'
expect_guard_rc "commit-gate: пустой GATE_FAST блокирует коммит" ".claude/hooks/commit-gate.sh" "$JSON_EMPTY_FAST" 2
set_conf GATE_FAST true
JSON_FEATURE='{"tool_name":"Bash","tool_input":{"command":"git commit -m \"feat(PLAN-1): acceptance\""}}'
expect_guard_rc "commit-gate: коммит с токеном на feature/PLAN-1-test" ".claude/hooks/commit-gate.sh" "$JSON_FEATURE" 0
step_ok

# ---------------------------------------------------------------------------
# Шаг 4. E18: коммит правки защищённых путей только с маркером hooks-edit.
# ---------------------------------------------------------------------------
begin_step 4 "E18: защищённые пути без hooks-edit блокируются"
printf '\n# acceptance-strict: E18 probe\n' >> "$PROJECT/.claude/hooks/registry-guard.sh"
expect_ok "git add protected path" "$LOGS/04-git-add.log" gitp add .claude/hooks/registry-guard.sh
before_head="$(head_sha)"
expect_fail "коммит .claude/hooks без маркера" "$LOGS/04-commit-blocked.log" \
  gitp commit -q -m "chore(PLAN-1): tweak registry guard"
[ "$(head_sha)" = "$before_head" ] || die "коммит protected path без маркера всё-таки создан"
expect_ok "planning-owner-ok.sh hooks-edit feature/PLAN-1-test" "$LOGS/04-owner-ok.log" \
  in_project bash .claude/scripts/planning-owner-ok.sh hooks-edit feature/PLAN-1-test
expect_guard_rc "branch-guard: защищённый путь с hooks-edit" ".claude/hooks/branch-guard.sh" "$EDIT_PROTECTED" 0
expect_ok "коммит .claude/hooks с маркером" "$LOGS/04-commit-ok.log" \
  gitp commit -q -m "chore(PLAN-1): tweak registry guard"
expect_ok "registry.sh check после E18" "$LOGS/04-registry-check.log" \
  in_project bash .claude/scripts/registry.sh check --registry all
step_ok

# ---------------------------------------------------------------------------
# Шаг 5. merge-gate: bare remote, ветка feature/PLAN-2, маркер merge, GATE_MERGE.
# ---------------------------------------------------------------------------
begin_step 5 "merge-gate: мерж в main только с merge-маркером и GATE_MERGE"
expect_ok "bare remote в TMP" "$LOGS/05-remote.log" git init -q --bare "$TMP/remote.git"
expect_ok "origin -> bare remote" "$LOGS/05-origin.log" gitp remote add origin "$TMP/remote.git"
expect_ok "ветка main" "$LOGS/05-main.log" gitp checkout -q main
expect_ok "push main (первый; прямых коммитов нет)" "$LOGS/05-push-main.log" gitp push -q -u origin main

expect_ok "ветка feature/PLAN-2-test" "$LOGS/05-branch2.log" gitp checkout -q -b feature/PLAN-2-test
expect_ok "registry.sh add PLAN PLAN-2" "$LOGS/05-add-plan.log" \
  in_project bash .claude/scripts/registry.sh add PLAN PLAN-2 "Strict merge plan"
grep -q 'PLAN-2' "$PROJECT/planning/ACTIVE_PLANS.md" || die "в ACTIVE_PLANS.md нет строки PLAN-2"
plan2_glob=("$PROJECT"/planning/plans/PLAN-2-*.md)
[ -e "${plan2_glob[0]}" ] || die "registry.sh add PLAN не создал planning/plans/PLAN-2-*.md"
printf '\nЦель: проверить строгий мерж в main по маркеру владельца.\n' >> "${plan2_glob[0]}"
expect_ok "git add плана PLAN-2" "$LOGS/05-git-add-plan.log" gitp add planning/ACTIVE_PLANS.md planning/plans
expect_ok "коммит PLAN-2" "$LOGS/05-commit-plan.log" gitp commit -q -m "docs(PLAN-2): add strict merge plan"
printf 'strict code\n' > "$PROJECT/src/main.txt"
expect_ok "git add src/main.txt" "$LOGS/05-git-add-src.log" gitp add src/main.txt
expect_ok "код-коммит feat(PLAN-2)" "$LOGS/05-commit-code.log" gitp commit -q -m "feat(PLAN-2): strict code"
expect_ok "реестры чисты перед мержем" "$LOGS/05-registry-check.log" \
  in_project bash .claude/scripts/registry.sh check --registry all

expect_ok "текущая ветка main" "$LOGS/05-to-main.log" gitp checkout -q main
MERGE_JSON='{"tool_name":"Bash","tool_input":{"command":"git merge --no-ff feature/PLAN-2-test"}}'
expect_guard_rc "merge-gate: мерж без merge-маркера" ".claude/hooks/merge-gate.sh" "$MERGE_JSON" 2
expect_ok "planning-owner-ok.sh merge feature/PLAN-2-test" "$LOGS/05-owner-ok-merge.log" \
  in_project bash .claude/scripts/planning-owner-ok.sh merge feature/PLAN-2-test
expect_guard_rc "merge-gate: пустой GATE_MERGE запрещает мерж" ".claude/hooks/merge-gate.sh" "$MERGE_JSON" 2
expect_rc "merge-ready: пустой GATE_MERGE не готов" 1 "$LOGS/05-ready-empty.log" \
  in_project bash .claude/scripts/merge-ready.sh feature/PLAN-2-test
set_conf GATE_MERGE true
expect_guard_rc "merge-gate: нет отметки" ".claude/hooks/merge-gate.sh" "$MERGE_JSON" 2
expect_ok "вернуться на целевую ветку" "$LOGS/05-to-feature.log" gitp checkout -q feature/PLAN-2-test
expect_ok "зелёный GATE_MERGE на вершине ветки" "$LOGS/05-gate-merge-ok.log" \
  in_project bash .claude/scripts/quality-gate.sh --merge
expect_ok "вернуться на main" "$LOGS/05-to-main-again.log" gitp checkout -q main
expect_guard_rc "merge-gate: маркер + токены + чистые реестры + гейт" ".claude/hooks/merge-gate.sh" "$MERGE_JSON" 0
expect_ok "скрыть неотслеживаемые файлы fixture" "$LOGS/05-hide-untracked.log" gitp config status.showUntrackedFiles no
expect_ok "merge-ready: пройденный гейт" "$LOGS/05-ready-green.log" \
  in_project bash .claude/scripts/merge-ready.sh feature/PLAN-2-test

set_conf GATE_MERGE false
expect_rc "quality-gate --merge при GATE_MERGE=false" 1 "$LOGS/05-gate-merge-fail.log" \
  in_project bash .claude/scripts/quality-gate.sh --merge
expect_guard_rc "merge-gate: GATE_MERGE не пройден" ".claude/hooks/merge-gate.sh" "$MERGE_JSON" 2
cp "$CONF_ORIG" "$PROJECT/.claude/planning.conf"
step_ok

# ---------------------------------------------------------------------------
# Шаг 6. main-push-guard и git pre-push: прямой коммит в main и force push.
# ---------------------------------------------------------------------------
begin_step 6 "main-push-guard и pre-push: прямой коммит/force push в main"
gitp checkout -q feature/PLAN-2-test
expect_ok "push feature/PLAN-2-test (разрешён)" "$LOGS/06-push-feature.log" \
  gitp push -q origin feature/PLAN-2-test
remote_feature="$(remote_sha feature/PLAN-2-test)"
[ -n "$remote_feature" ] || die "feature/PLAN-2-test не появился в remote"

gitp checkout -q main
printf '\n<!-- acceptance-strict: прямой коммит в main -->\n' >> "$PROJECT/planning/README.md"
expect_ok "git add planning/README.md" "$LOGS/06-git-add.log" gitp add planning/README.md
expect_ok "прямой коммит на main (planning разрешён)" "$LOGS/06-commit-main.log" \
  gitp commit -q -m "docs: direct main change"
remote_main_before="$(remote_sha main)"
[ -n "$remote_main_before" ] || die "main не появился в remote"

PUSH_JSON='{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}'
expect_guard_rc "main-push-guard: прямой не-мерж коммит в main" ".claude/hooks/main-push-guard.sh" "$PUSH_JSON" 2
expect_fail "реальный git push main блокируется pre-push" "$LOGS/06-push-main-blocked.log" \
  gitp push -q origin main
[ "$(remote_sha main)" = "$remote_main_before" ] || die "заблокированный push всё-таки обновил main в remote"

expect_ok "ветка feature/PLAN-2-test (перед force push)" "$LOGS/06-branch.log" gitp checkout -q feature/PLAN-2-test
expect_guard_rc "main-push-guard: push main из не-main" ".claude/hooks/main-push-guard.sh" "$PUSH_JSON" 2
expect_ok "amend коммита (создаём non-fast-forward)" "$LOGS/06-amend.log" gitp commit -q --amend --no-edit
expect_fail "force push non-fast-forward блокируется pre-push" "$LOGS/06-push-force.log" \
  gitp push -q --force origin feature/PLAN-2-test
[ "$(remote_sha feature/PLAN-2-test)" = "$remote_feature" ] || die "заблокированный force push всё-таки обновил remote"
step_ok

# ---------------------------------------------------------------------------
# Шаг 7. Кросс-агентные конфиги: Codex hooks.json и DSH bridge/community.
# ---------------------------------------------------------------------------
begin_step 7 "кросс-агентные конфиги: Codex и DSH (community/bridge)"
CODEX_REPO="$TMP/agent-codex"
DSH_COMMUNITY_REPO="$TMP/agent-dsh-community"
DSH_BRIDGE_REPO="$TMP/agent-dsh-bridge"
for dir in "$CODEX_REPO" "$DSH_COMMUNITY_REPO" "$DSH_BRIDGE_REPO"; do
  make_repo "$dir"
done

expect_ok "install --clients codex" "$LOGS/07-install-codex.log" \
  bash "$ROOT/install.sh" --project "$CODEX_REPO" --profile planning --clients codex --skills none --no-verify
check_hook_names "$CODEX_REPO/.codex/hooks.json" ".codex/hooks.json"
[ -f "$CODEX_REPO/.codex/hooks/claude-compat.py" ] || die "нет .codex/hooks/claude-compat.py"

expect_ok "install --dsh-hooks community" "$LOGS/07-install-dsh-community.log" \
  bash "$ROOT/install.sh" --project "$DSH_COMMUNITY_REPO" --profile planning --clients none --skills none \
    --dsh-hooks community --no-verify
check_dsh_adapter "$DSH_COMMUNITY_REPO" "$DSH_COMMUNITY_REPO/.dsh/hooks.json" ".dsh/hooks.json (community)"
grep -q 'dsh-hooks-plugin' "$FAKE_DSH_LOG" || die "install не вызывал dsh plugin для community"

expect_ok "install --dsh-hooks bridge" "$LOGS/07-install-dsh-bridge.log" \
  bash "$ROOT/install.sh" --project "$DSH_BRIDGE_REPO" --profile planning --clients none --skills none \
    --dsh-hooks bridge --dsh-version 0.0.0-test --no-verify
grep -q "github:cheusbeats/x-harness" "$FAKE_DSH_LOG" || die "bridge: install не добавил бандл x-harness в профиль DSH"
[ ! -e "$DSH_BRIDGE_REPO/.dsh/hooks-bridge.json" ] || die "bridge: конфиг моста не должен лежать в проекте (он общий на процесс DSH)"
grep -q '0.0.0-test' "$FAKE_DSH_LOG" || die "install не вызывал dsh plugin с --dsh-version"
step_ok

# ---------------------------------------------------------------------------
# Шаг 8. bin/xh: gate --fast и merge-ready (generic-агент).
# ---------------------------------------------------------------------------
begin_step 8 "bin/xh gate --fast и merge-ready (generic-агент)"
expect_ok "ветка main перед bin/xh" "$LOGS/08-main.log" gitp checkout -q main
set_conf GATE_FAST ""
expect_rc "bin/xh gate --fast (GATE_FAST пусто = блокировка)" 1 "$LOGS/08-gate-skip.log" \
  in_project bash "$ROOT/bin/xh" gate --fast
set_conf GATE_FAST false
expect_rc "bin/xh gate --fast (GATE_FAST=false)" 1 "$LOGS/08-gate-fail.log" \
  in_project bash "$ROOT/bin/xh" gate --fast
cp "$CONF_ORIG" "$PROJECT/.claude/planning.conf"
expect_fail "bin/xh merge-ready без merge-маркера" "$LOGS/08-merge-ready.log" \
  in_project bash "$ROOT/bin/xh" merge-ready feature/PLAN-2-test
step_ok

echo "acceptance-strict: OK"
