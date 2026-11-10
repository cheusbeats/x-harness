# Планировочный профиль x-harness — контракт (SPEC)

Статус: рабочий документ для реализации. Источник истины по интерфейсам профиля.
Цель: `./install.sh --profile planning` ставит в ЛЮБОЙ git-проект только слой управления
планами (RM/PLAN/HF, роадмап, планы, хотфиксы) — без Laravel-гейтов, `.ai`, `.mcp.json`,
`harness/CLAUDE.md` и прочей специфики Laravel-профиля. `harness/` не меняется (snapshot остаётся
побайтовой копией payload; MANIFEST.sha256 не перегенерируется).

## 1. Границы

- Профиль ставит: `AGENTS.md`, `planning/README.md`, `.claude/{settings.json,planning.conf,scripts/,hooks/}`,
  `.githooks/`, skill `x-harness-planning` (если `--skills` не `none`).
- `install.sh` дополнительно создаёт `.claude/state/.gitignore` (маркеры owner-ok и `registry.lock` —
  локальное состояние, в коммит не попадают) и генерирует `.claude/planning.conf`.
- Из `harness/` берутся ТОЛЬКО: `.claude/scripts/registry.sh`, `.claude/scripts/install-githooks.sh`,
  `.codex/hooks/claude-compat.py` (если выбран клиент codex).
- Не ставится: `.ai/`, `.mcp.json`, `boost.json`, `CLAUDE.md`, `harness/CLAUDE.md`, Laravel-хуки,
  агенты/навыки полного профиля, `quality-gate`, `merge-gate`, `commit-gate`, `branch-guard`, `big-read-guard`.
- `harness/` и `MANIFEST.sha256` не редактируются.

## 2. Файлы профиля (`profiles/planning/`)

Runtime (владелец A):

    .claude/planning.conf.template      # шаблон; install.sh подставит MAIN_BRANCH/CODE_ROOTS
    .claude/settings.json               # только SessionStart drift + PreToolUse registry-guard/owner-ok-guard
    .claude/scripts/planning-init.sh    # идемпотентно создаёт индексы/каталоги
    .claude/scripts/planning-lib.sh     # загрузка .claude/planning.conf + дефолты
    .claude/scripts/planning-owner-ok.sh
    .claude/scripts/plan-code-refs.sh   # портативная версия (CODE_ROOTS из conf)
    .claude/hooks/plans-drift.sh
    .claude/hooks/registry-guard.sh
    .claude/hooks/owner-ok-guard.sh
    .claude/hooks/planning-checks.py    # pre-commit checks + commit-msg token
    .githooks/commit-msg
    .githooks/pre-commit
    .githooks/pre-push

Документы/установка (владелец B):

    AGENTS.md                  # ставится в корень проекта; краткие правила работы с планами
    planning/README.md         # ставится в planning/README.md; правила реестров без констант Laravel-профиля
    README.md                  # документация профиля в упаковке
    skill/SKILL.md             # skill x-harness-planning (frontmatter name/description)

Тесты (владелец C): `tests/acceptance-planning.sh` + обновление `tests/acceptance.sh`.

## 3. CLI

    ./install.sh --project DIR --profile planning [--clients auto|all|claude,codex,dsh,generic|none]
                 [--skills auto|project|global|both|none] [--force] [--dry-run] [--no-verify]
                 [--dsh-hooks none|bridge|community] [--dsh-profile NAME] [--dsh-version VER]

- `--profile` новый; значения `full` (по умолчанию, текущее поведение) и `planning`.
- `planning` + `--mode`: `--mode` игнорируется (профиль всегда port-совместим).
- Конфликты (фактически): без `--force` при существующих `.claude`, `.githooks`, `AGENTS.md`,
  `planning/README.md`, а при `--clients codex` — ещё `.codex/hooks.json` и
  `.codex/hooks/claude-compat.py` — ошибка; с `--force` backup в `.x-harness-backup.<TS>/`.
  Чужой `planning/` (реестры) не перезаписывается: профиль ставит только `planning/README.md`.
  Существующие `.agents`/`.dsh` целиком не трогаются; навык `x-harness-planning` — по правилу `--force`.
- После копирования: сгенерировать `.claude/planning.conf`, подключить `core.hooksPath=.githooks`,
  выполнить `planning-init.sh`, затем `verify.sh --profile planning --project DIR` (если не `--no-verify`).

## 4. `.claude/planning.conf` (shell-совместимый KEY=VALUE)

    MAIN_BRANCH=main
    CODE_ROOTS="app src lib"                 # install.sh подставляет найденные каталоги
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

Все хуки обязаны работать и без файла (дефолты выше).

Пустой `CODE_ROOTS` (или ни одного существующего каталога из списка) включает автодетект
каталогов первого уровня по `git ls-files` (кроме `.*`, `planning`, `node_modules`, `vendor`).
`DRIFT_MEMORY_INDEX=` (пусто) выключает проверку памяти; заданный путь проверяется на существование.

## 5. Инварианты и семантика (как в полном профиле)

- Индексы `planning/{ROADMAP,ACTIVE_PLANS,PLANS,HOTFIXES}.md` правит только `registry.sh`;
  `registry-guard` блокирует Edit/Write по ним (exit 2).
- `planning-init.sh` создаёт недостающие индексы с шапками таблиц, каталоги
  `roadmap/ plans/ plans/closed/ hotfixes/` и `.gitkeep`; существующее не перезаписывает.
  Благодаря `plans/closed/` `registry.sh check` перестаёт молча пропускать PLAN.
- `registry.sh add PLAN|HF|RM auto "..."` — единственный способ завести запись.
- Статусы (словарь registry.sh): RM — идея/отложена/стала PLAN-N/отклонена;
  PLAN — черновик/в работе/на паузе/ждёт владельца/закрыт/аннулирован; HF — влит/откачен.
- Закрытие плана: тело `planning/plans/closed/PLAN-N.md` + `registry.sh set-status PLAN-N закрыт`.
  Новый RM и закрытие плана — только при маркере владельца (см. п.6).
- Коммит: conventional + токен `PLAN-N` (ветка `feature/PLAN-N-*`) или `HF-M` (`hotfix/*`);
  на `MAIN_BRANCH` токен не требуется (мерж-коммиты). Коммит только по
  `planning/roadmap/**`/`ROADMAP.md` может нести `RM-N`.
- `plans-drift.sh` — информатор (exit 0). Фактически проверяет: (1) код-коммит по `CODE_ROOTS`
  с токеном новее последнего упоминания токена в индексах (или токена там нет) → «план отстал»;
  (2) `PLAN-N` в коде без строки индекса и тела плана; (3) `HF-M` в коде без строки в `HOTFIXES.md`;
  (4) код-коммиты после последней правки `HOTFIXES.md` без токена — кандидаты в журнал;
  (5) лишнее в корне `planning/` относительно `PLANNING_ROOT_ALLOWED`; (6) не подключены git-хуки
  (`core.hooksPath != .githooks`); (7) заданный `DRIFT_MEMORY_INDEX` не существует. Бюджета
  стартового набора нет.

## 6. owner-ok (портативный)

    .claude/scripts/planning-owner-ok.sh close-plan PLAN-N [ветка]
    .claude/scripts/planning-owner-ok.sh rm-add RM-N [ветка]

Маркер: `.claude/state/planning-owner-ok/<kind>-<enc(id)>@<enc(branch)>` с key=value
(kind,id,branch,sha,ttl_until,target). Владелец запускает САМ в терминале; агент — нет
(`owner-ok-guard.sh` блокирует Bash с запуском скрипта или записью в state).
`planning-checks.py staged` требует маркер: `close-plan PLAN-N` при добавлении
`planning/plans/closed/PLAN-N.md`; `rm-add RM-N` при добавлении `planning/roadmap/RM-N-*.md`
или новой строки RM в ROADMAP.md. Маркер валиден: `target==MAIN_BRANCH`, `sha==HEAD`,
не старше `OWNER_OK_TTL_HOURS`, ветка совпадает.

## 7. Коды выхода и устойчивость

- Claude/Codex-хуки: exit 2 = блокировка (stderr — причина). Git-хуки: exit 1 = блокировка.
- `plans-drift.sh` всегда exit 0.
- Внутренняя ошибка хука не должна парализовать владельца: неразобранный ввод → fail-open
  с сообщением в stderr; авторитетная проверка — git-хук pre-commit.
- Требования: bash, git, python3, jq (только для PreToolUse-хуков; если jq нет — не блокировать).

## 8. Приёмка (C)

`tests/acceptance-planning.sh` на временном НЕ-Laravel git-репозитории (8 шагов):
1. install `--profile planning --clients none --skills none`; состав, отсутствие лишнего,
   `core.hooksPath=.githooks`, отсутствие констант Laravel-профиля в установленном слое;
2. `registry.sh check` чист; `planning-init.sh` идемпотентен (sha256 индексов до/после);
3. add PLAN/HF/RM; ветка `feature/PLAN-1-*`; коммит с токеном проходит, без токена — блокируется
   (и commit-msg напрямую, и `git commit`, HEAD не сдвигается);
4. прямой Edit индекса (JSON в registry-guard) — exit 2, тело плана — exit 0;
5. RM-коммит без маркера — блок; после `planning-owner-ok.sh rm-add RM-N` — проходит;
   `owner-ok-guard` на запуске скрипта — exit 2;
6. закрытие плана: без маркера — блок, с `close-plan` — проходит; `registry.sh check` чист;
7. drift видит код-коммит с токеном при активном плане; после обновления индекса — не видит;
8. `verify.sh --profile planning --project DIR` = OK; повторная установка без `--force` — ошибка,
   с `--force` — backup `.x-harness-backup.*`.


## 9. Строгий слой (STRICT=on по умолчанию)

Цель: в planning-профиле работают те же барьеры дисциплины, что в полном профиле, но без Laravel:
E2 (ветки), E18 (защищённые пути), E16 (обход хуков), защита main (коммит/мерж/пуш),
Quality Gate по командам проекта. Отключается только `STRICT=off` в `planning.conf`.

Новые ключи conf (дефолты):

    STRICT=on
    PROTECTED_PATHS=".claude/hooks/ .claude/scripts/ .claude/settings.json .claude/planning.conf .githooks/ AGENTS.md .codex/"
    CODE_FILES="Makefile package.json pyproject.toml go.mod go.sum Cargo.toml composer.json requirements.txt"
    GATE_FAST=
    GATE_MERGE=

Новые хуки (Claude settings.json, Codex hooks.json, DSH-мост, generic — git-хуки):
- `branch-guard.sh` — PreToolUse Edit|Write|NotebookEdit: E2/E18. На `MAIN_BRANCH` правки запрещены
  (кроме merge/rebase/cherry-pick), на `feature/PLAN-N-*`/`hotfix/*` разрешены, на прочих ветках —
  только `planning/`, `docs/`, `*.md` и не-код. Правка `PROTECTED_PATHS` требует маркер `hooks-edit`.
- `commit-gate.sh` — PreToolUse Bash: `git commit` на `MAIN_BRANCH`/не-conventional ветке, `--no-verify`,
  `-n`, `-c core.hooksPath=…`, `GIT_CONFIG_KEY_n=core.hooksPath`, `git config core.hooksPath …` — блок.
- `merge-gate.sh` — PreToolUse Bash: мерж в `MAIN_BRANCH` только из `feature/PLAN-N-*`/`hotfix/*`,
  все коммиты ветки несут токен, реестры чисты, маркер владельца `merge <ветка>`, `GATE_MERGE` задан и пройден; отметка соответствует HEAD и хешу команды. Иначе exit 2.
- `main-push-guard.sh` — PreToolUse Bash: force/delete/`+`/`--all`/`--mirror`, push в main из не-main,
  прямые (не-мерж) коммиты впереди `<remote>/main` или недоступный remote — блок.
- `owner-ok-guard.sh` — блок запуска `planning-owner-ok.sh` и записи в `.claude/state/planning-owner-ok`.
- `registry-guard.sh`, `plans-drift.sh` — без изменений.

owner-ok добавляет виды:

    .claude/scripts/planning-owner-ok.sh hooks-edit <ветка>   # E18: правка хуков/настроек/AGENTS
    .claude/scripts/planning-owner-ok.sh merge <ветка>        # мерж этой ветки в MAIN_BRANCH

Правила приёма прежние: kind/id/branch, target==MAIN_BRANCH, sha==HEAD, TTL. Маркер `merge`
привязан к вершине ИСХОДНОЙ ветки; `hooks-edit` — к вершине текущей ветки.

Git-хуки (авторитетный слой, работает без событийных хуков):
- `pre-commit`: `planning-checks.py staged` добавляет E2 (код — только `feature/PLAN-N-*`/`hotfix/*`;
  на `MAIN_BRANCH` код запрещён, planning/docs разрешены, кроме merge/rebase/cherry-pick) и E18
  (`PROTECTED_PATHS` — только с маркером `hooks-edit`); затем `registry.sh check` по staged-дереву
  и `GATE_FAST` обязателен при STRICT=on.
- `pre-push`: non-fast-forward (force), удаление main, push в main из не-main, прямые коммиты
  впереди удалённого main — блок (E19-лайт). Теги не трогаются.
- `commit-msg` — без изменений.

Quality Gate (портативный, `.claude/scripts/quality-gate.sh [--fast|--merge]`):
- `--fast` выполняет `GATE_FAST` через `bash -c` в корне проекта; пусто при STRICT=on — ошибка;
- `--merge` выполняет `GATE_MERGE`, при чистом дереве пишет
  `.claude/state/gates/<branch>.merge-passed` с HEAD и хешем команды; пустой GATE_MERGE или падение — exit 1.
- `bin/xh gate [--fast|--merge]` — та же команда для generic-агентов.

Классификация кода (E2): путь под `CODE_ROOTS` (первый сегмент) или корневой файл из `CODE_FILES`.
`planning/`, `docs/`, `wiki/`, `*.md` и `PROTECTED_PATHS` — не код.

Клиенты: Claude — `settings.json`; Codex — `.codex/hooks.json` через `claude-compat.py`;
DSH — мост из `settings.json`; generic — git-хуки + `bin/xh`. Событийные хуки — ранняя блокировка,
git-хуки — авторитетная.

Приёмка (строгая, `tests/acceptance-strict.sh`, вызывается из `tests/acceptance.sh`, 8 шагов):
1. install + наличие strict-файлов, conf-ключей и settings.json со всеми хуками;
2. branch-guard: правка `src/` и индекса planning на main → 2; на feature/PLAN-1 → 0;
   защищённый путь без `hooks-edit` → 2;
3. commit-gate: коммит на main → 2; `--no-verify`/core.hooksPath → 2; feature/PLAN-1 с токеном → 0;
4. E18: коммит правки `.claude/hooks/` без маркера — блок; после `hooks-edit` — проходит;
5. merge-gate: bare remote, ветка feature/PLAN-2; без `merge`-маркера → 2; с маркером и чистыми
   реестрами → 0; `GATE_MERGE=false` → quality-gate rc1 и merge-gate rc2;
6. main-push-guard + git pre-push: прямой коммит в main и force push → блок, remote не сдвигается;
   push feature → 0;
7. кросс-агентные конфиги: Codex `.codex/hooks.json`, DSH community и bridge (фейковый dsh) содержат
   branch-guard/commit-gate/merge-gate/main-push-guard/owner-ok-guard/registry-guard;
8. `bin/xh gate --fast` (пусто → 0, `false` → 1) и `bin/xh merge-ready` без маркера → rc≠0.

## 10. Запреты для исполнителей

- Не менять `harness/`, `MANIFEST.sha256`, `install.sh`, `verify.sh`, `bin/xh` (кроме владельца
  соответствующего файла), чужие файлы из п.2.
- Не коммитить в x-harness (git-репозиторий пакета пуст; коммиты — отдельное решение владельца).
- Не запускать `install.sh` в корень x-harness; все прогоны — во временных каталогах.
- Не добавлять Laravel/PHP-константы (`<project>-horizon-1`, `/var/www/html`, `app_dusk`,
  `app resources routes database config tests`, абсолютные пути хоста).

**Граница Git-хуков:** в клиентах без PreToolUse нативные Git-хуки не гарантируют проверку owner-ok и гейта при `git merge`, в том числе fast-forward. Перед мержем запускайте `merge-ready` и вручную проверяйте условия; для принуждения используйте серверную защиту.
