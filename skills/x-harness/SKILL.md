---
name: x-harness
description: Универсальная обвязка агентной разработки — правила, реестры планирования (RM/PLAN/HF), git-процесс, ревью, хуки и гейты, субагенты, окружение. Использовать при работе в проекте с установленной обвязкой и при установке, переносе или проверке обвязки в агентном клиенте. Возможности клиента проверяются отдельно; название модели само по себе не определяет поддержку хуков.
---

# X-Harness — переносимая обвязка

Репозиторий x-harness — одновременно скилл и плагин. Обвязка лежит в `harness/` и ставится в проект `install.sh`. Политики живут только в проектных `.claude/hooks`. Клиенты получают их так: Claude Code — нативно, Codex — `.codex/hooks.json` или плагин, Kimi Code, ZCode и OpenCode — плагин x-harness, DSH — мост. Все неклаудовские пути идут через общий переводчик `adapters/agent-hook.py`. В проекте без обвязки плагинные хуки ничего не делают. DeepSeek и GLM — модели; возможности определяет клиент.

## Когда читать

- Работа в репозитории с установленной обвязкой: перед первой правкой кода, плана или реестра.
- Установка/перенос обвязки в другой проект или другого агента.
- Проверка целостности файлов и фактического исполнения в целевом клиенте.
- Спор о правиле: здесь карта источников и приоритет.

## Установка скилла и выбор клиента

Навык распространяется через GitHub: `npx skills add cheusbeats/x-harness --skill x-harness`. Пользователь выбирает агентный клиент; `-g` устанавливает навык глобально. Модель (GLM, DeepSeek и другие) не определяет формат инструкций, навыков и событийных хуков — ориентируйся на фактический клиент.

При поручении установить обвязку сначала определи целевой проект и клиент. Если скилл установлен менеджером навыков без собственного `.git` и без `.x-harness-package.json`, используй `bash <skill-base-dir>/scripts/install-from-source --project <target> --clients auto --skills project`, а не `install.sh` из такой копии. Подставь фактический каталог скилла из среды; не выполняй относительный путь из целевого проекта. Скрипт получает `main` из исходного репозитория и запускает штатный установщик во временном Git checkout. Для планировочного слоя добавь `--profile planning`. Не заменяй существующие файлы через `--force` без поручения на замену.

Событийные хуки клиентов Kimi Code, ZCode, OpenCode (и Codex без проектного `.codex/hooks.json`) ставятся плагином x-harness. Команды установки плагина приведены в README репозитория и печатаются в конце `install.sh`. Для клиента без адаптера используй общий слой: `AGENTS.md`, `.agents/skills`, Git-хуки и явные команды `bin/xh`. Проверяй чтение навыка и исполнение хуков раздельно; не обещай одинакового принуждения только на основании названия модели.

## Приоритет правил

1. Прямое указание владельца и ограничения среды.
2. `CLAUDE.md` / `AGENTS.md` — правила проекта (обычно один файл).
3. `.ai/guidelines/*.md` — environment / filament / pillars / ui-rules (внедряются через Laravel Boost).
4. `.claude/reference/planning-registries.md` и остальные справочники `.claude/reference/`.
5. Исполняемые хуки и скрипты — фактическое принуждение, а не декларация.
6. Устаревшие адаптеры (`.cline`, `.trae`), локальная память, комментарии — могут отставать.

При расхождении фиксируй два факта отдельно: «требуется правилом» и «фактически проверяется хуком». Обнаруженное расхождение не даёт права менять защищённые настройки/хуки/CLAUDE.md без `owner-ok`.

## Работа над самим пакетом

В репозитории `x-harness` проверяй установщик и профили командой `bash tests/acceptance.sh`, целостность — `bash verify.sh --quiet`. Эти проверки работают на временных проектах без Laravel, Sail и Docker. Правила ниже о Larastan, реестрах и Quality Gate относятся к целевому проекту, если соответствующий слой там установлен. Не запускай Laravel-гейты из `harness/` для проверки самого пакета.

## Обязательный цикл работы

1. Старт: `git status`, текущая ветка, `planning/ACTIVE_PLANS.md`, резюме нужного плана; разобрать вывод `plans-drift`.
2. Локализовать задачу и потребителей изменяемых символов. Выбрать PLAN или HF; RM — только по прямому слову владельца.
3. Код — только в ветке от `main`: `feature/PLAN-N-slug` или `hotfix/*`. Перед вызовами API — версионная документация (`search-docs`), профильные навыки.
4. Делегировать ограниченные куски подходящим субагентам, проверить фактический diff. Правка минимальная, без попутного рефакторинга.
5. Перед тестами — Larastan. Перед приёмкой делегированной работы — Quality Gate. Не ослаблять тесты ради зелёного.
6. Коммит: conventional commits на английском с токеном `PLAN-N`/`HF-N`; `--no-verify`/`-n` запрещены; перед коммитом `quality-gate.sh --fast`.
7. Ревью ≤2 проходов (полный + дельта). Деньги: один аудит opus и один Codex параллельно + одна проверка правок.
8. `merge-ready.sh <ветка>`; о слове владельца о мерже спрашивать только при READY.
9. После слова владельца — только разрешённый выпуск; новый SHA требует новых допусков.
10. Мерж и публикация `main` — только по слову владельца; закрытие плана — отдельное разрешённое действие.

## Жёсткие инварианты (нельзя)

- Прямые коммиты в `main`; `develop` не заводим; мерж/пуш `main` — только по слову владельца.
- `--no-verify`/`-n`, force-push, `+main`, `--all`/`--mirror`, чужие refspec.
- Ручная правка индексов `planning/` (только `registry.sh`); переписывание закрытых записей (`plans/closed/`, `hotfixes/HF-1…148`).
- Правка `CLAUDE.md`, хуков, настроек, `.claude/state/owner-ok` без маркера `owner-ok` от владельца.
- Копирование секретов, `.env`, `.claude/state/`, ревью-токенов, личной памяти в обвязку/коммиты.
- Нарушение Resource Economy, лестницы запросов (Eloquent → Builder → Raw SQL), полного покрытия множеств.
- Нативные браузерные диалоги; `@php` в Blade; PHP-логика в шаблонах; правки без Laravel-навыков и `search-docs`.
- Установка хуков «на глаз»: заявленный в JSON хук ≠ исполняемый; проверяй сценариями.

## Карта знаний

| Файл | Что внутри | Когда читать |
|---|---|---|
| [00-index.md](references/00-index.md) | полная карта источников правил и порядок чтения | первый заход в незнакомую тему |
| [01-planning-registries.md](references/01-planning-registries.md) | RM/PLAN/HF, `registry.sh`, E1–E19, owner-ok, закрытие плана | любая работа с `planning/` |
| [02-git-review-release.md](references/02-git-review-release.md) | ветки, коммиты, Quality Gate, ревью, merge-ready, релиз | перед коммитом/мержем |
| [03-hooks-and-gates.md](references/03-hooks-and-gates.md) | все хуки, git-хуки, Codex-адаптер, quality-gate, тесты | когда хук блокирует или ставишь обвязку |
| [04-subagents.md](references/04-subagents.md) | роли субагентов, делегирование, MCP, local workers | перед делегированием |
| [05-skills.md](references/05-skills.md) | проектные навыки, symlink-схема, обязательные навыки | перед UI/Laravel-работой |
| [06-environment.md](references/06-environment.md) | Sail/Docker/Horizon, npm на хосте, БД, команды, CI | подъём окружения, тесты |
| [07-code-standards.md](references/07-code-standards.md) | Resource Economy, Query Building, Filament 5, UI, безопасность | любая правка кода |
| [08-install-and-acceptance.md](references/08-install-and-acceptance.md) | установка в любой клиент, матрица совместимости, приёмка | установка/перенос/проверка среды |
| [09-planning-profile.md](references/09-planning-profile.md) | профиль `--profile planning`: только реестры/планы/owner-ok/git-хуки, без Laravel | нужен слой планирования в не-Laravel проекте |

Точные исходники лежат в `harness/`: `harness/CLAUDE.md`, `harness/.ai/guidelines/`, `harness/.claude/reference/`, `harness/.claude/agents/`, `harness/.claude/hooks/`, `harness/.claude/scripts/`, `harness/.githooks/`, `harness/.codex/`. Это копия, а не пересказ: при сомнении читай оригинал.

## Установка и проверка

```bash
./install.sh --project /path/to/target --clients auto --skills auto   # snapshot (payload как поставляется)
./install.sh --project /path/to/target --mode port                    # другой проект, с параметрами
./verify.sh --project /path/to/target --tests                          # parity + smoke-тесты хуков
bin/xh doctor                                                          # что подключено в текущем репо
```

`install.sh` повторяем: без `--force` при существующей обвязке — ошибка, с `--force` старые пути уходят в backup; `state`, `settings.local.json`, секреты и память не копируются. `verify.sh` сверяет `harness/` с `MANIFEST.sha256` и установленную копию с манифестом — это проверяет целостность файлов, но не их исполнение клиентом или соответствие вашему проекту.

Полный профиль при включённых навыках устанавливает `make-interfaces-feel-better` и `impeccable` из их исходных GitHub-репозиториев, без копий внутри пакета. Для установки без сети укажи `--no-upstream-skills` — тогда эти два навыка не устанавливаются. `--skills none` также отключает их загрузку.

## Планировочный профиль (любой проект)

Если нужен не snapshot целиком, а только слой управления планами с той же дисциплиной —
реестры RM/PLAN/HF, роадмап, планы, хотфиксы, owner-ok, строгий слой (E2/E18/E16, защита `main` и
Quality Gate по командам проекта) и git-хуки — есть отдельный профиль. Он ставится **строгим по
умолчанию** и переносится между агентами: правила — в `AGENTS.md`, принуждение — событийные хуки
клиента (Claude/Codex), git-хуки (везде) и `bin/xh` (generic).

```bash
./install.sh --project /path/to/project --profile planning            # ставит профиль
./install.sh --project /path/to/project --profile planning --clients none --skills none   # минимум
./verify.sh --profile planning --project /path/to/project             # проверка состава
```

Проект получает `AGENTS.md`, `planning/README.md`, `.claude/{settings.json,planning.conf,scripts/,hooks/}`
(включая портативные `branch-guard`, `commit-gate`, `merge-gate`, `main-push-guard`), `.githooks/{commit-msg,pre-commit,pre-push}`
и (при `--skills`) навык `x-harness-planning`. Не ставится: `.ai/`, `.mcp.json`, `CLAUDE.md`, полные
Laravel-хуки и Laravel Quality Gate, агенты полного профиля. `--mode` для профиля игнорируется: он всегда
port-совместим, констант Laravel-профиля в нём нет. `harness/` и `MANIFEST.sha256` не меняются.

Строгий слой: код — только на `feature/PLAN-N-*`/`hotfix/*`, коммит на `main` агенту запрещён;
защищённые пути — только с маркером владельца `hooks-edit`; мерж в `main` — с маркером `merge`;
`--no-verify` и снятие `core.hooksPath` запрещены; `GATE_FAST`/`GATE_MERGE` — команды проекта.
Отключается только владельцем (`STRICT=off`). Приёмка — `tests/acceptance-planning.sh` и
`tests/acceptance-strict.sh`.

Подробно — [09-planning-profile.md](references/09-planning-profile.md); документация профиля в пакете —
[profiles/planning/README.md](../../profiles/planning/README.md).

## Единая среда у разных агентов

| Слой | Claude Code | Codex | Kimi Code | ZCode | OpenCode | DSH | generic |
|---|---|---|---|---|---|---|---|
| Правила | `CLAUDE.md` | `AGENTS.md` | `AGENTS.md` | `AGENTS.md` | `AGENTS.md` (иначе `CLAUDE.md`) | `AGENTS.md` | передать явно |
| Навыки | `.claude/skills` | плагин или `.agents/skills` | плагин, `.agents/skills` | плагин, `~/.zcode/skills` | `.claude/skills`, `.agents/skills` | `.dsh/skills`, `.agents/skills` | `.agents/skills` |
| Событийные хуки | `.claude/settings.json` | `.codex/hooks.json` или плагин | плагин (`.kimi-plugin`) | плагин (`.claude-plugin`, `hooks/hooks.json`) | плагин (`.opencode/plugins/x-harness.js`) | бандл профиля (`dsh plugin add github:cheusbeats/x-harness`) | только git-хуки + `bin/xh` |
| Субагенты | `.claude/agents` | `.codex/agents` | `.agents/agents` (указатели на `.claude/agents`) | только пользовательские — нет | плагин регистрирует `.claude/agents` | зависит от клиента | вручную |
| Git-хуки | `.githooks` | `.githooks` | `.githooks` | `.githooks` | `.githooks` | `.githooks` | `.githooks` |

Полная матрица и ограничения — [08-install-and-acceptance.md](references/08-install-and-acceptance.md). Git-хуки подключаются через Git; `bin/xh` вызывается явно. Чтение `AGENTS.md` зависит от клиента. Событийные хуки и их доверие необходимо проверять в каждом клиенте.

## Ограничения

- SKILL.md сам по себе не устанавливает хуки и не является песочницей. Установка — `install.sh`/адаптер клиента; исполнение подтверждается сценариями.
- «Файл загружен» ≠ «политика исполняется»: после установки проверь позитивный и негативный сценарий в клиенте и перезапусти его.
- Snapshot-режим содержит параметры Laravel-профиля (контейнер `<project>-horizon-1`, БД `testing`/`app_dusk`, money-paths). Для другого проекта `--mode port` не меняет эти команды автоматически: замени параметры и исторические проверки по 08 вручную до использования; если нужен только слой планирования — `--profile planning` (09), эти параметры там не требуются.
- Внешние плагины, MCP-серверы и личная память не входят в git и не переносятся автоматически; их состав описан в 04/05/06.
