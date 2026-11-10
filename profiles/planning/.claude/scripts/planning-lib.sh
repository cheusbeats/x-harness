#!/usr/bin/env bash
# planning-lib.sh — загрузка .claude/planning.conf с дефолтами (SPEC п.4).
#
# Подключение:
#   . "$(dirname "$0")/planning-lib.sh"             # .claude/scripts/*
#   . "$(dirname "$0")/../scripts/planning-lib.sh"  # .claude/hooks/*
#   planning_load_conf
#
# Конфига может не быть: дефолты ниже совпадают с шаблоном SPEC. Значение, явно
# заданное в файле, главнее дефолта — в том числе пустое: пустой CODE_ROOTS означает
# автодетект корней кода (см. planning_code_roots), пустой DRIFT_MEMORY_INDEX —
# выключенную проверку памяти.

# Корень проекта: git-корень, иначе текущий каталог.
planning_root() {
  local root
  root="$(git rev-parse --show-toplevel 2>/dev/null)" || root=""
  [ -n "$root" ] || root="$(pwd)"
  printf '%s\n' "$root"
}

# Строку со списком (через пробелы/табы/переводы строк) — по одному слову на строку.
# Через pipe, чтобы слова не раскрывались как glob-маски.
planning_words() {
  printf '%s\n' "$1" | tr -s '[:space:]' '\n' | sed '/^$/d'
}

# Число из конфига; мусор и пустое значение заменяются дефолтом.
planning_int() { # $1 значение, $2 дефолт, $3 минимум (по умолчанию 0)
  local v="$1" d="$2" min="${3:-0}"
  case "$v" in
    ''|*[!0-9]*) printf '%s\n' "$d" ;;
    *) if [ "$v" -lt "$min" ]; then printf '%s\n' "$d"; else printf '%s\n' "$v"; fi ;;
  esac
}

# Каталоги первого уровня, похожие на корни кода: по git, кроме служебных.
# Нужен, когда CODE_ROOTS пуст или не содержит ни одного существующего каталога —
# так профиль работает в любом репозитории без правки conf.
planning_autodetect_roots() {
  local name
  git ls-files -z 2>/dev/null | tr '\0' '\n' | awk -F/ 'NF>1{print $1}' | sort -u | while IFS= read -r name; do
    case "$name" in
      .*|planning|node_modules|vendor) continue ;;
    esac
    [ -d "$name" ] && printf '%s\n' "$name"
  done
}

# Итоговые корни кода: существующие из CODE_ROOTS, иначе автодетект.
planning_code_roots() {
  local list=() existing=() name
  while IFS= read -r name; do list+=("$name"); done < <(planning_words "$CODE_ROOTS")
  if [ ${#list[@]} -gt 0 ]; then
    for name in "${list[@]}"; do
      [ -d "$name" ] && existing+=("$name")
    done
  fi
  if [ ${#existing[@]} -gt 0 ]; then
    printf '%s\n' "${existing[@]}"
    return 0
  fi
  planning_autodetect_roots
}

# ---------------------------------------------------------------- строгий слой

# STRICT=on (SPEC §9). off выключает новые блокировки, ядро остаётся.
planning_strict_on() {
  [ "${STRICT:-on}" = on ]
}

# Однозначное имя в маркере owner-ok: % / _ @ кодируются (см. planning-checks.py enc).
planning_enc() {
  printf '%s' "$1" | sed -e 's/%/%25/g' -e 's#/#%2F#g' -e 's/_/%5F/g' -e 's/@/%40/g'
}

# Путь относится к planning/ (реестры и тела записей).
planning_is_planning_path() {
  case "$1" in planning/*) return 0 ;; *) return 1 ;; esac
}

# Путь защищён (E18): каталог-префикс с «/» на конце или точный файл.
planning_is_protected_path() {
  local rel="$1" p
  for p in ${PROTECTED_PATHS:-}; do
    case "$p" in
      */) case "$rel" in "$p"*) return 0 ;; esac ;;
      *) [ "$rel" = "$p" ] && return 0 ;;
    esac
  done
  return 1
}

# Путь — код (E2): каталог из CODE_ROOTS/автодетекта или корневой файл из CODE_FILES.
# planning/, docs/, wiki/, *.md и защищённые пути — НЕ код (SPEC §9).
planning_is_code_path() {
  local rel="$1" first roots r
  case "$rel" in
    planning/*|docs/*|wiki/*) return 1 ;;
    *.md) return 1 ;;
  esac
  planning_is_protected_path "$rel" && return 1
  first="${rel%%/*}"
  if [ "$first" = "$rel" ]; then
    case " ${CODE_FILES:-} " in
      *" $rel "*) return 0 ;;
    esac
  fi
  roots="$(planning_code_roots | tr '\n' ' ')"
  for r in $roots; do
    [ "$first" = "$r" ] && return 0
  done
  return 1
}

# Маркер владельца: 0 — принимается, иначе печатает причину. $1 kind, $2 id, $3 ветка,
# $4 sha (необязателен; по умолчанию HEAD). Логика — SPEC §6/§9.
planning_marker_problem() {
  local kind="$1" id="$2" branch="$3" sha="${4:-}" file data k v head
  file=".claude/state/planning-owner-ok/${kind}-$(planning_enc "$id")@$(planning_enc "$branch")"
  if [ ! -f "$file" ]; then
    echo "только по слову владельца: попроси владельца выполнить .claude/scripts/planning-owner-ok.sh $kind $id"
    return 0
  fi
  while IFS= read -r line; do
    case "$line" in
      *=*) data="${data} ${line%%=*}=${line#*=}" ;;
    esac
  done < "$file"
  getv() { local want="$1" item; for item in $data; do case "$item" in "$want="*) printf '%s' "${item#*=}"; return 0;; esac; done; }
  [ "$(getv kind)" = "$kind" ] && [ "$(getv id)" = "$id" ] && [ "$(getv branch)" = "$branch" ] || {
    echo "маркер не относится к этой операции или ветке"; return 0; }
  [ "$(getv target)" = "$MAIN_BRANCH" ] || { echo "маркер выдан не для ветки $MAIN_BRANCH"; return 0; }
  v="$(getv ttl_until)"
  case "$v" in ''|*[!0-9]*) echo "у маркера нет срока ttl_until"; return 0 ;; esac
  [ "$(date +%s)" -le "$v" ] || { echo "разрешение владельца истекло (TTL $OWNER_OK_TTL_HOURS ч)"; return 0; }
  [ -n "$sha" ] || sha="$(git rev-parse HEAD 2>/dev/null || true)"
  [ -n "$sha" ] && [ "$(getv sha)" = "$sha" ] || { echo "после выдачи разрешения ветка изменилась (вершина не совпала)"; return 0; }
  return 1
}

planning_load_conf() {
  PLANNING_ROOT="${PLANNING_ROOT:-$(planning_root)}"

  # Дефолты (SPEC п.4) — действуют, если конфига нет или ключ в нём не задан.
  MAIN_BRANCH=main
  CODE_ROOTS="app src lib"
  FEATURE_BRANCH_RE='^feature/PLAN-([0-9]+(\.[0-9]+)*)(?:-|$)'
  HOTFIX_BRANCH_RE='^hotfix/'
  TOKEN_REQUIRED=on
  PLAN_SUMMARY_MIN_NUMBER=1
  PLAN_WARN_BYTES=40960
  PLAN_HARD_BYTES=81920
  DRIFT_HORIZON_DAYS=90
  DRIFT_MEMORY_INDEX=
  OWNER_OK_TTL_HOURS=24
  PLANNING_ROOT_ALLOWED="ROADMAP.md ACTIVE_PLANS.md PLANS.md HOTFIXES.md README.md plans roadmap hotfixes"
  STRICT=on
  PROTECTED_PATHS=".claude/hooks/ .claude/scripts/ .claude/settings.json .claude/planning.conf .githooks/ AGENTS.md .codex/"
  CODE_FILES="Makefile package.json pyproject.toml go.mod go.sum Cargo.toml composer.json requirements.txt"
  GATE_FAST=
  GATE_MERGE=

  local conf="$PLANNING_ROOT/.claude/planning.conf"
  if [ -f "$conf" ]; then
    # shellcheck disable=SC1090
    . "$conf" || true
  fi

  # Пустой/битый конфиг не должен ронять хуки: приводим значения к безопасным.
  case "${MAIN_BRANCH:-}" in
    ''|*[!A-Za-z0-9._/-]*) MAIN_BRANCH=main ;;
  esac
  [ -n "${FEATURE_BRANCH_RE:-}" ] || FEATURE_BRANCH_RE='^feature/PLAN-([0-9]+(\.[0-9]+)*)(?:-|$)'
  [ -n "${HOTFIX_BRANCH_RE:-}" ] || HOTFIX_BRANCH_RE='^hotfix/'
  case "${TOKEN_REQUIRED:-}" in
    off|OFF|0|false|no) TOKEN_REQUIRED=off ;;
    *) TOKEN_REQUIRED=on ;;
  esac
  [ -n "${PLANNING_ROOT_ALLOWED:-}" ] || PLANNING_ROOT_ALLOWED="ROADMAP.md ACTIVE_PLANS.md PLANS.md HOTFIXES.md README.md plans roadmap hotfixes"
  case "${STRICT:-on}" in
    off|OFF|0|false|no) STRICT=off ;;
    *) STRICT=on ;;
  esac
  PLAN_SUMMARY_MIN_NUMBER="$(planning_int "${PLAN_SUMMARY_MIN_NUMBER:-}" 1)"
  PLAN_WARN_BYTES="$(planning_int "${PLAN_WARN_BYTES:-}" 40960)"
  PLAN_HARD_BYTES="$(planning_int "${PLAN_HARD_BYTES:-}" 81920)"
  DRIFT_HORIZON_DAYS="$(planning_int "${DRIFT_HORIZON_DAYS:-}" 90)"
  OWNER_OK_TTL_HOURS="$(planning_int "${OWNER_OK_TTL_HOURS:-}" 24 1)"

  export PLANNING_ROOT MAIN_BRANCH CODE_ROOTS FEATURE_BRANCH_RE HOTFIX_BRANCH_RE TOKEN_REQUIRED
  export PLAN_SUMMARY_MIN_NUMBER PLAN_WARN_BYTES PLAN_HARD_BYTES DRIFT_HORIZON_DAYS
  export DRIFT_MEMORY_INDEX OWNER_OK_TTL_HOURS PLANNING_ROOT_ALLOWED
  export STRICT PROTECTED_PATHS CODE_FILES GATE_FAST GATE_MERGE
}
