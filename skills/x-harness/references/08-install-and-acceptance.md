# 08. Установка пакета «x-harness» и приёмка идентичности среды

Назначение: перенести обвязку на агентные клиенты; доступность событийных проверок, навыков и ролей зависит от клиента и должна проверяться отдельно. Документ описывает установку пакета `x-harness`, подключение клиентов и приёмку. Снимок 30 октября 2026; версия Host DSH в снимке — `0.2.1-rc.5`.

Термины:
- **Payload** — каталог `harness/`: исполняемая обвязка, дополненная ролями Codex; абсолютный cwd MCP отсутствует.
- **Клиент** — Claude Code, Codex, DSH, ZCode/OpenCode или другой агент.
- **Модель** — GLM, DeepSeek и т.п. Модель не определяет наличие хуков и навыков: это свойства клиента.
- **Настроено** — конфигурация записана. **Подтверждено** — событие реально вызвано и проверка реально заблокировала действие в целевом клиенте.

## 1. Принцип: один канонический payload

Правила и проверки существуют в одном экземпляре. Клиент только подключает их штатным механизмом. Переписывать политику под каждого клиента нельзя: две копии правил расходятся, и «одинаковая среда» перестаёт быть одинаковой.

```text
x-harness/
  SKILL.md                  # вход skill: frontmatter name+description, карта 00–08
  README.md
  references/00..08.md      # 00-index — карта источников, 01–08 — темы
  harness/                  # единственный канонический payload
    .claude/                # hooks, scripts, skills, agents, reference, rules, settings.json
    .ai/                    # guidelines и канонические skills
    .codex/                 # hooks.json, hooks/claude-compat.py, config.toml
    .githooks/              # pre-commit, commit-msg, pre-push, post-merge
    CLAUDE.md
    AGENTS.md -> CLAUDE.md  # символическая ссылка сохраняется
    boost.json  .mcp.json  planning/README.md
  install.sh                # установка в проект; при конфликте --force, старые пути в backup
  verify.sh                 # parity: MANIFEST.sha256 <=> harness/ <=> установленная копия
  bin/xh                    # CLI: doctor, gate, drift, merge-ready, registry, hook, verify
  tests/acceptance.sh       # приёмка пакета в чистом временном git-репозитории
  MANIFEST.sha256           # хэши и режимы файлов + цели симлинков
```

Состав payload: `.claude/`, `.ai/`, `.codex/`, `.githooks/`, `CLAUDE.md`, `AGENTS.md`, `.mcp.json`, `boost.json`, `planning/README.md`. Обоснование — `outputs/AGENT_HARNESS.md`, строки 23–41.

Профиль `--profile planning` **не является частью payload** `harness/`: он собирается из `profiles/planning/` плюс трёх файлов `harness/` (`registry.sh`, `install-githooks.sh`, `.codex/hooks/claude-compat.py` для Codex). Подробно — [09-planning-profile.md](09-planning-profile.md).

Payload включает 8 ролей Codex, абсолютный cwd MCP в нём отсутствует. Вне payload — только runtime-артефакты: `.claude/state/`, `.claude/settings.local.json`, `__pycache__/`.

Три уровня переноса:

1. Текст правил (`CLAUDE.md`/`AGENTS.md`, `.claude/rules/`, `.claude/reference/`, `.ai/guidelines/`) — что агент должен делать.
2. Событийные хуки клиента (`.claude/settings.json`, `.codex/hooks.json`, мосты DSH) — что проверяется до действия.
3. Настоящие Git-хуки (`.githooks/`) — что проверяется в обычном терминале и при push.

Уровни дополняют друг друга. Git-хуки не видят правки через инструмент агента до коммита, событийные хуки не работают в терминале владельца. Skill сам по себе не является принуждением: это переносимый каталог инструкций. Карта источников — `references/00-index.md`.

## 2. Где каждый клиент ищет правила, навыки и хуки

### 2.1. Claude Code

| Что | Где ищет | Примечание |
|---|---|---|
| Правила | `./CLAUDE.md` или `./.claude/CLAUDE.md`; `~/.claude/CLAUDE.md` | Иерархия загружается при старте |
| AGENTS.md | Только если рядом нет `CLAUDE.md`/`CLAUDE.local.md` | Если оба файла есть, читается `CLAUDE.md`, а не `AGENTS.md` |
| Навыки | `~/.claude/skills/<name>/SKILL.md`, `<project>/.claude/skills/<name>/SKILL.md` | Симлинки на каталог навыка поддерживаются |
| Событийные хуки | `~/.claude/settings.json`, `<project>/.claude/settings.json`, `.claude/settings.local.json` | События → matcher groups → command hooks |
| Субагенты | `<project>/.claude/agents/*.md` | YAML frontmatter: name, description, model, color |

В payload `.claude/settings.json` содержит только `SessionStart` (plans-drift.sh) и `PreToolUse` с matchers `Edit|Write|NotebookEdit`, `Bash`, `Read`. Событий `Stop`/`PostToolUse` нет. Команды вызываются как `"$CLAUDE_PROJECT_DIR/.claude/hooks/*.sh"`.

### 2.2. Codex

| Что | Где ищет | Примечание |
|---|---|---|
| Правила | `$CODEX_HOME/AGENTS.md` (по умолчанию `~/.codex/AGENTS.md`) и `AGENTS.md` от корня проекта вниз до cwd | Сначала `AGENTS.override.md`, потом `AGENTS.md`; `project_doc_max_bytes`, по умолчанию 32 КиБ |
| Навыки | `$REPO_ROOT/.agents/skills`, `$CWD/.agents/skills`, `$HOME/.agents/skills`, `/etc/codex/skills` | Каталог с `SKILL.md` или плоский `<name>.md`; симлинки поддерживаются |
| Событийные хуки | `<repo>/.codex/hooks.json`, `~/.codex/hooks.json`, inline `[hooks]` в `config.toml` | Плюс `[features] hooks = true` в `config.toml` |
| Субагенты | `.codex/agents/*.toml` | Формат и trust — в документации Codex |

События Codex: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PreCompact`, `PostCompact`, `SubagentStart`, `SubagentStop`, `Stop`, `Interrupt`, `SessionEnd`. Обвязка использует `SessionStart` и `PreToolUse`; matchers `.codex/hooks.json`: `apply_patch|Edit|Write|NotebookEdit` и `Bash|exec_command|shell_command|shell|functions.exec_command`.

Недоверенные project-хуки Codex не запускает до подтверждения в `/hooks`; доверие привязано к хешу определения, после правки файла его нужно подтверждать снова.

Расхождение: `$CODEX_HOME/skills` (~/.codex/skills) в актуальной документации Codex не указан; перечислены `.agents/skills`. Поэтому `install.sh --skills global` при выбранном Codex копирует навыки и в `${CODEX_HOME:-$HOME/.codex}/skills`, и в `~/.agents/skills`. Какое из мест реально обнаружит конкретный билд Codex, **не подтверждено без прогона**.

### 2.3. DeepSeek Harness (DSH)

**Правила.** Загружается один baseline:
- пользовательская цепочка: `$DSH_HOME/AGENTS.md`, затем `<agentsHome>/AGENTS.md`;
- проектная цепочка: от корня проекта (маркер `.git`) вниз до рабочего каталога сессии;
- кандидаты: `AGENTS.md`, `CLAUDE.md`; локальные надстройки: `AGENTS.local.md`, `CLAUDE.local.md`;
- бюджет по умолчанию в `dsh-base` — **65536 байт** на весь baseline; при превышении сначала отбрасываются более широкие файлы, затем усекается самый конкретный, с уведомлением;
- `$DSH_HOME` = `$DSH_HOME`, иначе `~/.dsh`; `agentsHome` = `$DSH_AGENTS_HOME`, иначе `~/.agents`.

Одинаковые после trim файлы рендерятся один раз: `AGENTS.md`-симлинк на `CLAUDE.md` не дублируется.

**Навыки.** Корни по приоритету:

| Ранг | Источник | Путь |
|---|---|---|
| 100 | project-dsh | `<projectRoot>/.dsh/skills` |
| 200 | project-agents | `<projectRoot>/.agents/skills` |
| 300 | custom | `customSkillDirs` профиля |
| 400 | user-dsh | `<dshHome>/skills` (~/.dsh/skills) |
| 500 | user-agents | `<agentsHome>/skills` (~/.agents/skills) |

Формат: каталог `<name>/SKILL.md` или плоский `<name>.md` на верхнем уровне корня. Вложенные `**/SKILL.md` намеренно не обнаруживаются. Frontmatter обязателен: `name` и `description`; невалидный frontmatter отбрасывает навык с предупреждением.

**Хуки.** Встроенного чтения `hooks.json` у DSH нет. Переносимые варианты — только мосты:

| Мост | Пакет | События | Ограничения |
|---|---|---|---|
| Официальный Claude | `@deepseek-ai/dsh-hooks-claude-code` | SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop, SubagentStart, SubagentStop (7 из 30 событий Claude) | Только command hooks; один `configPath` читается один раз при старте; `SessionStart` detached, plain stdout не потребляется |
| Официальный Codex | `@deepseek-ai/dsh-hooks-codex` | SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, Stop (5) | `PreToolUse` передаёт `tool_input: {command}`; не-shell аргументы не передаются |
| Community | `dsh-hooks-plugin` (npm, MIT, не официальный) | README v0.2.15: PreToolUse, PostToolUse, PostToolUseFailure, UserPromptSubmit, SessionStart, SessionEnd, Stop, SubagentEnd (8) | Конфиг `.dsh/hooks.json`; не выставляет `CLAUDE_PROJECT_DIR`; сторонний код |

Версии мостов должны совпадать с Host: peerDependencies `0.2.1-rc.5`. `install.sh --dsh-hooks bridge` требует явный `--dsh-version`; пример `0.1.0-rc.8` в его `--help` устарел относительно снимка — подставлять версию Host.

Монтирование: x-harness — бандл профиля (`package.json` → `"dsh": {"bundle": {"patch": "./dsh/cordis.patch.yml"}}`). `dsh plugin --profile <profile> add github:cheusbeats/x-harness` сам добавляет его в `dsh.profile.bundles`; патч вставляет строку `x-harness-hooks` (мост `dsh-hooks-claude-code`), пути считаются выражением `!!js` от `baseUrl` — каталога профиля. Пакет моста и протокола ставится отдельно, версией Host.

**Конфиг моста общий на процесс.** Мост читает `configPath` один раз при загрузке DSH (README моста: process-level, без поиска по сессии), поэтому конфиг в проекте с жёстким `cd <project>` работал бы только для одного проекта. x-harness кладёт глобальный [`hooks/dsh-hooks.json`](../../../hooks/dsh-hooks.json): команды `python3 "${CLAUDE_PLUGIN_ROOT}/adapters/agent-hook.py" dsh <Event>` (`pluginRoot` подставляет мост), хуки исполняются в `cwd` сессии, переводчик находит по нему проект и ничего не делает вне обвязки. Проверено в изолированном `DSH_HOME` (Host 0.1.0-rc.7): бандл добавлен в профиль, в «Списке плагинов» `include:x-harness-hooks` включён и смонтирован; живой вызов хука требует сессии с API-ключом и не выполнялся. `install.sh --dsh-hooks bridge` делает тот же `dsh plugin add` и файлов моста в проект не пишет; `--dsh-hooks community` по-прежнему пишет `.dsh/hooks.json` и `.dsh/agent-hook.py` в проект.

Codex-мост DSH для файловых проверок не подходит: не-shell аргументы приходят как `''`. Выбирать Claude-мост.

### 2.4. Kimi Code, ZCode, OpenCode (плагин x-harness)

Хуки этих клиентов задаются только глобально или через плагин, проектных хуков у них нет. Поэтому x-harness ставится в них **плагином**. Его хуки вызывают `adapters/agent-hook.py`, который ищет проект по `cwd` из payload. Если в проекте нет обвязки (маркер — `.claude/hooks/plans-drift.sh`), хук ничего не делает. Форматы payload сверены с кодом приложений (Kimi Code.app, ZCode.app `glm/zcode.cjs`, `opencode-ai@1.19.5`), а не только с документацией.

| | Kimi Code | ZCode | OpenCode 1.x |
|---|---|---|---|
| Правила | `AGENTS.md`, `.kimi-code/AGENTS.md` | `AGENTS.md` (+`~/.zcode/AGENTS.md`) | `AGENTS.md`, иначе `CLAUDE.md` |
| Навыки | `.agents/skills`, `~/.agents/skills`, плагин | `~/.zcode/skills`, плагин | `.claude/skills`, `.agents/skills`, `~/.agents/skills` |
| Хуки | `.kimi-plugin/plugin.json` → `hooks[]`; cwd хука = корень плагина, проект берётся из `payload.cwd` | `.claude-plugin` + `hooks/hooks.json`, подставляет `${CLAUDE_PLUGIN_ROOT}`, ставит `ZCODE_PLUGIN_ROOT` | `.opencode/plugins/x-harness.js`, `tool.execute.before`, блок — `throw` |
| Блок | exit 2 + stderr; прочие коды — fail-open | exit 2 + stderr | exit 2 переводчика → `throw` |
| Роли | `.agents/agents/*.md` — указатели на `.claude/agents` (`--clients kimi`) | только пользовательские — не ставятся | плагин регистрирует `.claude/agents/*.md` через хук `config` |
| MCP | `.kimi-code/mcp.json` — не ставится (новый корневой путь, `paths.conf` блокирует его fail-closed) | `.agents/mcp.json` → `../.mcp.json` (`--clients zcode`) | не ставится |

Уровень подтверждения (5.8):
- OpenCode — уровень 4: в живой сессии с моделью `opencode/glm-5.3-flash-free` `write` индекса отклонён registry-guard, `git commit` без токена отклонён commit-gate, разрешённая запись прошла; восемь ролей видны в `opencode agent list`.
- ZCode — уровень 2: `zcode plugin validate` ok, установка в изолированный HOME показывает `hooks: 2`; перевод payload — тесты.
- Kimi Code — уровень 1: схема манифеста и payload сверены с кодом приложения; перевод — тесты.
- Codex-плагин — уровень 2: `codex plugin add` ставит его в изолированный `CODEX_HOME`, `codex debug prompt-input` показывает `x-harness:x-harness`. Если в проекте есть `.codex/hooks.json`, плагинный хук пропускается.

GLM, DeepSeek, Kimi — модели. Внутри Claude Code или Codex они наследуют адаптер этого клиента.

### 2.5. Generic

Минимальный набор: `AGENTS.md` (или `CLAUDE.md`, если клиент его понимает), `.githooks/` с `core.hooksPath`, `bin/xh` для `gate`/`drift`/`merge-ready`/`hook`. Остальное — инструкции агенту. Это честный режим: правила работают как текст, принуждение — Git-хуки и ручной `bin/xh`.

## 3. Матрица совместимости

**нативно** — клиент поддерживает сам; **мост** — нужен адаптер/пакет; **инструкция** — только текст; **—** — нет.

| Клиент | Правила | Навыки | Событийные хуки | Git-хуки | Субагенты |
|---|---|---|---|---|---|
| Claude Code | нативно (`CLAUDE.md`) | нативно | нативно (`settings.json`) | нативно | нативно (`.claude/agents`) |
| Codex | нативно (`AGENTS.md`) | нативно (`.agents/skills`) | нативно + trust в `/hooks` | нативно | нативно (`.codex/agents`) |
| DSH + Claude-мост | нативно (`AGENTS.md`/`CLAUDE.md`) | нативно | мост, 7 событий; нужен matcher-адаптер | нативно | нативно; роли переносить отдельно |
| DSH + Codex-мост | нативно | нативно | мост, 5 событий; файловые аргументы неполные | нативно | нативно |
| DSH + community | нативно | нативно | мост, 8 событий; нужен адаптер + env-обёртка | нативно | нативно |
| GLM через Claude/Codex | наследует | наследует | наследует | наследует | наследует |
| GLM standalone / generic | `AGENTS.md` | вручную | — | нативно | инструкция |

Честные пробелы:
- В payload нет `Stop`/`PostToolUse`; добавлять их при переносе не нужно, иначе набор перестанет совпадать с манифестом.
- DSH Claude-мост не потребляет plain stdout `SessionStart`: предупреждения `plans-drift.sh` могут не дойти до модели.
- DSH Codex-мост не передаёт `file_path` для не-shell инструментов.
- Community-плагин не официальный: фиксировать версию, читать код, не включать автоподтверждение.
- Windows: хуки на bash, нужен Git Bash/WSL; запуск `.claude/settings.json`-команд в PowerShell/CMD **не подтверждён**.
- Симлинки `.claude/skills/*` на Windows без поддержки симлинков ломаются; включать Developer Mode или `core.symlinks=true`, либо копировать реальные каталоги.
- Модели `fable/opus/sonnet/haiku` — имена среды Claude; в другом клиенте выбирать доступные модели по назначению роли. Подделывать независимое ревью запрещено.

## 4. Протокол установки

### 4.1. Режимы и флаги `install.sh`

| Флаг | Значение |
|---|---|
| `--project DIR` | целевой проект (по умолчанию текущий каталог) |
| `--profile full|planning` | `full` — Laravel-профиль, snapshot (по умолчанию); `planning` — строгий портативный слой планирования в любом проекте (E2/E18/E16, защита main, Quality Gate по командам проекта); для planning `--mode` игнорируется |
| `--mode snapshot|port` | snapshot = payload как поставляется; port = адаптация параметров под ваш проект (имеет смысл только для `--profile full`) |
| `--clients auto|all|claude,codex,dsh,generic|none` | `auto` определяет по команде или каталогу `~/.claude`, `~/.codex`, `~/.dsh`; generic включается всегда |
| `--skills auto|project|global|both|none` | `auto` = project + global; `project` = симлинки в `.agents/skills` и `.dsh/skills`; `global` = копии в `~/.claude/skills`, `~/.codex/skills`, `~/.dsh/skills`, `~/.agents/skills` + сам `x-harness` |
| `--dsh-hooks none|bridge|community` | `none` по умолчанию; `bridge` требует `--dsh-version` и `dsh` в PATH |
| `--dsh-profile NAME` | профиль DSH для моста (по умолчанию `web`) |
| `--dsh-version VER` | точная версия моста; равна версии Host |
| `--force` | перезаписать существующие файлы с backup |
| `--fix-paths` | переписать все строки `cwd =` в `.codex/config.toml` на целевой проект |
| `--dry-run` | только показать план |
| `--no-verify` | не запускать `verify.sh` в конце |
| `--no-git` | разрешить проект без git (git-хуки не подключаются) |

Для `--profile planning` набор конфликтов свой: `.claude`, `.githooks`, `AGENTS.md`, `planning/README.md` (при `--clients codex` — ещё `.codex/hooks.json` и `.codex/hooks/claude-compat.py`). Существующий `planning/` профиль не перезаписывает — только `planning/README.md`. `.ai/`, `.mcp.json`, `boost.json`, `CLAUDE.md` профиль не ставит и не трогает. Подробно — 09.

Фактическое поведение конфликтов (по коду `install.sh`): если в проекте уже есть любой из `.claude`, `.ai`, `.codex`, `.githooks`, `CLAUDE.md`, `AGENTS.md`, `.mcp.json`, `boost.json` или `planning/README.md`, установка без `--force` завершается ошибкой. С `--force` каждый существующий элемент **перемещается** в `<project>/.x-harness-backup.<YYYYmmdd-HHMMSS>/`, затем копируется payload. Пропуска идентичных файлов нет. Поэтому формулировка «идемпотентен» в README/SKILL означает «повторяемо и с backup», а не «не трогает совпадающее»: **расхождение с кодом**, учитывать при обновлении.

`--mode port` в полном профиле сейчас не преобразует файлы: это только метка. Параметры из 4.3 заменяются вручную (кроме `cwd` при `--fix-paths`). Полной автоматизации port-режима нет — это **не подтверждённое** обещание пакета.

Для `--profile planning` перенос реально port-совместим: констант Laravel-профиля в профиле нет, все параметры проекта вынесены в `.claude/planning.conf`, а `--mode` игнорируется. Список параметров из 4.3 к planning-профилю **не применяется**; его конфиг и ограничения — в [09-planning-profile.md](09-planning-profile.md).

Planning-профиль ставится **строгим по умолчанию** (`STRICT=on`): код — только на `feature/PLAN-N-*`/`hotfix/*`, коммит на `MAIN_BRANCH` агенту запрещён, защищённые пути — по маркеру владельца `hooks-edit`, мерж в main — по маркеру `merge`, `--no-verify`/`-n`/снятие `core.hooksPath` запрещены, Quality Gate — команды проекта `GATE_FAST`/`GATE_MERGE` (пусто = пропуск). Отключается только владельцем — `STRICT=off` в `.claude/planning.conf`. **Laravel Quality Gate (Larastan/Pint/PHPUnit/Dusk) в профиль не входит.**

### 4.2. Последовательность

1. Прочитать `SKILL.md` и `references/00-index.md`. Проверить пакет: `./verify.sh --quiet` (0 = манифест совпал с `harness/`).
2. Сделать внешний backup проекта (Git-ветка или копия), затем установить:
   `./install.sh --project /path/to/project --clients auto --skills auto`
3. Если в проекте уже есть обвязка — сначала сравнить `./verify.sh --project /path/to/project`; при осознанной замене: `--force`. Backup появится в `.x-harness-backup.<TS>`.
4. Для другого проекта: `--mode port`, затем заменить параметры из 4.3 и выполнить `--fix-paths`. Если нужен только строгий слой планирования (не Laravel) — `--profile planning` (09): port-параметры не требуются, строгий слой включён по умолчанию.
5. Проверить parity: `./verify.sh --project /path/to/project`; при необходимости `--tests`.
6. Подключить событийные хуки клиента (раздел 2) и подтвердить trust.
7. Перезапустить клиент/профиль: настройки читаются при старте.
8. Выполнить приёмку (раздел 5). До неё статус — «настроено, но исполнение не подтверждено».

Копировать: только `harness/` (полный список — раздел 1) и сам пакет skill. Не копировать: `.claude/state/`, `.claude/settings.local.json`, `.claude/worktrees/`, `.env`, credentials, `~/.claude.json`, личную память, ревью-маркеры, `outputs/`, `node_modules/`, `vendor/`, `__pycache__/`, логи. Установка эти пути не трогает. Backup можно удалить только после успешной проверки; команды `uninstall` в пакете нет — откат = восстановление нужных путей из `.x-harness-backup.<TS>` вручную.

### 4.3. Параметры port-режима полного профиля

| Параметр | Где в payload | Что заменить |
|---|---|---|
| Основная ветка | `main` в `branch-guard`, `merge_checks.py`, `quality-gate.sh`, `.githooks/pre-push` (`origin/main`) | имя ветки проекта |
| Классификация путей | `.claude/hooks/paths.conf` | полный список корневых путей; иначе fail-closed заблокирует коммиты |
| Денежные пути | `.claude/hooks/money-paths.txt` | маски проекта или удалить правило E12 |
| Инструкции | `CLAUDE.md`, `AGENTS.md` | текст правил и ссылки |
| Реестры | `planning/`, `.claude/scripts/registry.sh` | структура и индексы проекта |
| Контейнер | `$COMPOSE_PROJECT-horizon-1` (`COMPOSE_PROJECT_NAME` или имя каталога основного checkout в нижнем регистре), `/var/www/html` в `quality-gate.sh` | имя контейнера и контейнерный корень |
| Тестовые БД | `app_dusk`, `testing` | имена БД проекта |
| cwd Codex | `.codex/config.toml` → `mcp_servers.laravel-boost.cwd` | `--fix-paths` или вручную |
| Индекс памяти | `plans-drift.sh`: `$HOME/.claude/projects/<путь проекта, не-алфанумерики заменены на ->/memory/MEMORY.md` | `HARNESS_MEMORY_INDEX`, если индекс лежит в другом месте |
| Навыки | симлинки `.claude/skills/*` → `.ai/skills/*` | сохранить относительные ссылки |
| Роли | `.claude/agents/*.md` | модели и обязанности под среду |
| Команды проверок | `quality-gate.sh` | sail/docker/phpunit/dusk проекта |

Все параметры этой таблицы относятся к `--profile full`. Для `--profile planning` они не нужны: констант Laravel-профиля в профиле нет, а параметры проекта живут в `.claude/planning.conf` (`MAIN_BRANCH`, `CODE_ROOTS`, шаблоны веток, пороги) — см. [09-planning-profile.md](09-planning-profile.md), раздел 4.

Проверить поиском: `origin/main`, `main...HEAD`, `CLAUDE_PROJECT_DIR`, `/var/www/html`, `<project>-horizon-1`, `app_dusk`, абсолютные пути хоста. Ни одна константа Laravel-профиля не должна остаться неадаптированной в вашем проекте.

### 4.4. Куда ставится skill

`install.sh --skills global` копирует `x-harness` в глобальные каталоги обнаружения. Проектные корни навыков он заполняет только навыками пакета, но не самим пакетом; для project-local обнаружения пакета нужен отдельный symlink.

| Клиент | Куда положить `x-harness` | Проверка |
|---|---|---|
| Claude Code | глобально `~/.claude/skills/x-harness` (ставит `--skills global`) или symlink в `<repo>/.claude/skills/x-harness` | `/skills`, `/context` |
| Codex | `~/.agents/skills/x-harness` или `<repo>/.agents/skills/x-harness` | `/skills` или `$` |
| DSH | `~/.dsh/skills/x-harness` (ставит `--skills global`), `~/.agents/skills/x-harness`, или symlink в `<repo>/.dsh/skills/x-harness` / `<repo>/.agents/skills/x-harness` | новая сессия: skill в каталоге |
| Generic/GLM | любой путь; передать агенту путь к `SKILL.md` | прочитан и применён |

DSH: `SKILL.md` должен лежать на верхнем уровне каталога навыка; вложенный `references/` допустим, вложенный `SKILL.md` не обнаруживается. Если навык не появился — проверить frontmatter (`name`, `description`) и что каталог — прямой потомок `skills/`.

## 5. Приёмка

### 5.1. Целостность пакета и parity

`MANIFEST.sha256` — не формат `sha256sum -c`: строки `H <режим> <sha256> <путь>` и `L <цель> <путь>`. Поэтому проверять только `verify.sh`:
```bash
./verify.sh                       # harness/ <=> MANIFEST.sha256
./verify.sh --project /path/to/project   # установленная копия + core.hooksPath
./verify.sh --project /path/to/project --tests   # плюс smoke-тесты хуков
./verify.sh --manifest            # пересчитать манифест после обновления harness/
./verify.sh --profile planning --project /path/to/project   # состав planning-профиля и git-хуки
```
Коды: 0 — совпадает, 1 — расхождения, 2 — ошибка аргументов/окружения. `verify.sh --project` сравнивает SHA-256, режим файла и цели симлинков; вывод `missing/changed/extra/link/mode` — конкретные расхождения. Ожидается 0 проблем. `install.sh` запускает verify автоматически, если не указан `--no-verify`.

Ручная точечная проверка: строка манифеста `grep ' CLAUDE.md$' MANIFEST.sha256` должна совпасть с `shasum -a 256 harness/CLAUDE.md` и с установленным файлом. Симлинки проверять отдельно: `AGENTS.md -> CLAUDE.md` и шесть `.claude/skills/*`; сравнение содержимого без учёта ссылок не ловит подмену ссылки копией.

Приёмка самого пакета: `bash tests/acceptance.sh`. Скрипт делает манифест-проверку, установку в чистый временный git-репозиторий с `HOME=$TMP/home` и `--clients none --skills none --no-verify`, затем parity и `bin/xh doctor`, проверку всех Codex-ролей, конфигурации гейтов, planning/strict-сценарии и безопасность установщика; успех — строка `acceptance: OK`. Это проверка установки и parity, но не исполнения хуков в клиенте.

Приёмка planning-профиля: `bash tests/acceptance-planning.sh` — базовые сценарии на временном **не-Laravel** git-репозитории: состав установки, `registry.sh check`, идемпотентность `planning-init.sh`, `add` PLAN/HF/RM, токен коммита (с токеном — проходит, без — блок), прямой Edit индекса (exit 2), owner-ok для RM и закрытия плана, drift, `verify.sh --profile planning` и повторная установка с `--force`. Полный список — SPEC, раздел 8, и [09-planning-profile.md](09-planning-profile.md).

Приёмка строгого слоя: `bash tests/acceptance-strict.sh` — E2/E18/E16, `branch-guard`/`commit-gate`/`merge-gate`/`main-push-guard`, git `pre-commit`/`pre-push`, маркер `merge`, `GATE_MERGE`, сгенерированные Codex/DSH-конфиги. Сценарии — SPEC, раздел 9, и [09-planning-profile.md](09-planning-profile.md), раздел 7.

### 5.2. Обнаружение skill

Критерий: клиент показывает `x-harness` в каталоге навыков, `SKILL.md` имеет frontmatter с `name: x-harness` и `description`. Claude Code — `/skills`/`/context`; Codex — `/skills`; DSH — новая сессия; generic — агент прочитал `SKILL.md`. Наличие файла на диске обнаружением не считается.

### 5.3. Событийные хуки: положительный и отрицательный сценарий

Сценарии — в одноразовом клоне/fixture, не в рабочем дереве продукта. Хуки вызывать абсолютным путём и с `CLAUDE_PROJECT_DIR`: относительный путь ломает внутренний вызов `owner_ok.py` (проверено: exit 2 из-за отсутствующего файла). В установленном проекте удобно `bin/xh hook <name>`: он сам выставляет `CLAUDE_PROJECT_DIR`.

| Хук | Положительный сценарий | Отрицательный сценарий | Ожидание |
|---|---|---|---|
| `plans-drift.sh` | чистый репозиторий | искусственный drift в fixture | всегда exit 0; во втором — предупреждение в stdout |
| `branch-guard.sh` | `feature/PLAN-N-*` + `app/a.php` | `main` + `app/a.php` | 0 / 2 + причина |
| `registry-guard.sh` | `registry.sh set-status` | прямой Edit `planning/ACTIVE_PLANS.md` | 0 / 2 + «используй registry.sh» |
| `commit-gate.sh` | `git status` | `git commit --no-verify -m x` | 0 / 2 + «обход запрещён» |
| `merge-gate.sh` | `git pull --ff-only` | `git merge feature/x` в fixture | 0 / 2 + причина |
| `main-push-guard.sh` | push feature-ветки | `git push --force origin main` | 0 / 2 + причина |
| `owner-ok-guard.sh` | обычная Bash-команда | запуск `.claude/scripts/owner-ok.sh` | 0 / 2 + «только владелец» |
| `big-read-guard.sh` | Read с `offset`/`limit` | полный Read файла >300 строк/>40960 байт | 0 / 2 + предложение диапазона |

Проверенные вручную примеры (30.10.2026):
```bash
P=/path/to/x-harness
printf '%s' '{"tool_name":"Bash","tool_input":{"command":"git commit --no-verify -m x"}}' | "$P/bin/xh" hook commit-gate; echo $?   # 2
printf '%s' '{"tool_name":"Edit","tool_input":{"file_path":"'"$PWD"'/planning/ACTIVE_PLANS.md"}}' | "$P/bin/xh" hook registry-guard; echo $?  # 2
printf '%s' '{"tool_name":"Bash","tool_input":{"command":".claude/scripts/owner-ok.sh hooks-edit feature/x"}}' | "$P/bin/xh" hook owner-ok-guard; echo $?  # 2
printf '%s' '{"tool_name":"Read","tool_input":{"file_path":"'"$PWD"'/outputs/AGENT_HARNESS.md"}}' | "$P/bin/xh" hook big-read-guard; echo $?  # 2
```
Положительные сценарии обязательны: проверка, которая блокирует всё, тоже неверна.

### 5.4. Git-хуки

```bash
git config --get core.hooksPath     # .githooks (или абсолютный путь, оканчивающийся на .githooks)
.claude/scripts/install-githooks.sh # повторный запуск: «уже подключено»
```
В fixture проверить: `commit-msg` отклоняет сообщение без PLAN-N/HF-N на кодовой ветке; `pre-commit` видит staged-дерево; `pre-push` проверяет пушимый SHA, а не рабочее дерево; `post-merge` создаёт локальный тег только на `main`. Абсолютный `core.hooksPath` корректен, но `plans-drift.sh` сравнивает строку с `.githooks` и может дать ложное предупреждение — известное расхождение, не поломка.

### 5.5. Бюджеты инструкций

```bash
wc -c CLAUDE.md .claude/rules/* planning/README.md
```
На 30.10.2026: `CLAUDE.md` — 27662 байта, стартовый набор — 31635 байт. Лимиты: `CLAUDE.md` >36864 байт блокируется `commit-gate`; стартовый набор >53248 байт даёт предупреждение `SessionStart`. DSH-бюджет 65536 байт: `CLAUDE.md` плюс цепочка помещается, дубль `AGENTS.md`/`CLAUDE.md` сворачивается. Codex: `project_doc_max_bytes = 131072` в локальном `.codex/config.toml`; без него дефолт 32 КиБ. При превышении DSH печатает «Workspace instruction budget ...», Codex — предупреждение об усечении; это не «зелёная» проверка.

### 5.6. Smoke-тесты

`./verify.sh --project <dir> --tests` запускает `python3 -m unittest discover -s .claude/hooks -p 'test_*.py'`. Точечно:
```bash
python3 .claude/hooks/test_planning_gates.py
python3 .claude/hooks/test_e18.py
python3 .claude/hooks/test_owner_ok.py
python3 .claude/hooks/test_merge_gate.py
python3 .claude/hooks/test_main_push_guard.py
python3 .claude/hooks/test_githooks.py
python3 .claude/hooks/test_quality_gate.py
python3 .claude/scripts/test_registry.py
python3 .codex/hooks/test_claude_compat.py
```
Наборы создают временные репозитории и не должны менять рабочее дерево; падение — блокер приёмки. Наблюдение 30.10.2026: `test_githooks.py` в sandbox DSH дал 26 тестов, 1 падение (`test_amend_no_edit_on_roadmap_commit_with_rm_token`): `/bin/ps` запрещён песочницей, а `commit_checks.is_amend` вызывает `ps`. Это ограничение среды, а не доказанный дефект payload; повторять в обычном терминале владельца.

### 5.7. Приёмка DSH (мост)

1. Поставить бандл: `dsh plugin --profile <profile> add @deepseek-ai/dsh-hooks-claude-code@<host> @deepseek-ai/dsh-hook-protocol@<host> github:cheusbeats/x-harness` (или `install.sh --dsh-hooks bridge --dsh-version <host>`), перезапустить профиль.
2. Проверить вызов событий probe-хуками: SessionStart — command `echo ok >> /tmp/harness-dsh-sessionstart` (файл появился); PreToolUse — matcher `bash`, command `echo denied >&2; exit 2` (безобидная Bash-команда заблокирована).
3. В «Настройки → Плагины → Список плагинов» найти `hooks-claude-code` с id `include:x-harness-hooks`, статус «смонтирован». Negative-сценарий в проекте с обвязкой: Edit индекса реестра блокируется, `git commit --no-verify` блокируется. Если PreToolUse не срабатывает — посмотреть имя инструмента, которое передаёт Host, и добавить его в matcher `hooks/dsh-hooks.json` и `TOOL_ALIASES` переводчика.
4. `CLAUDE_PROJECT_DIR` выставляет переводчик — корень git-проекта из `cwd`.

### 5.8. Критерий «настроено, но исполнение не подтверждено»

Уровни: (1) конфигурация записана; (2) клиент её загрузил/показал; (3) событие реально вызвало хук; (4) проверка заблокировала запрещённое и пропустила разрешённое. Перенос принят только на уровне 4 для каждого хука, который должен работать. Остальное перечисляется в отчёте с причиной: нет клиента, не подтверждён trust, мост не поддерживает событие, sandbox запретил инструмент.

## 6. Ограничения

- Декларация в JSON не равна исполнению: нужен прогон сценария.
- Доверие к хукам подтверждает пользователь (Codex — `/hooks`; Claude Code — доверие рабочей области). Правка файла сбрасывает доверие.
- После установки перезапустить клиент или профиль: открытая сессия может работать со старым набором.
- Многие внутренние сбои хуков fail-open; merge-gate и owner-claim — fail-closed. «Хук не запустился» нельзя выдавать за успешную проверку.
- Мосты DSH реализуют подмножество событий и различаются payload; community-плагин не официальный.
- На Windows нужен bash (Git Bash/WSL), LF-переводы строк и поддержка симлинков. `.gitattributes` исходного проекта задаёт `* text=auto eol=lf`, но в payload не входит — при port-переносе скопировать отдельно или выставить `core.autocrlf=false`.
- Имена моделей и slash-команды не переносимы как API: переносится назначение роли.
- Пакет не должен включать секреты, личную память, глобальные разрешения и накопленные допуски.
- Планировочный профиль (`--profile planning`) ставит **портативный строгий слой** (E2/E18/E16, защита main, Quality Gate по командам проекта), но без Laravel-гейтов, без E12/E13/E17 и с честными границами: событийные хуки — только Claude/Codex (DSH — мост), в generic `--no-verify` технически обходим, `GATE_FAST`/`GATE_MERGE` пусты по умолчанию. Ограничения — [09-planning-profile.md](09-planning-profile.md).

## 7. Источники

Локальные:
- `outputs/AGENT_HARNESS.md`, строки 23–41 (порядок подключения, состав переноса), 527–558 (сценарии приёмки);
- `SKILL.md`, `references/00-index.md`, `README.md` — карта пакета и границы;
- `install.sh`, `verify.sh`, `bin/xh`, `tests/acceptance.sh`, `tests/acceptance-strict.sh` — фактическая установка/проверка;
- `profiles/planning/SPEC.md`, `profiles/planning/README.md`, `profiles/planning/AGENTS.md`, `profiles/planning/planning/README.md`, `profiles/planning/skill/SKILL.md`, `references/09-planning-profile.md` — planning-профиль и его приёмка;
- `.claude/settings.json` — события и matchers payload; `.codex/hooks.json`, `.codex/config.toml` — Codex-адаптер;
- `.claude/scripts/install-githooks.sh`; `.claude/hooks/paths.conf`, `money-paths.txt`, `.claude/scripts/quality-gate.sh`, `.githooks/*` — параметры port-режима;
- `.claude/hooks/test_*.py`, `.codex/hooks/test_claude_compat.py` — smoke-наборы.

Внешние:
- Claude Code: memory — https://code.claude.com/docs/en/memory; skills — https://code.claude.com/docs/en/skills; hooks — https://code.claude.com/docs/en/hooks; субагенты — https://code.claude.com/docs/en/sub-agents;
- Codex: AGENTS.md — https://learn.chatgpt.com/docs/agent-configuration/agents-md; skills — https://learn.chatgpt.com/docs/build-skills; hooks — https://learn.chatgpt.com/docs/hooks; субагенты — https://learn.chatgpt.com/docs/agent-configuration/subagents;
- AGENTS.md как формат — https://agents.md/;
- DSH: инструкции — https://unpkg.com/@deepseek-ai/dsh-agent-instructions@0.2.1-rc.5/README.md; навыки — https://unpkg.com/@deepseek-ai/dsh-skill-filesystem@0.2.1-rc.5/README.md; домашние пути — https://unpkg.com/@deepseek-ai/dsh-home-paths@0.2.1-rc.5/README.md;
- DSH-мосты: Claude — https://unpkg.com/@deepseek-ai/dsh-hooks-claude-code@0.2.1-rc.5/README.md; Codex — https://unpkg.com/@deepseek-ai/dsh-hooks-codex@0.2.1-rc.5/README.md; протокол — https://unpkg.com/@deepseek-ai/dsh-hook-protocol@0.2.1-rc.5/README.md;
- Community-плагин: https://www.npmjs.com/package/dsh-hooks-plugin (README v0.2.15);
- GLM Coding Plan: https://docs.z.ai/devpack/overview; Claude Code через GLM: https://docs.z.ai/devpack/tool/claude;
- OpenCode: https://opencode.ai/docs/rules/; плагины — https://opencode.ai/docs/plugins/.

Внешние ссылки проверены 30.10.2026. Утверждения без ссылки или локального файла помечены как «не подтверждено».
