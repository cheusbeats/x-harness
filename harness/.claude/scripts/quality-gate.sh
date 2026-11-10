#!/usr/bin/env bash
# Quality Gate — исполняемая версия правила из CLAUDE.md:
# «перед каждым тестом и перед каждым коммитом — Larastan; Pint перед сдачей».
# Быстрые проверки идут все, чтобы показать все находки сразу; долгие шаги (PHPUnit, Dusk) после первого
# падения не запускаются. Код выхода ненулевой при любом падении.
#
# Запуск: .claude/scripts/quality-gate.sh [--fast|--merge]
#   --fast  — пропустить полный прогон тестов (быстрая проверка в процессе работы)
#   --merge — добавить Dusk: полный чеклист перед мержем ветки в main. Dusk (и npm run build под него)
#             пропускается, если `git diff main...HEAD` трогает только документы/служебные пути
#             (см. dusk_needed); любой путь вне белого списка или ошибка diff — Dusk идёт как обычно.
#   --dusk-plan — только напечатать решение «dusk: run|skip (причина)» и выйти (для тестов)
#
# Dusk НЕ входит в обычный прогон намеренно: он работает по своим БД app_dusk_N и
# truncate'ит их. Автоматически по хуку такое запускать нельзя, поэтому merge-чеклист
# запускается руками: .claude/scripts/quality-gate.sh --merge
#
# PHP-шаги идут через контейнер horizon: sail-сервис laravel.test не всегда держит
# порт 80 (конфликт с другими проектами), horizon поднят всегда. npm — на хосте,
# внутри контейнера node_modules с linux-биндингами (см. planning + memory).

set -uo pipefail

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}" || exit 1

# Имя compose-проекта: COMPOSE_PROJECT_NAME или имя основного чекаута (как у docker compose).
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')}"
CONTAINER="$COMPOSE_PROJECT-horizon-1"
FAST=0
MERGE=0
[ "${1:-}" = "--fast" ] && FAST=1
[ "${1:-}" = "--merge" ] && MERGE=1

FAILED=""
# Отметка полного гейта — только за тот коммит, с которого прогон начался.
GATE_HEAD="$(git rev-parse HEAD)"

# Нужен ли Dusk: «skip», только если ветка относительно main трогает исключительно белый список
# (planning/, .claude/, .githooks/, .codex/, .agents/, любые *.md). Fail closed: ошибка diff,
# пустой diff или любой иной путь — «run». --no-renames: переименование показывает и старый путь.
dusk_needed() {
  local files bad rc
  if ! files="$(git diff --no-renames --name-only main...HEAD 2>/dev/null)" || [ -z "$files" ]; then
    echo "run (diff main...HEAD недоступен или пуст)"; return 0
  fi
  # grep: rc 0 — есть путь вне белого списка, 1 — все пути в списке; rc >= 2 — сбой самого фильтра, решать нельзя.
  bad="$(printf '%s\n' "$files" | grep -Ev '^(planning/|\.claude/|\.githooks/|\.codex/|\.agents/)|\.md$')"
  rc=$?
  if [ "$rc" -ge 2 ]; then
    echo "run (сбой фильтра путей, rc=$rc)"; return 0
  fi
  if [ -n "$bad" ]; then
    echo "run (код вне белого списка: $bad)"; return 0
  fi
  echo "skip (diff main...HEAD — только planning/.claude/.githooks/.codex/.agents/*.md)"
}
if [ "${1:-}" = "--dusk-plan" ]; then printf 'dusk: %s\n' "$(dusk_needed)"; exit 0; fi

# Контейнер монтирует основной чекаут в /var/www/html; worktree лежит внутри
# него (.claude/worktrees/*), поэтому гейт обязан работать в пути worktree —
# иначе из worktree он проверяет чужой код основного чекаута.
COMMON_DIR="$(git rev-parse --path-format=absolute --git-common-dir)" || exit 1
MAIN_ROOT="$(dirname "$COMMON_DIR")"
CONTAINER_DIR="/var/www/html${PWD#"$MAIN_ROOT"}"
if [ "$PWD" != "$MAIN_ROOT" ] && [ ! -d vendor ]; then
  echo "[gate] в worktree нет vendor/: cp -c -R \"$MAIN_ROOT/vendor\" vendor" >&2
  exit 1
fi

php_exec() {
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"; then
    # Xdebug в horizon замедляет тесты примерно на четверть, в гейте он не нужен.
    docker exec -e XDEBUG_MODE=off -w "$CONTAINER_DIR" "$CONTAINER" "$@"
  else
    vendor/bin/sail "$@"
  fi
}

step() {
  local name="$1"; shift
  printf '\n[gate] %s\n' "$name"
  if "$@"; then
    return 0
  fi
  FAILED="${FAILED}${FAILED:+, }${name}"
  return 1
}

step "Larastan"  php_exec php vendor/bin/phpstan analyse --no-progress
step "Site-page slugs" php_exec php artisan site-pages:check-slugs
# `.git` worktree указывает на путь хоста, которого нет в контейнере: без явных путей `pint --dirty` падает.
GIT_DIR_ABS="$(git rev-parse --absolute-git-dir)"
step "Pint"      php_exec env GIT_DIR="/var/www/html${GIT_DIR_ABS#"$MAIN_ROOT"}" GIT_WORK_TREE="$CONTAINER_DIR" vendor/bin/pint --dirty --format agent

# eslint — на хосте: node_modules собран под macOS
if [ -d node_modules ]; then
  step "eslint" npm run lint --silent
else
  printf '\n[gate] eslint пропущен — нет node_modules\n'
fi

# Наши скиллы живут в .ai/skills, а .claude/skills/<имя> — СИМЛИНК на них (так их
# заводит boost). Копия вместо симлинка = два расходящихся источника правды: ровно
# это и случилось, когда субагент продублировал UI-скилл, а boost:update
# молча вернул симлинк. Проверяем инвариант, а не равенство файла самому себе.
if [ -d .ai/skills ] && [ -d .claude/skills ]; then
  symlink_check() {
    local s rc=0
    for s in .ai/skills/*/; do
      s="$(basename "$s")"
      if [ ! -e ".claude/skills/$s" ]; then
        echo ".claude/skills/$s отсутствует"; rc=1
      elif [ ! -L ".claude/skills/$s" ]; then
        echo ".claude/skills/$s — копия, а должен быть симлинк на ../../.ai/skills/$s"; rc=1
      fi
    done
    return $rc
  }
  step "skills: симлинки, не копии" symlink_check
fi

# Долгие шаги — после быстрых и только если быстрые прошли: ждать PHPUnit и Dusk при уже известном падении незачем.
long_step() {
  if [ -n "$FAILED" ]; then
    printf '\n[gate] %s пропущен: уже есть падение (%s)\n' "$1" "$FAILED"
    return 1
  fi
  if ! take_gate_lock; then
    FAILED="очередь гейта"
    return 1
  fi
  step "$@"
}

# Долгие шаги двух гейтов разом мешают друг другу: общие базы testing_*, ложные таймауты браузера под
# нагрузкой. Второй гейт ждёт очереди. Замок один на основной чекаут и все worktree; зависший (после
# SIGKILL) снимает человек.
GATE_LOCK="$MAIN_ROOT/storage/app/quality-gate.lock"
GATE_LOCK_HELD=0
take_gate_lock() {
  [ "$GATE_LOCK_HELD" -eq 0 ] || return 0
  local waited=0
  until mkdir "$GATE_LOCK" 2>/dev/null; do
    [ "$waited" -gt 0 ] || printf '\n[gate] другой гейт гоняет долгие шаги, жду очереди. Если гейт никто не гоняет: rm -rf %s\n' "$GATE_LOCK"
    if [ "$waited" -ge 3600 ]; then
      printf '[gate] очереди нет час\n' >&2
      return 1
    fi
    sleep 10
    waited=$((waited + 10))
  done
  GATE_LOCK_HELD=1
  trap 'rm -rf "$GATE_LOCK"' EXIT
  trap 'exit 130' INT TERM
}

if [ "$FAST" -eq 0 ]; then
  # Parallel (paratest): one testing_test_N database per process. 8 processes need Postgres max_connections=200
  # (compose.yaml), next to the dev app (~40). GATE_PHPUNIT_PROCESSES overrides.
  # Race tests (group serial-db) commit real rows to the shared `testing` DB — they run after, sequentially.
  long_step "PHPUnit" php_exec php artisan test --compact --parallel --processes="${GATE_PHPUNIT_PROCESSES:-8}" --exclude-group=serial-db
  long_step "PHPUnit (serial DB)" php_exec php artisan test --compact --group=serial-db
fi

# Dusk — только в merge-режиме: свои БД app_dusk_N, которые он truncate'ит; шарды — dusk-shards.sh.
# Перед ним обязательно npm run build НА ХОСТЕ: браузер в контейнере не достаёт
# до vite dev-сервера на хосте, поэтому Dusk всегда работает с public/build —
# без пересборки он проверял бы вчерашний бандл (см. DuskTestCase::prepare).
if [ "$MERGE" -eq 1 ]; then
  DUSK_PLAN="$(dusk_needed)"
  if [ "${DUSK_PLAN%% *}" = "skip" ]; then
    printf '\n[gate] Dusk и npm run build пропущены: %s\n' "${DUSK_PLAN#skip }"
  else
    printf '\n[gate] Dusk идёт: %s\n' "${DUSK_PLAN#run }"
    if [ -d node_modules ]; then
      long_step "npm run build (для Dusk)" npm run build --silent
    else
      # Отметка гейта общая на репозиторий (HF-177): worktree без node_modules не должен дать её без eslint и свежей сборки.
      printf '\n[gate] нет node_modules: eslint и npm run build не выполнены\n'
      FAILED="${FAILED}${FAILED:+, }нет node_modules"
    fi
    long_step "Dusk" "$(dirname "${BASH_SOURCE[0]}")/dusk-shards.sh"
  fi
fi

if [ -n "$FAILED" ]; then
  printf '\n[gate] ПАДЕНИЕ: %s\n' "$FAILED" >&2
  exit 1
fi

printf '\n[gate] всё зелёное\n'

# Пропуск для merge-gate.sh: полный гейт (--merge) зелёный именно на этой вершине ветки.
# Только при чистом дереве отслеживаемых файлов — иначе проверялся не тот код, что уйдёт в коммит.
if [ "$MERGE" -eq 1 ]; then
  branch="$(git rev-parse --abbrev-ref HEAD)"
  if git diff --quiet HEAD -- && [ "$branch" != "HEAD" ] && [ "$(git rev-parse HEAD)" = "$GATE_HEAD" ]; then
    # Общая на репозиторий: merge-gate читает отметку из основного чекаута, откуда бы ни шёл гейт (HF-177).
    mkdir -p "$MAIN_ROOT/.claude/state/gates"
    printf '%s\n' "$GATE_HEAD" > "$MAIN_ROOT/.claude/state/gates/$(printf '%s' "$branch" | tr '/' '_').merge-passed"
    printf '[gate] отметка полного гейта: %s @ %s\n' "$branch" "$(git rev-parse --short HEAD)"
  else
    printf '[gate] отметка полного гейта НЕ записана: есть незакоммиченные изменения или за время прогона появился коммит\n'
  fi
fi
