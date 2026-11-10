# 00. Карта правил X-Harness

Что это: навигатор по всей обвязке в одном skill. Здесь — какие источники правил существуют, что из них обязательно, чем правило реально принуждается и в каком порядке читать. Детали — в файлах 01–09 (09 — отдельный planning-профиль для не-Laravel проектов).

## Приоритет (при расхождении)

1. Прямое указание владельца и ограничения среды (sandbox, approval, доступность инструментов).
2. `CLAUDE.md` / `AGENTS.md` — правила проекта. Обычно это один файл (AGENTS.md — симлинк).
3. `.ai/guidelines/*.md` — environment / filament / pillars / ui-rules; внедряются Laravel Boost в контекст.
4. `.claude/reference/*.md` — справочники: planning-registries, environment, filament-patterns, laravel-boost-guidelines, sail-artisan-commands, local-workers.
5. Исполняемые хуки и скрипты — фактическое принуждение. Именно они, а не текст, блокируют действие.
6. Устаревшие адаптеры (`.cline`, `.trae`), локальная память, комментарии — могут отставать; при конфликте верить 1–5.

Правило «задекларировано, но не исполняется» фиксируй честно: в тексте — требование, в проверке — фактическое поведение. Не выдавай одно за другое.

## Источники (payload — в `harness/`, planning-профиль — в `profiles/planning/`)

| Путь | Что | Тип | Читать когда |
|---|---|---|---|
| `harness/CLAUDE.md` (`AGENTS.md`) | главные правила проекта: реестры, git, окружение, Quality Gate, столпы, UI, оркестрация | правила | в начале каждой сессии |
| `harness/.ai/guidelines/environment.md` | Sail/Docker/Horizon, npm на хосте, composer refresh, воркеры | правила | подъём окружения, тесты |
| `harness/.ai/guidelines/filament.md` | Filament v5: namespace, частые ошибки, artisan | правила | любая правка админки |
| `harness/.ai/guidelines/pillars.md` | Resource Economy, Query Building, полное покрытие множеств | правила | проектирование/ревью кода |
| `harness/.ai/guidelines/ui-rules.md` | обязательные навыки, запрет native dialogs, NO PHP в Blade | правила | любой UI/Livewire/Blade |
| `harness/.claude/reference/planning-registries.md` | схема RM/PLAN/HF, статусы, E1–E19, ревью плана | правила | работа с `planning/` |
| `harness/.claude/reference/environment.md` | краткий подъём окружения | справка | старт |
| `harness/.claude/reference/filament-patterns.md` | рецепты Filament (формы, таблицы, экшены, тесты) | справка | UI |
| `harness/.claude/reference/laravel-boost-guidelines.md` | дословные общие Laravel-правила (Foundation/PHP/Sail/tests/Pint/PHPUnit) | правила | Laravel-правки |
| `harness/.claude/reference/sail-artisan-commands.md` | команды Sail/Artisan/Composer/npm/анализ/тесты | справка | команды |
| `harness/.claude/reference/local-workers.md` | дешёвая ступень делегирования через local-workers MCP | справка | мелкие задачи |
| `harness/.claude/rules/context-hygiene.md` | гигиена контекста (читать диапазоном, tail, 3 попытки) | правила | всегда |
| `harness/.claude/rules/working-rules.md` | рабочие правила Claude/Codex: БД не вайпать, кто что ревьюит | правила | всегда |
| `harness/.claude/agents/*.md` | 8 ролей субагентов + модели/инструменты/границы | правила | перед делегированием |
| `harness/.claude/hooks/*` | 9 событийных хуков + python-модули + тесты | исполнение | хук блокирует / ставишь обвязку |
| `harness/.claude/scripts/*` | registry.sh, quality-gate.sh, merge-ready.sh, mark-reviewed.sh, owner-ok.sh, release-tag.sh, scan-secrets.sh, plan-code-refs.sh, blast-radius.sh, install-githooks.sh | исполнение | по задаче |
| `harness/.claude/skills/` + `harness/.ai/skills/` | 9 проектных навыков (6 канонических в `.ai/skills`, 3 локальных, симлинки) | правила/процедуры | перед работой по теме |
| `harness/.githooks/*` | pre-commit, commit-msg, pre-push, post-merge — настоящие git-хуки | исполнение | всегда (не обходятся агентом) |
| `harness/.codex/` | `config.toml`, `hooks.json`, `claude-compat.py` — адаптер Codex | исполнение/адаптер | Codex |
| `harness/planning/README.md` | что где в `planning/`, как поддерживать | правила | планирование |
| `harness/.claude/settings.json` | проводка событий Claude: SessionStart + PreToolUse(Edit/Write/Bash/Read) | исполнение | диагностика хуков |
| `harness/.mcp.json`, `harness/boost.json` | MCP laravel-boost, список навыков/guidelines Boost | конфиг | подъём среды |
| `profiles/planning/` + `references/09-planning-profile.md` | planning-профиль (`--profile planning`): реестры RM/PLAN/HF, owner-ok, git-хуки — без Laravel и констант Laravel-профиля | сборка профиля + правила | нужен слой планирования в не-Laravel проекте |

## Порядок чтения по задаче

- **Старт сессии:** `CLAUDE.md` → `planning/ACTIVE_PLANS.md` → резюме нужного плана → `git status`, ветка, `plans-drift`.
- **Планирование:** 01 → `planning/README.md` → `registry.sh`.
- **Код:** 07 → 05 (навыки) → 06 (окружение) → 02 (ветки/тесты).
- **Коммит/ревью/мерж:** 02 → 03 (что именно блокирует) → `quality-gate.sh`/`merge-ready.sh`.
- **Хук мешает:** 03 → исходник хука → его тест; не отключать хук, а понять проверку.
- **Делегирование:** 04 → карта ролей.
- **Установка/перенос:** 08 → `install.sh` → `verify.sh`.
- **Планирование в не-Laravel проекте:** 09 → `profiles/planning/README.md` → `planning/README.md` установленного проекта.
- **Аудит безопасности/денег:** 07 + `money-paths.txt` → `compliance-checker`.

## Правило → принуждение (кратко)

| Требование | Чем принуждается |
|---|---|
| Ветка не `main` для кода | `.claude/hooks/branch-guard.sh` (PreToolUse) + `.githooks/pre-commit` |
| Индексы `planning/` только через registry.sh | `.claude/hooks/registry-guard.sh` + `registry.sh` |
| Larastan + Pint перед коммитом | `.claude/hooks/commit-gate.sh` → `quality-gate.sh --fast` (агентский слой; нативный `pre-commit` Larastan/Pint не гоняет) |
| Мерж только с гейтом/ревью/словом | `.claude/hooks/merge-gate.sh`, `merge_checks.py`, `merge-ready.sh` |
| Пуш `main` без прямых коммитов | `.claude/hooks/main-push-guard.sh` + `.githooks/pre-push` |
| Защищённые файлы/owner-ok | `.claude/hooks/owner-ok-guard.sh` + `owner_ok.py` + `paths.conf` |
| Большие чтения | `.claude/hooks/big-read-guard.sh` |
| БД не чистить (`migrate:fresh`, `db:wipe` и т.п.) | `.claude/hooks/db-wipe-guard.sh` + `db_wipe_checks.py` |
| Дрейф реестров | `.claude/hooks/plans-drift.sh` (SessionStart) |
| Зависимость shell-хуков | `jq` (разбор payload); без `jq` хуки часто fail-open — проверяй наличие |
| Conventional commits + PLAN/HF | `.githooks/commit-msg` + `commit-gate.sh` |
| `--no-verify` запрещён | `commit_checks.py` |
| Секреты в staged-диффе | `commit-gate.sh` → `scan-secrets.sh` (только агентский слой; нативный `pre-commit` секреты не сканирует) |
| Денежные пути | `money-paths.txt` + `compliance-checker` + ревью-процедура |

Полные списки и коды возврата — 03.

## Глоссарий

- **PLAN** — план в `planning/plans/` для работы с проектированием; **HF** — хотфикс для правок без плана; **RM** — идея в roadmap (только по слову владельца).
- **owner-ok** — маркер владельца в `.claude/state/owner-ok`, выдаётся только в терминале владельца (`owner-ok.sh`); агент его не создаёт.
- **Quality Gate** — `quality-gate.sh`: Larastan → Pint → PHPUnit → eslint → сверка копий скиллов; `--fast` / `--merge`.
- **merge-ready** — `merge-ready.sh <ветка>`: гейт + ревью + реестры; о слове владельца спрашивают только при READY.
- **drift** — расхождение реестров с git, которое печатает `plans-drift.sh`.
- **E1–E19** — таблица правил принуждения из `planning-registries.md` (см. 01).

## Синхронизация

`harness/` — копия, а не источник. `profiles/planning/` — самостоятельная сборка профиля: её файлы правятся в пакете, а не перекопируются откуда-либо. Меняешь правило — меняй его в источнике payload, затем перекопируй и обнови `MANIFEST.sha256` (`verify.sh --manifest`), иначе `verify.sh` покажет drift. Никогда не правь копию «по месту», если это не осознанный port-режим.
