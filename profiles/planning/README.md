# Планировочный профиль x-harness (`--profile planning`)

Слой управления планами для **любого** git-проекта: реестры RM/PLAN/HF, роадмап, планы, хотфиксы,
слово владельца (owner-ok), строгая дисциплина веток и git-хуки. Без Laravel, без `.ai/`, без MCP,
без констант Laravel-профиля. Snapshot-обвязка (`harness/`) при этом не меняется: профиль — отдельная сборка из
`profiles/planning/` плюс три файла из `harness/`.

## Зачем

Полный профиль (`--profile full`, по умолчанию) — дисциплина Laravel-проекта: Sail/Docker,
Larastan/Pint/PHPUnit/Dusk, агенты, MCP, money-paths, Quality Gate. Для проекта на другом стеке это
лишнее, но правила работы переносимы: номера, индексы, коммиты с токеном, реестры как источник правды
об этапе. Профиль ставит этот слой **строгим по умолчанию**: E2 (ветки), E18 (защищённые пути),
E16 (обход хуков), защита `main` (коммит/мерж/пуш) и Quality Gate по командам проекта.

Контракт профиля — [SPEC.md](SPEC.md). Подробная документация для потребителя пакета —
[../../skills/x-harness/references/09-planning-profile.md](../../skills/x-harness/references/09-planning-profile.md).

## Установка

```bash
# в git-проект (клиенты и навыки — автоопределение)
./install.sh --project /path/to/project --profile planning

# минимум: только правила и git-хуки, без клиентских обвязок и навыков
./install.sh --project /path/to/project --profile planning --clients none --skills none

# посмотреть план без записи
./install.sh --project /path/to/project --profile planning --dry-run
```

Флаги (общие с полным профилем):

| Флаг | Смысл для planning-профиля |
|---|---|
| `--project DIR` | целевой проект (по умолчанию текущий каталог) |
| `--profile full|planning` | `full` — текущий snapshot (по умолчанию); `planning` — этот профиль |
| `--clients auto|all|claude,codex,dsh,generic|none` | какие клиентские обвязки ставить; `none` — только файлы и git-хуки |
| `--skills auto|project|global|both|none` | ставить ли skill `x-harness-planning` и куда |
| `--force` | заменить существующие пути (старые уезжают в `.x-harness-backup.<TS>/`) |
| `--dry-run` | показать план, ничего не записывая |
| `--no-verify` | не запускать `verify.sh` в конце установки |
| `--no-git` | разрешить проект без git (git-хуки тогда не подключаются) |
| `--dsh-hooks none|bridge|community`, `--dsh-profile`, `--dsh-version` | мост событийных хуков для DSH (как в полном профиле) |

`--mode` для planning **игнорируется**: профиль всегда port-совместим, подменять константы Laravel-профиля в нём
нечего. `--fix-paths` относится к Codex-конфигу полного профиля и профилю не нужен.

Последовательность установки: скопировать профиль → сгенерировать `.claude/planning.conf` (`MAIN_BRANCH`,
`CODE_ROOTS`, `STRICT=on` и остальные ключи) → подключить `core.hooksPath=.githooks` → выполнить
`.claude/scripts/planning-init.sh` → `verify.sh --profile planning`. Установщик также создаёт
`.claude/state/.gitignore`, чтобы маркеры owner-ok и `registry.lock` не попали в коммит.

**Конфликты.** Без `--force` установка падает, если в проекте уже есть `.claude`, `.githooks`,
`AGENTS.md` или `planning/README.md` (при `--clients codex` — ещё `.codex/hooks.json` и
`.codex/hooks/claude-compat.py`). Существующий каталог `planning/` не перезаписывается: заменяется
только `planning/README.md`. Навыки ставятся отдельно и при уже существующем навыке без `--force` дают
предупреждение, а не падение. С `--force` заменяемые пути уходят в `.x-harness-backup.<YYYYmmdd-HHMMSS>/`.
Повторная установка без `--force` — ошибка: это защита, а не «не трогает совпадающее».

## Что ставится

| Путь в проекте | Назначение |
|---|---|
| `AGENTS.md` | правила проекта: реестры, строгий слой, owner-ok, токены, gate |
| `planning/README.md` | правила реестров: что где, команды, статусы, шаблон, закрытие, strict |
| `.claude/planning.conf` | параметры профиля (из `.claude/planning.conf.template`) |
| `.claude/settings.json` | события Claude: `SessionStart` (drift) и `PreToolUse` (branch-guard, commit-gate, merge-gate, main-push-guard, registry-guard, owner-ok-guard) |
| `.claude/scripts/planning-init.sh` | идемпотентно создаёт индексы, каталоги и `.gitkeep` |
| `.claude/scripts/planning-lib.sh` | загрузка `.claude/planning.conf` и дефолтов |
| `.claude/scripts/install-githooks.sh` | подключение `core.hooksPath=.githooks` (копия из `harness/`) |
| `.claude/scripts/registry.sh` | единственный способ правки индексов (копия из `harness/`) |
| `.claude/scripts/planning-owner-ok.sh` | маркеры владельца: `close-plan`, `rm-add`, `hooks-edit`, `merge` |
| `.claude/scripts/plan-code-refs.sh` | сверка ссылок плана с кодом проекта |
| `.claude/scripts/quality-gate.sh` | `--fast` → `GATE_FAST`, `--merge` → `GATE_MERGE` (команды проекта) |
| `.claude/scripts/merge-ready.sh` | сухой прогон требований мержа (не мержит, маркеры не расходует) |
| `.claude/hooks/plans-drift.sh` | сверка реестров с git, всегда exit 0 |
| `.claude/hooks/registry-guard.sh` | блокирует Edit/Write по четырём индексам |
| `.claude/hooks/owner-ok-guard.sh` | блокирует выдачу маркера агентом |
| `.claude/hooks/branch-guard.sh` | E2/E18: ветка и защищённые пути при правках |
| `.claude/hooks/commit-gate.sh` | E2/E16: коммиты на main, `--no-verify`, `core.hooksPath` |
| `.claude/hooks/merge-gate.sh` | мерж в main: ветка, токены, реестры, маркер `merge`, `GATE_MERGE` |
| `.claude/hooks/main-push-guard.sh` | force/delete/прямые коммиты в main |
| `.claude/hooks/strict-checks.py` | общая логика строгих guard'ов |
| `.claude/hooks/planning-checks.py` | проверки для git-хуков: токен, резюме/размер, owner-ok |
| `.githooks/commit-msg`, `.githooks/pre-commit`, `.githooks/pre-push` | авторитетные проверки в терминале |
| `.claude/skills/` · `.agents/skills/` · `.dsh/skills/` | навык `x-harness-planning` у выбранных клиентов (если `--skills` не `none`) |

Из `harness/` берутся только `.claude/scripts/registry.sh`, `.claude/scripts/install-githooks.sh`
(подключение `core.hooksPath`) и `.codex/hooks/claude-compat.py` (если выбран клиент codex).

## Что НЕ ставится

- `.ai/`, `.mcp.json`, `boost.json`, `CLAUDE.md`, `harness/CLAUDE.md` — правила Laravel-профиля и Laravel Boost.
- Полные версии хуков и гейтов: `quality-gate.sh` с Larastan/Pint/PHPUnit/Dusk, `merge_checks.py`,
  `commit_checks.py`, money-paths, `paths.conf`, `big-read-guard`. В профиле — свои портативные
  `branch-guard`/`commit-gate`/`merge-gate`/`main-push-guard` без Laravel-логики.
- Агенты и навыки полного профиля (`.claude/agents`, `.ai/skills`; из `.claude/skills` ставится только навык
  `x-harness-planning`).
- `.claude/reference/`, `.claude/rules/`, `.codex/config.toml` полного профиля.
- Состояние и секреты: `.claude/state/` (кроме создаваемого установщиком `.claude/state/.gitignore`),
  `settings.local.json`, `.env` — установка их не копирует.

## Строгий слой (STRICT=on по умолчанию)

Цель — те же барьеры дисциплины, что в полном профиле, но без Laravel. Управление — `.claude/planning.conf`;
отключение `STRICT=off` — **слово владельца** (conf лежит в защищённых путях, для правки нужен маркер
`hooks-edit`; агент его себе не выдаёт).

| Правило | Суть | Чем принуждается |
|---|---|---|
| **E2** ветки | код (`CODE_ROOTS`, `CODE_FILES`) — только на `feature/PLAN-N-*`/`hotfix/*`; на `MAIN_BRANCH` правки кода и коммиты запрещены (`planning/`, `docs/`, `*.md` можно; merge/rebase/cherry-pick — исключение); на прочих ветках — только planning/docs/*.md/не-код | `branch-guard.sh` (ранняя блокировка), `pre-commit` (авторитетно) |
| **E18** защищённые пути | `PROTECTED_PATHS` — только с маркером `hooks-edit <ветка>`: хуки, скрипты, `settings.json`, `planning.conf`, `.githooks/`, `AGENTS.md`, `.codex/` | `branch-guard.sh`, `pre-commit` |
| **E16** обходы | `--no-verify`, `-n`, `-c core.hooksPath=…`, `GIT_CONFIG_*`, `git config core.hooksPath …` запрещены | `commit-gate.sh` (Claude/Codex); правило для всех |
| **main: коммит** | коммит на `MAIN_BRANCH` агенту запрещён | `commit-gate.sh`, `pre-commit` |
| **main: мерж** | только из `feature/PLAN-N-*`/`hotfix/*`, все коммиты с токеном, реестры чисты, маркер владельца `merge <ветка>`, `GATE_MERGE` обязателен; обходные движения main (`cherry-pick`, `rebase`, `reset --hard`, `branch -f main`) блокируются | `merge-gate.sh` (ранняя блокировка) |
| **main: пуш** | событийный `main-push-guard`: force/delete любого refspec, push main офлайн без `refs/remotes/<remote>/<MAIN_BRANCH>` (просит `git fetch`). Git `pre-push`: non-fast-forward любой ветки, удаление `MAIN_BRANCH`, push в main из не-main, прямые (не-мерж) коммиты впереди `<remote>/<MAIN_BRANCH>`; первый push main разрешён. Пуши `feature/*`, `hotfix/*` и теги проходят | `main-push-guard.sh` + git `pre-push` |
| **Quality Gate** | `GATE_FAST` перед коммитом, `GATE_MERGE` перед мержем; команды проекта, при STRICT=on пустой GATE_FAST или GATE_MERGE блокирует операцию | `.claude/scripts/quality-gate.sh --fast|--merge`; для generic — `bin/xh gate` |

### Кто что блокирует

| Слой | Claude Code | Codex | DSH | generic |
|---|---|---|---|---|
| Событийные хуки (branch/commit/merge/main-push/owner-ok/registry) | нативно (`.claude/settings.json`) | `.codex/hooks.json` + `claude-compat.py` | только мост (`--dsh-hooks`) | — |
| Git-хуки `commit-msg`/`pre-commit`/`pre-push` | нативно | нативно | нативно | нативно |
| Quality Gate | `quality-gate.sh` / `commit-gate` | то же | то же | `bin/xh gate` |
| Кто блокирует раньше | событийный хук | событийный хук | мост (subset) | git-хук |

Событийные хуки — **ранняя** блокировка до выполнения действия; git-хуки — **авторитетная** проверка
в терминале. Профиль честно таков: без событийных хуков git-слой продолжает работать, а `bin/xh` даёт
ручной запуск.

**`STRICT=off`** (только владелец, через `.claude/planning.conf`) выключает строгие guard'ы (exit 0),
E2/E18 и `GATE_FAST` в `pre-commit`, strict-часть `pre-push` и `merge-ready`. Базовый слой остаётся:
реестры через `registry.sh`, `registry.sh check`, owner-ok для `close-plan`/`rm-add`, токен в
`commit-msg`, `plans-drift`.

### Quality Gate и merge-ready

- `.claude/scripts/quality-gate.sh --fast` выполняет `GATE_FAST` через `bash -c` в корне проекта;
  при STRICT=on пустые значения блокируют проверку. `--merge` выполняет `GATE_MERGE`; при чистом дереве пишет
  `.claude/state/gates/<ветка с / → _>.merge-passed` = полный `HEAD` и SHA-256 команды (грязное дерево — предупреждение без
  отметки); падение — exit 1. `merge-gate` требует отметку всегда при STRICT=on и сверяет её
  с вершиной мержимой ветки и текущей командой. Повторный запуск `--merge` удаляет прежнюю отметку до проверки.
- `bin/xh gate --fast|--merge` — та же команда для generic-агентов.
- `.claude/scripts/merge-ready.sh <ветка>` — сухой прогон требований мержа (ветка, токены, реестры,
  маркер `merge`, `GATE_MERGE`); ничего не мержит и маркеры **не расходует**. `exit 0` = `READY` (в том числе
  `READY (кроме слов владельца)` — недостающий маркер `merge` перечислен отдельно), `exit 1` = `NOT READY` +
  причины; при `STRICT=off` печатает, что слой выключен, и выходит 0.

## Матрица ограничений strict

- В generic-клиенте E16 (`--no-verify`) технически обходим: git сам не запускает хуки; правило
  запрещает обход, `pre-push` ловит только часть (force/delete/main). Событийный `commit-gate` есть
  только в Claude/Codex.
- Событийные хуки не гарантия: DSH — только через мост и subset событий; generic — нет.
- `GATE_FAST`/`GATE_MERGE` пусты по умолчанию: профиль не навязывает конкретные проверки. Это НЕ
  Laravel Quality Gate: никаких Larastan/Pint/PHPUnit/Dusk.
- `merge-ready` — сухой прогон требований (ветка/токены/реестры/маркер/гейт); сам он не мержит и
  маркеры не расходует.
- `merge`-маркер привязан к вершине исходной ветки: новый коммит после выдачи требует нового маркера.

## Карта исходников профиля

| Файл в `profiles/planning/` | Куда ставится / роль |
|---|---|
| `AGENTS.md` | `<проект>/AGENTS.md` |
| `planning/README.md` | `<проект>/planning/README.md` |
| `skill/SKILL.md` | каталог навыка `x-harness-planning` у выбранных клиентов |
| `README.md` | эта документация (в проект не ставится) |
| `SPEC.md` | контракт реализации (в проект не ставится) |
| `.claude/`, `.githooks/` | runtime-файлы профиля, ставятся в проект как есть |

## `.claude/planning.conf`

Shell-совместимый `KEY=VALUE`, читается `planning-lib.sh`. Без файла работают те же дефолты — хук не
должен падать из-за отсутствия конфига.

| Ключ | Дефолт | Смысл |
|---|---|---|
| `MAIN_BRANCH` | `main` | основная ветка проекта; на ней токен коммита не требуется, к ней привязаны маркеры owner-ok |
| `CODE_ROOTS` | `"app src lib"` | каталоги с кодом для `plans-drift`, `plan-code-refs` и классификации E2. Пусто или ни одного существующего каталога — автодетект каталогов первого уровня по git (кроме `.*`, `planning`, `node_modules`, `vendor`) |
| `FEATURE_BRANCH_RE` | `^feature/PLAN-([0-9]+(\.[0-9]+)*)(?:-|$)` | какие ветки считаются плановыми; из ветки берётся номер `PLAN-N` |
| `HOTFIX_BRANCH_RE` | `^hotfix/` | какие ветки считаются хотфиксными |
| `TOKEN_REQUIRED` | `on` | требовать ли токен `PLAN-N`/`HF-N` в коммитах на плановых/хотфикс-ветках |
| `PLAN_SUMMARY_MIN_NUMBER` | `1` | с какого номера плана обязателен `## Резюме` (1 = все) |
| `PLAN_WARN_BYTES` | `40960` | размер плана, с которого pre-commit печатает предупреждение |
| `PLAN_HARD_BYTES` | `81920` | размер плана, с которого pre-commit блокирует коммит (для номеров от `PLAN_SUMMARY_MIN_NUMBER`; меньшие — только предупреждение) |
| `DRIFT_HORIZON_DAYS` | `90` | окно, за которое `plans-drift` ищет код-коммиты |
| `DRIFT_MEMORY_INDEX` | пусто | путь к файлу памяти, наличие которого проверяет drift; пусто = проверка выключена |
| `OWNER_OK_TTL_HOURS` | `24` | срок жизни маркера owner-ok |
| `PLANNING_ROOT_ALLOWED` | `"ROADMAP.md ACTIVE_PLANS.md PLANS.md HOTFIXES.md README.md plans roadmap hotfixes"` | что допустимо в корне `planning/`; остальное — нарушение E9 |
| `STRICT` | `on` | строгий слой: E2/E18/E16, защита main, gate. `off` — только словом владельца |
| `PROTECTED_PATHS` | `".claude/hooks/ .claude/scripts/ .claude/settings.json .claude/planning.conf .githooks/ AGENTS.md .codex/"` | пути, правимые только с маркером `hooks-edit` (E18) |
| `CODE_FILES` | `"Makefile package.json pyproject.toml go.mod go.sum Cargo.toml composer.json requirements.txt"` | корневые файлы, которые считаются кодом для E2 |
| `GATE_FAST` | пусто | команда перед коммитом (пусто при STRICT=on — блокировка) |
| `GATE_MERGE` | пусто | команда перед мержем (пусто — мерж заблокирован) |

Шаблон (`.claude/planning.conf.template`) содержит дефолты; установщик подставляет `MAIN_BRANCH` и
`CODE_ROOTS`. Менять конфиг можно, но это настройка проекта, а не обход проверок.

## Команды

Выполняются из корня проекта.

```bash
# инициализация/починка planning/: индексы, каталоги, .gitkeep; затем registry.sh check
.claude/scripts/planning-init.sh

# реестры — только через registry.sh
.claude/scripts/registry.sh next-id PLAN
.claude/scripts/registry.sh add PLAN PLAN-1 "Название плана" --slug nazvanie
.claude/scripts/registry.sh add HF auto "Что и зачем" --slug hotfix-fix
.claude/scripts/registry.sh add RM auto "Идея" --trigger "после PLAN-1" --slug idea
.claude/scripts/registry.sh set-status PLAN-1 "в работе"
.claude/scripts/registry.sh show PLAN-1
.claude/scripts/registry.sh check --registry all

# слово владельца (ТОЛЬКО владелец в своём терминале)
.claude/scripts/planning-owner-ok.sh close-plan PLAN-1 [ветка]
.claude/scripts/planning-owner-ok.sh rm-add RM-1 [ветка]
.claude/scripts/planning-owner-ok.sh hooks-edit <ветка>
.claude/scripts/planning-owner-ok.sh merge <ветка>

# Quality Gate и мерж (команды проекта из conf; при STRICT=on пустые значения блокируют проверку)
.claude/scripts/quality-gate.sh --fast
.claude/scripts/quality-gate.sh --merge
.claude/scripts/merge-ready.sh <ветка>
bin/xh gate --fast|--merge          # generic-клиент

# сверка (информационные, не гейты)
.claude/hooks/plans-drift.sh
.claude/scripts/plan-code-refs.sh planning/plans/PLAN-1-*.md
```

`plan-code-refs.sh` проверяет пути файлов в обратных кавычках и ссылки `Класс::член`; ненайденное у
открытого плана — норма (будущий код), перед закрытием список должен быть пуст. Он проверяет
существование сущности, но не её использование.

Git-хуки (подключаются `core.hooksPath=.githooks`, exit 1 = блокировка, внутренний сбой — fail-open):

| Хук | Что проверяет |
|---|---|
| `commit-msg` | `planning-checks.py msg`: токен `PLAN-N`/`HF-N` на плановой/хотфикс-ветке (на `MAIN_BRANCH` не требуется; коммит только по `planning/roadmap/**`/`ROADMAP.md` может нести `RM-N`) |
| `pre-commit` | E2 (ветка) и E18 (`PROTECTED_PATHS` с маркером `hooks-edit`), `planning-checks.py staged` (резюме/размер, E9-лайт, owner-ok для нового RM и `plans/closed/PLAN-N.md`), `registry.sh check` по staged-дереву, затем `GATE_FAST` обязателен при STRICT=on |
| `pre-push` | форма реестров по пушимому дереву; при `STRICT=on` — non-fast-forward (force) любой ветки, удаление `MAIN_BRANCH`, push в main из не-main, прямые коммиты впереди `<remote>/main` блокируются; первый push main разрешён, `feature/*`/`hotfix/*` и теги проходят |

## Приёмка

```bash
./verify.sh --profile planning --project /path/to/project   # состав, реестры, core.hooksPath
bash tests/acceptance-planning.sh                            # базовые сценарии профиля
bash tests/acceptance-strict.sh                               # строгий слой (E2/E18/E16, merge/push, клиенты)
```

`tests/acceptance-planning.sh` прогоняет на временном git-репозитории: установку `--profile planning`
и отсутствие лишних файлов; чистый `registry.sh check` и идемпотентность `planning-init.sh`; `add`
PLAN/HF/RM; прохождение коммита с токеном и блокировку без него; блокировку прямого Edit индекса
(exit 2); блокировку RM-коммита без маркера и прохождение после `planning-owner-ok.sh rm-add`;
закрытие плана с маркером `close-plan`; drift; `verify.sh --profile planning` = OK; повторную
установку без `--force` (ошибка) и с `--force` (backup).

`tests/acceptance-strict.sh` проверяет строгий слой: `branch-guard` (правка кода на main — блок,
на `feature/PLAN-1` — проходит); `commit-gate` (коммит на main, `--no-verify`, код на не-плановой
ветке — блок); E18 (правка `.claude/hooks/` без `hooks-edit` — блок, с маркером — проходит);
`merge-gate` (мерж в main без маркера `merge` — блок, с маркером/чистыми реестрами/токенами — проходит,
падение `GATE_MERGE` — блок); `main-push-guard`/`pre-push` (force/delete/прямой коммит в main — блок);
сгенерированные Codex/DSH-конфиги содержат строгие guard'ы. До прогона приёмки статус профиля —
«настроено, но исполнение не подтверждено».

## Ограничения

- **Нет гейтов ревью и уникальности номеров**: E12 (ревью), E13 (бюджет), E17 (номера на дереве
  слияния) в профиле отсутствуют; `merge`-маркер и чистые реестры их не заменяют.
- **Quality Gate — только команды проекта.** `GATE_FAST`/`GATE_MERGE` пусты по умолчанию; профиль
  не содержит Laravel/PHP-проверок (Larastan/Pint/PHPUnit/Dusk) и не выдаёт зелёный гейт сам.
- **E16 в generic не гарантирован.** `--no-verify` отключает git-хуки; его ловит событийный
  `commit-gate` (Claude/Codex). В generic обход запрещён правилом, но технически возможен; `pre-push`
  проверяет только часть сценариев.
- **Событийные хуки — свойство клиента**: нативно Claude Code/Codex, DSH — только мост (subset),
  generic — нет. Git-хуки работают везде, где есть bash и python3.
- **`PreToolUse` требует `jq`**; без него событийные хуки пропускают действие (exit 0), авторитетной
  остаётся git-проверка.
- **Словарь статусов — русский** и точный: `черновик`/`в работе`/`на паузе`/…; английские слова и
  произвольные статусы `registry.sh check` отвергает.
- `plans-drift.sh` — информатор, всегда exit 0; `plan-code-refs.sh` — тоже не гейт (exit 0, код 2 —
  только на неверный вызов). Это сигнал, а не защита от нарушения.
- **`.claude/state/` — локальное состояние.** `install.sh` создаёт там `.gitignore` (`*` +
  `!.gitignore`), поэтому маркеры и `registry.lock` в коммит не попадут; правило «не коммить state»
  действует, если `.gitignore` удалён или state скопирован вручную.
- Нет `.claude/reference/`, `.ai/`, `CLAUDE.md`: правила живут в `AGENTS.md` и `planning/README.md`.
  Клиент, который не читает `AGENTS.md`, правил не получит.

## Связанные файлы

- [SPEC.md](SPEC.md) — контракт профиля: файлы, CLI, conf, инварианты, строгий слой, приёмка.
- [../../skills/x-harness/references/09-planning-profile.md](../../skills/x-harness/references/09-planning-profile.md) — подробная документация
  (архитектура, строгий слой, клиенты, отличия от snapshot).
- [../../skills/x-harness/references/08-install-and-acceptance.md](../../skills/x-harness/references/08-install-and-acceptance.md) — установка
  и приёмка пакета целиком.

**Граница Git-хуков:** в клиентах без PreToolUse нативные Git-хуки не гарантируют проверку owner-ok и гейта при `git merge`, в том числе fast-forward. Перед мержем запускайте `merge-ready` и вручную проверяйте условия; для принуждения используйте серверную защиту.
