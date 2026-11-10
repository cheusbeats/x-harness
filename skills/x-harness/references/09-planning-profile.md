# 09. Планировочный профиль x-harness (`--profile planning`)

Подробная документация профиля: что ставится, как устроено, строгий слой, какие команды и ограничения.
Контракт реализации — [../profiles/planning/SPEC.md](../../../profiles/planning/SPEC.md); краткая документация
для потребителя пакета — [../profiles/planning/README.md](../../../profiles/planning/README.md). Установка
пакета целиком и клиентские обвязки — [08-install-and-acceptance.md](08-install-and-acceptance.md);
правила реестров — [01-planning-registries.md](01-planning-registries.md).

Статус: профиль добавляет к пакету отдельную сборку; `harness/` и `MANIFEST.sha256` не меняются.

## 1. Назначение и границы

Профиль ставит в **любой** git-проект слой управления планами: `planning/` с реестрами
RM/PLAN/HF, правила для агента, слово владельца, git-хуки и строгую дисциплину (E2/E18/E16,
защита `main`, Quality Gate по командам проекта). Ничего Laravel-специфичного в нём нет: ни Sail/Docker,
ни Larastan/Pint/PHPUnit, ни money-paths, ни констант Laravel-профиля (имя контейнера, серверные пути, тестовые БД,
пути macOS).

Границы:

- **Ставится:** `AGENTS.md`, `planning/README.md`, `.claude/{settings.json,planning.conf,scripts/,hooks/}`,
  `.githooks/`, skill `x-harness-planning` (если `--skills` не `none`). Установщик также создаёт
  `.claude/state/.gitignore`.
- **Берётся из `harness/`:** только `.claude/scripts/registry.sh`,
  `.claude/scripts/install-githooks.sh` и `.codex/hooks/claude-compat.py` (если выбран клиент codex).
- **Не ставится:** `.ai/`, `.mcp.json`, `boost.json`, `CLAUDE.md`, `harness/CLAUDE.md`, полные
  версии гейтов Laravel-профиля и хуков (Laravel `quality-gate`, `merge_checks.py`, `commit_checks.py`,
  money-paths, `paths.conf`, `big-read-guard`), агенты и навыки полного профиля. Свои строгие guard'ы профиль
  ставит отдельно (раздел 7) — они портативные, без Laravel.
- Профиль всегда port-совместим: `--mode` для него игнорируется, подменять константы Laravel-профиля нечего.

## 2. Архитектура

Та же трёхуровневая схема, что у полного пакета (08, раздел 1), но с планировочными и строгими
проверками:

1. **Текст правил** — `AGENTS.md` (старт с `planning/ACTIVE_PLANS.md`, реестры, strict, токены,
   owner-ok) и `planning/README.md` (что где, команды, статусы, шаблон плана, strict).
2. **Событийные хуки клиента** — `.claude/settings.json`: `SessionStart` → `plans-drift.sh`;
   `PreToolUse` → `branch-guard.sh`, `commit-gate.sh`, `merge-gate.sh`, `main-push-guard.sh`,
   `registry-guard.sh`, `owner-ok-guard.sh`. Работают нативно в Claude Code/Codex; DSH — через мост;
   generic — нет.
3. **Настоящие git-хуки** — `.githooks/{commit-msg,pre-commit,pre-push}` с логикой
   `.claude/hooks/planning-checks.py`, `strict-checks.py` и `.claude/scripts/registry.sh check`.
   Это авторитетная проверка в терминале; она не зависит от клиента.

Исходники профиля лежат в `profiles/planning/`; установщик раскладывает их по проекту. Runtime-файлы
(`.claude/**`, `.githooks/**`) пишутся в профиль отдельно от документов, но ссылки в правилах всегда
относятся к установленному проекту, а не к каталогу пакета.

### 2.1. Что появляется в проекте

| Путь | Роль |
|---|---|
| `AGENTS.md` | правила проекта для любого агента; единственный файл инструкций профиля |
| `planning/README.md` | правила реестров (что где, команды, статусы, шаблон, закрытие, strict) |
| `.claude/planning.conf` | параметры профиля (сгенерирован из `planning.conf.template`) |
| `.claude/settings.json` | проводка `SessionStart`/`PreToolUse` (включая строгие guard'ы) |
| `.claude/scripts/planning-init.sh` | идемпотентная инициализация `planning/` |
| `.claude/scripts/planning-lib.sh` | загрузка конфига и дефолтов |
| `.claude/scripts/install-githooks.sh` | подключение `core.hooksPath=.githooks` |
| `.claude/scripts/registry.sh` | правка индексов — единственный путь |
| `.claude/scripts/planning-owner-ok.sh` | маркеры владельца: `close-plan`, `rm-add`, `hooks-edit`, `merge` |
| `.claude/scripts/plan-code-refs.sh` | сверка ссылок плана с кодом |
| `.claude/scripts/quality-gate.sh` | `--fast` → `GATE_FAST`, `--merge` → `GATE_MERGE` |
| `.claude/scripts/merge-ready.sh` | сухой прогон требований мержа |
| `.claude/hooks/plans-drift.sh` | сверка реестров с git (информатор) |
| `.claude/hooks/registry-guard.sh` | блокировка Edit/Write по индексам |
| `.claude/hooks/owner-ok-guard.sh` | блокировка выдачи маркера агентом |
| `.claude/hooks/branch-guard.sh` | E2/E18: ветка и защищённые пути при правках |
| `.claude/hooks/commit-gate.sh` | E2/E16: коммиты на main, `--no-verify`, `core.hooksPath` |
| `.claude/hooks/merge-gate.sh` | мерж в main: ветка, токены, реестры, маркер `merge`, `GATE_MERGE` |
| `.claude/hooks/main-push-guard.sh` | force/delete/прямые коммиты в main |
| `.claude/hooks/strict-checks.py` | общая логика строгих guard'ов |
| `.claude/hooks/planning-checks.py` | проверки для git-хуков |
| `.githooks/*` | commit-msg, pre-commit, pre-push |
| `.claude/state/` | локальное состояние: маркеры owner-ok и `registry.lock`; `install.sh` создаёт `.claude/state/.gitignore`, содержимое не коммитится |
| `.claude/skills/`, `.agents/skills/`, `.dsh/skills/` | навык `x-harness-planning` (при `--skills`) |

## 3. Установка

```bash
./install.sh --project /path/to/project --profile planning
./install.sh --project /path/to/project --profile planning --clients none --skills none
./install.sh --project /path/to/project --profile planning --dry-run
```

Флаги: `--project`, `--profile full|planning`, `--clients auto|all|claude,codex,dsh,generic|none`,
`--skills auto|project|global|both|none`, `--force`, `--dry-run`, `--no-verify`, `--no-git`,
`--dsh-hooks none|bridge|community`, `--dsh-profile NAME`, `--dsh-version VER`.

Последовательность: копирование профиля → генерация `.claude/planning.conf` (`MAIN_BRANCH`, `CODE_ROOTS`,
`STRICT=on` и остальные ключи) → `core.hooksPath=.githooks` через
`.claude/scripts/install-githooks.sh` → `.claude/scripts/planning-init.sh` →
`verify.sh --profile planning --project DIR` (если не `--no-verify`).

Конфликты: без `--force` при существующих `.claude`, `.githooks`, `AGENTS.md`, `planning/README.md`
(при `--clients codex` — ещё `.codex/hooks.json` и `.codex/hooks/claude-compat.py`) — ошибка; с `--force`
эти пути перемещаются в `.x-harness-backup.<TS>/`. Существующий каталог `planning/` не перезаписывается,
заменяется только `README.md`; навык при совпадении без `--force` даёт предупреждение. Повторная
установка без `--force` — тоже ошибка; это защита, а не «идемпотентность».

`planning-init.sh` создаёт недостающие индексы (`ROADMAP.md`, `ACTIVE_PLANS.md`, `PLANS.md`,
`HOTFIXES.md`) с шапками таблиц, каталоги `roadmap/ plans/ plans/closed/ hotfixes/` и `.gitkeep`,
существующее не перезаписывает, в конце выполняет `registry.sh check --registry all`. Благодаря
`plans/closed/` проверка PLAN-реестра перестаёт молча пропускать планы.

`--no-git` разрешает проект без git, но тогда git-хуки не подключаются, и единственным принуждением
остаются ручные запуски скриптов.

## 4. `.claude/planning.conf`

Shell-совместимый `KEY=VALUE`, читается `planning-lib.sh`. Все хуки обязаны работать и без файла —
с теми же дефолтами.

| Ключ | Дефолт | Смысл |
|---|---|---|
| `MAIN_BRANCH` | `main` | основная ветка; на ней токен коммита не требуется, к ней привязаны маркеры owner-ok |
| `CODE_ROOTS` | `"app src lib"` | каталоги кода для `plans-drift`, `plan-code-refs` и классификации E2; пусто или ни одного существующего каталога — автодетект первого уровня по git (кроме `.*`, `planning`, `node_modules`, `vendor`) |
| `FEATURE_BRANCH_RE` | `^feature/PLAN-([0-9]+(\.[0-9]+)*)(?:-|$)` | шаблон плановой ветки, из него берётся `PLAN-N` |
| `HOTFIX_BRANCH_RE` | `^hotfix/` | шаблон хотфикс-ветки |
| `TOKEN_REQUIRED` | `on` | требовать ли токен `PLAN-N`/`HF-N` в коммитах на плановых/хотфикс-ветках |
| `PLAN_SUMMARY_MIN_NUMBER` | `1` | с какого номера плана обязателен `## Резюме` (1 — все планы) |
| `PLAN_WARN_BYTES` | `40960` | предупреждение о размере плана |
| `PLAN_HARD_BYTES` | `81920` | блокировка коммита плана этого размера (для номеров от `PLAN_SUMMARY_MIN_NUMBER`; меньшие — только предупреждение) |
| `DRIFT_HORIZON_DAYS` | `90` | окно поиска код-коммитов для `plans-drift` |
| `DRIFT_MEMORY_INDEX` | пусто | путь к файлу памяти, наличие которого проверяет drift; пусто — проверка выключена |
| `OWNER_OK_TTL_HOURS` | `24` | срок жизни маркера owner-ok |
| `PLANNING_ROOT_ALLOWED` | `"ROADMAP.md ACTIVE_PLANS.md PLANS.md HOTFIXES.md README.md plans roadmap hotfixes"` | допустимое содержимое корня `planning/` |
| `STRICT` | `on` | строгий слой (раздел 7); `off` — только словом владельца |
| `PROTECTED_PATHS` | `".claude/hooks/ .claude/scripts/ .claude/settings.json .claude/planning.conf .githooks/ AGENTS.md .codex/"` | пути, правимые только с маркером `hooks-edit` (E18) |
| `CODE_FILES` | `"Makefile package.json pyproject.toml go.mod go.sum Cargo.toml composer.json requirements.txt"` | корневые файлы, считающиеся кодом для E2 |
| `GATE_FAST` | пусто | команда перед коммитом; пусто при STRICT=on — блокировка |
| `GATE_MERGE` | пусто | команда перед мержем; пусто — мерж заблокирован |

Конфиг — настройка проекта, а не обход проверок. `MAIN_BRANCH` и `CODE_ROOTS` установщик подставляет
сам; `STRICT=off` — только решение владельца (файл в `PROTECTED_PATHS`).

## 5. Workflow PLAN / HF / RM

| Реестр | Индекс | Тело | Когда |
|---|---|---|---|
| RM — идея | `planning/ROADMAP.md` | `planning/roadmap/RM-N-*.md` | идея «потом», только по слову владельца |
| PLAN — план | `planning/ACTIVE_PLANS.md` (в работе), `planning/PLANS.md` (закрытые) | `planning/plans/PLAN-N-*.md`; закрытие — `plans/closed/PLAN-N.md` | есть что проектировать |
| HF — хотфикс | `planning/HOTFIXES.md` | `planning/hotfixes/HF-N-*.md` | багфикс, мелкая правка, конфиг |

Команды (все — `.claude/scripts/registry.sh`):

```bash
registry.sh next-id PLAN
registry.sh add PLAN PLAN-1 "Название" --slug nazvanie
registry.sh add HF auto "Что и зачем" --slug hotfix-fix
registry.sh add RM auto "Идея" --trigger "после PLAN-1" --slug idea
registry.sh set-status PLAN-1 "в работе"
registry.sh show PLAN-1
registry.sh check --registry all
```

Статусы (словарь `registry.sh`, полное совпадение): RM — `идея`, `отложена`, `стала PLAN-N`,
`отклонена`; PLAN — `черновик`, `в работе`, `на паузе`, `ждёт владельца`, `закрыт`, `аннулирован`;
HF — `влит`, `откачен`. Дата — `YYYY-MM-DD`, текст строки индекса (без колонки id) ≤ 160 символов.

Шаблон плана: H1 `# PLAN-N — название`, строка «Статус / ветка / дата», затем `## Резюме` (цель, что
меняем, решения, текущий статус). Строку про ветку/дату и содержание резюме пишет автор: `add PLAN`
создаёт только `**Статус:**` и пустой `## Резюме`. `pre-commit` проверяет наличие `## Резюме` (для
планов начиная с `PLAN_SUMMARY_MIN_NUMBER`) и размер плана, затем прогоняет `registry.sh check` по
staged-дереву; осознанный обход размера — `<!-- size-waiver: причина -->` в начале плана.

Перед закрытием `.claude/scripts/plan-code-refs.sh planning/plans/PLAN-N-*.md` должен быть пуст
(признанные расхождения — в разделе «Поправка по факту реализации»). Скрипт проверяет существование
файлов и членов (текстом по `CODE_ROOTS`), но не их использование; exit 0 при нормальном запуске,
2 — только на неверный вызов.

## 6. Слово владельца (owner-ok)

```bash
.claude/scripts/planning-owner-ok.sh close-plan PLAN-N [ветка]
.claude/scripts/planning-owner-ok.sh rm-add RM-N [ветка]
.claude/scripts/planning-owner-ok.sh hooks-edit <ветка>
.claude/scripts/planning-owner-ok.sh merge <ветка>
```

Маркер: `.claude/state/planning-owner-ok/<kind>-<enc(id)>@<enc(branch)>`; в имени `%`, `/`, `_`, `@`
кодируются (`%25`, `%2F`, `%5F`, `%40`). Содержимое — `key=value`: `kind`, `id`, `branch`, `sha`
(вершина ветки в момент выдачи), `ttl_until` (epoch), `target=MAIN_BRANCH`.

Маркер создаёт **только владелец в своём терминале**. Агент не запускает `planning-owner-ok.sh` и не
пишет в `.claude/state/planning-owner-ok/` — это блокирует `.claude/hooks/owner-ok-guard.sh` (Bash).
Маркер валиден, если совпали `kind`/`id`/`branch`, `target` равен `MAIN_BRANCH`, `sha` равен текущему
`HEAD`, а `ttl_until` не истёк. Новый коммит в ветку после выдачи отменяет маркер — выдавать заново.

Виды: `close-plan` (E10) и `rm-add` (E11) — базовый слой; `hooks-edit` (E18) и `merge` — строгий
(раздел 7). `planning-checks.py staged` требует `close-plan PLAN-N` при добавлении
`planning/plans/closed/PLAN-N.md` и `rm-add RM-N` при добавлении `planning/roadmap/RM-N-*.md` или новой
строки RM в `ROADMAP.md`. Для `hooks-edit` и `merge` id = имя ветки (совпадает с `branch`), файл —
`<kind>-<enc(ветка)>@<enc(ветка)>`; `merge`-маркер привязан к вершине ИСХОДНОЙ ветки, `hooks-edit` — к
вершине текущей. В портативном профиле маркер не захватывается атомарно и не расходуется: `merge-gate`
только проверяет его.

## 7. Строгий слой (STRICT=on по умолчанию)

Цель — в planning-профиле работают те же барьеры дисциплины, что в полном профиле, но без Laravel. Слой включён
по умолчанию; отключается **только** `STRICT=off` в `.claude/planning.conf` (файл защищён E18, правка —
по маркеру `hooks-edit`; это слово владельца, агент его себе не выдаёт).

### 7.1. Правила

| Правило | Суть | Чем принуждается |
|---|---|---|
| **E2** ветки | код (`CODE_ROOTS`, `CODE_FILES`) — только на `feature/PLAN-N-*`/`hotfix/*`; на `MAIN_BRANCH` правки кода и коммиты запрещены (`planning/`, `docs/`, `*.md` разрешены; merge/rebase/cherry-pick — исключение); на прочих ветках — только planning/docs/*.md/не-код | `branch-guard.sh` (ранняя блокировка), `pre-commit` (авторитетно) |
| **E18** защищённые пути | `PROTECTED_PATHS` — только с маркером `hooks-edit <ветка>` | `branch-guard.sh` (ранняя блокировка), `pre-commit` через `planning-checks.py staged` (авторитетно) |
| **E16** обходы | `--no-verify`, `-n`, `-c core.hooksPath=…`, `GIT_CONFIG_*`, `git config core.hooksPath …` запрещены | `commit-gate.sh` (Claude/Codex); правило для всех |
| **main: коммит** | коммит на `MAIN_BRANCH` агенту запрещён | `commit-gate.sh`, `pre-commit` |
| **main: мерж** | только из `feature/PLAN-N-*`/`hotfix/*`, все коммиты с токеном, реестры чисты, маркер владельца `merge <ветка>`, `GATE_MERGE` обязателен; обходные движения main (`cherry-pick`, `rebase`, `reset --hard`, `branch -f main`, `checkout -B main`) блокируются | `merge-gate.sh` |
| **main: пуш** | событийный `main-push-guard`: force/delete любого refspec, push main офлайн без `refs/remotes/<remote>/<MAIN_BRANCH>` (просит `git fetch`). Git `pre-push`: non-fast-forward любой ветки, удаление `MAIN_BRANCH`, push в main из не-main, прямые (не-мерж) коммиты впереди `<remote>/<MAIN_BRANCH>`; первый push main разрешён. Пуши `feature/*`, `hotfix/*` и теги проходят | `main-push-guard.sh` + git `pre-push` |
| **Quality Gate** | `GATE_FAST` перед коммитом, `GATE_MERGE` перед мержем; при STRICT=on пустые GATE_FAST и GATE_MERGE блокируют операцию | `.claude/scripts/quality-gate.sh --fast|--merge`; generic — `bin/xh gate` |

Классификация кода: путь под `CODE_ROOTS` (первый сегмент) или корневой файл из `CODE_FILES`;
`planning/`, `docs/`, `wiki/`, `*.md`, `PROTECTED_PATHS` — не код.

### 7.2. Quality Gate

`.claude/scripts/quality-gate.sh`:

- `--fast` выполняет `GATE_FAST` через `bash -c` в корне проекта; пусто при STRICT=on — ошибка;
- `--merge` выполняет `GATE_MERGE`; при чистом дереве пишет
  `.claude/state/gates/<ветка с / → _>.merge-passed` = полный `HEAD`; грязное дерево — предупреждение без
  отметки; падение — exit 1. `merge-gate` требует отметку при STRICT=on и сверяет её с
  вершиной мержимой ветки и хешем текущей команды.
- `bin/xh gate --fast|--merge` — та же команда для generic-агентов.

Это **не** Laravel Quality Gate: профиль не содержит Larastan/Pint/PHPUnit/Dusk и не выдаёт зелёный гейт
сам — он только исполняет команды, заданные проектом. При STRICT=on пустые `GATE_FAST` и `GATE_MERGE` блокируют операцию.

`merge-ready.sh <ветка>` — сухой прогон требований мержа: ветка, токены, чистые реестры, маркер
`merge`, `GATE_MERGE`; ничего не мержит и маркеры **не расходует** (атомарного захвата в портативном
профиле нет). `exit 0` = `READY`, в том числе `READY (кроме слов владельца)` — отсутствующий маркер
`merge` перечисляется отдельно; `exit 1` = `NOT READY` + причины. При `STRICT=off` печатает, что строгий
слой выключен, и выходит 0.

### 7.3. Кто что блокирует

| Слой | Claude Code | Codex | DSH | generic |
|---|---|---|---|---|
| Событийные хуки (branch/commit/merge/main-push/owner-ok/registry) | нативно (`.claude/settings.json`) | `.codex/hooks.json` + `claude-compat.py`, trust в `/hooks` | только мост (`--dsh-hooks`; subset событий) | — |
| Git-хуки `commit-msg`/`pre-commit`/`pre-push` | нативно | нативно | нативно | нативно |
| Quality Gate | `quality-gate.sh` / `commit-gate` | то же | то же | `bin/xh gate` |
| Кто блокирует раньше | событийный хук | событийный хук | мост | git-хук |

Событийные хуки — ранняя блокировка до выполнения действия; git-хуки — авторитетная проверка в
терминале. Без событийных хуков git-слой продолжает работать, `bin/xh` даёт ручной запуск.

### 7.4. `STRICT=off`

Отключает только владелец: `STRICT=off` в `.claude/planning.conf` (файл в `PROTECTED_PATHS`, правка —
по маркеру `hooks-edit`; агент маркер себе не выдаёт). Что меняется:

- `branch-guard`, `commit-gate`, `merge-gate`, `main-push-guard` пропускают действие (exit 0);
- `pre-commit` не применяет E2/E18 и не запускает `GATE_FAST`;
- `pre-push` не проверяет force/main-сценарии (остаётся проверка реестров по пушимому дереву);
- `merge-ready` сообщает, что строгий слой выключен (exit 0).

Базовый слой продолжает работать: индексы правит только `registry.sh`, `registry.sh check` в
`pre-commit`/`pre-push`, owner-ok для `close-plan`/`rm-add`, токен в `commit-msg`, `plans-drift`.
То есть `STRICT=off` — это «без E2/E18/E16/main/gate», а не «без реестров».

## 8. Drift и сверки

`.claude/hooks/plans-drift.sh` — `SessionStart`-информатор, **всегда exit 0**, при отсутствии находок
молчит. Сообщает:

- код-коммиты по `CODE_ROOTS` с токеном `PLAN-N`/`HF-N`, более новые, чем последнее упоминание токена
  в индексах (план отстал от кода);
- токен в коде без записи в реестре;
- HF-токены без строки в `HOTFIXES.md`;
- коммиты с кодом без единого токена — кандидаты в реестр хотфиксов;
- лишнее в корне `planning/` относительно `PLANNING_ROOT_ALLOWED`;
- предупреждения окружения: не подключены git-хуки (`core.hooksPath`); `DRIFT_MEMORY_INDEX` задан, а
  файла нет.

Найденное разбирается до новой работы: проверяй `git log` и код, а не только формулировку плана.

`.claude/scripts/plan-code-refs.sh` — отдельная сверка ссылок внутри плана (см. раздел 5).

## 9. Клиенты

| Клиент | Правила | Навык | Событийные хуки (включая strict) | Git-хуки |
|---|---|---|---|---|
| Claude Code | `AGENTS.md` (если в проекте нет `CLAUDE.md`) | `.claude/skills/x-harness-planning/` | нативно (`.claude/settings.json`) | нативно |
| Codex | `AGENTS.md` | `.agents/skills/` | `.codex/hooks.json` + `claude-compat.py`, trust в `/hooks` | нативно |
| DSH | `AGENTS.md` | `.dsh/skills/` или `.agents/skills/` | только мост (`--dsh-hooks bridge|community`) | нативно |
| generic | `AGENTS.md` | вручную | — | нативно |

Профиль не ставит `CLAUDE.md`. Если в проекте уже есть `CLAUDE.md`, Claude Code читает именно его, а
`AGENTS.md` игнорирует (08, раздел 2.1): в таком проекте в `CLAUDE.md` нужна ссылка на `AGENTS.md`
или его правила. Остальные клиенты читают `AGENTS.md` напрямую.

Без событийных хуков (`--clients none`, generic, DSH без моста) работают git-хуки, ручной
`plans-drift.sh`, `bin/xh gate` и `registry.sh check`; строгие guard'ы в этом случае не исполняются как
событийные — их проверки повторяет `pre-commit`/`pre-push`. Это честное ограничение, а не «правило
работает».

## 10. Приёмка

```bash
./verify.sh --profile planning --project /path/to/project
bash tests/acceptance-planning.sh
bash tests/acceptance-strict.sh
```

`verify.sh --profile planning` сверяет состав установленного профиля (файлы профиля, `registry.sh`,
`install-githooks.sh`, ключи `planning.conf`, при Codex — `.codex/hooks.json`), чистоту реестров через
`registry.sh check` и подключение git-хуков (`core.hooksPath`).

`tests/acceptance-planning.sh` прогоняет базовые сценарии на временном **не-Laravel** git-репозитории
(SPEC, раздел 8): установка и отсутствие лишних файлов; чистый `registry.sh check` и идемпотентность
`planning-init.sh`; `add` PLAN/HF/RM; коммит с токеном проходит, без — блок; прямой Edit индекса — exit 2;
RM без маркера — блок, после `rm-add` — проходит; закрытие плана с `close-plan`; drift; verify; повторная
установка с `--force`/без.

`tests/acceptance-strict.sh` (8 шагов: сценарии SPEC §9 плюс кросс-агентные конфиги и `bin/xh`) проверяет строгий слой: установку strict-файлов
и ключей conf; `branch-guard` (код на main — блок, на `feature/PLAN-1` — проходит); `commit-gate`
(коммит на main, `--no-verify`, `core.hooksPath` — блок); E18 (правка `.claude/hooks/` без
`hooks-edit` — блок, с маркером — проходит); `merge-gate` (без `merge`-маркера — блок; с маркером,
чистыми реестрами, токенами и `GATE_MERGE` — проходит); `main-push-guard`/`pre-push` (force/delete/
прямой коммит в main — блок, push feature — проходит); кросс-агентные Codex/DSH-конфиги содержат
strict-хуки; `bin/xh gate --fast` и `merge-ready` работают для generic.

Критерий приёмки — исполнение, а не наличие файлов: «настроено» (файл на месте) не равно
«подтверждено» (событие вызвано, запрещённое заблокировано, разрешённое прошло). До прогона сценариев
статус профиля — «настроено, но исполнение не подтверждено».

Ручные негативные сценарии, которые стоит прогнать после установки:

| Сценарий | Ожидание |
|---|---|
| правка кода в `src/` на `MAIN_BRANCH` | `branch-guard` блокирует (exit 2), `pre-commit` — при коммите |
| коммит на `MAIN_BRANCH` | `commit-gate` блокирует (exit 2) |
| коммит с `--no-verify` в Claude/Codex | `commit-gate` блокирует (exit 2) |
| правка `.claude/hooks/` без `hooks-edit` | `branch-guard`/pre-commit блокируют |
| мерж в `MAIN_BRANCH` без маркера `merge` | `merge-gate` блокирует (exit 2) |
| `git push --force origin main` | `main-push-guard`/pre-push блокируют |
| коммит на `feature/PLAN-1-*` без `PLAN-1` в сообщении | `commit-msg` блокирует (exit 1) |
| прямой Edit `planning/ACTIVE_PLANS.md` | `registry-guard` блокирует (exit 2) |

## 11. Отличия от snapshot-профиля

| Аспект | `--profile full` (snapshot) | `--profile planning` |
|---|---|---|
| Назначение | Laravel-профиль целиком | только планирование и строгая дисциплина в любом проекте |
| Константы | контейнер, БД, money-paths, пути macOS | нет; параметры — `.claude/planning.conf` |
| Инструкции | `CLAUDE.md` + `AGENTS.md`-симлинк + `.claude/reference/` | `AGENTS.md` + `planning/README.md` |
| Гейты качества | Larastan/Pint/PHPUnit/eslint/Dusk | только команды проекта из `GATE_FAST`/`GATE_MERGE` (пусто по умолчанию) |
| Ветки и мерж | `branch-guard`, `merge-gate`, `main-push-guard`, ревью E12 | портативные `branch-guard`/`commit-gate`/`merge-gate`/`main-push-guard`; без E12/E17 |
| Проверки чтения | `big-read-guard` (E14) | нет |
| owner-ok | `close-plan`, `rm-add`, `hooks-edit` | `close-plan`, `rm-add`, `hooks-edit`, `merge` |
| Событийные хуки | SessionStart + PreToolUse (8 хуков) | SessionStart + PreToolUse (6 хуков) |
| Git-хуки | pre-commit/commit-msg/pre-push/post-merge | commit-msg/pre-commit/pre-push (с E2/E18/GATE_FAST) |
| Режим установки | `--mode snapshot|port` имеет значение | `--mode` игнорируется, профиль всегда port |
| Манифест | `harness/` под `MANIFEST.sha256` | профиль вне манифеста; `harness/` не меняется |

## 12. Ограничения и честные пробелы

- **E16 в generic не гарантирован.** `--no-verify` отключает git-хуки; его ловит событийный
  `commit-gate` (Claude/Codex). В generic обход запрещён правилом, но технически возможен;
  `pre-push` проверяет только часть сценариев.
- **Нет ревью и уникальности номеров:** E12 (ревью), E13 (бюджет), E17 (номера на дереве слияния) в
  профиле отсутствуют; `merge`-маркер и чистые реестры их не заменяют.
- **Quality Gate — только команды проекта.** `GATE_FAST`/`GATE_MERGE` пусты по умолчанию; профиль не
  содержит Laravel-проверок и не выдаёт зелёный гейт сам.
- **Словарь статусов русский.** Английские и произвольные статусы `registry.sh check` отвергает.
- **`PreToolUse` требует `jq`.** Без `jq` хуки молча пропускают действие (exit 0); авторитетной
  остаётся git-проверка.
- **Информаторы не блокируют.** `plans-drift.sh` всегда exit 0; `plan-code-refs.sh` — тоже (exit 2 только
  на неверный вызов). Это сигнал, а не защита.
- **Событийные хуки — свойство клиента, а не профиля.** В generic и DSH без моста их нет.
- **Профиль вне `MANIFEST.sha256`.** `verify.sh` без `--profile` проверяет только `harness/`; состав
  профиля проверяется отдельно (`--profile planning`).
- **Нет `CLAUDE.md`.** В проекте, где Claude Code уже читает `CLAUDE.md`, правила `AGENTS.md` нужно
  продублировать ссылкой.
- **`.claude/state/` — локальное состояние.** `install.sh --profile planning` создаёт
  `.claude/state/.gitignore` (`*` + `!.gitignore`), поэтому маркеры owner-ok и `registry.lock` в коммит не
  попадут; правило «не коммить state» действует, если `.gitignore` удалён или state скопирован вручную.

## 13. Источники

Локальные:
- `profiles/planning/SPEC.md` — контракт: файлы, CLI, `planning.conf`, инварианты, строгий слой, приёмка;
- `profiles/planning/README.md`, `profiles/planning/AGENTS.md`, `profiles/planning/planning/README.md`,
  `skills/x-harness-planning/SKILL.md` — тексты профиля;
- `harness/.claude/scripts/registry.sh`, `harness/.claude/scripts/install-githooks.sh`,
  `harness/.claude/hooks/plans-drift.sh` — поведение, из которого профиль берёт инварианты;
- `install.sh`, `verify.sh`, `tests/acceptance-planning.sh`, `tests/acceptance-strict.sh` — установка
  и приёмка профиля.

**Граница Git-хуков:** в клиентах без PreToolUse нативные Git-хуки не гарантируют проверку owner-ok и гейта при `git merge`, в том числе fast-forward. Перед мержем запускайте `merge-ready` и вручную проверяйте условия; для принуждения используйте серверную защиту.
