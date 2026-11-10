# 05 — Проектные навыки (skills), симлинки и Boost

**Что это:** полный инвентарь навыков — семь проектных навыков, схема симлинков, `boost.json`, обязательные навыки и правило `search-docs`.
**Когда читать:** когда агент выбирает навык под задачу, когда переносишь обвязку в другой клиент или когда навык «не подхватился».
**Срез:** 30.10.2026. Источники — `.ai/skills/*/SKILL.md`, `.claude/skills/`, `boost.json`, `config/boost.php`, `.claude/scripts/quality-gate.sh`, `outputs/AGENT_HARNESS.md`.

## 1. Полный набор: семь навыков

Проект держит **два места** для навыков. Источник правды — `.ai/skills/` (четыре навыка); локальные, не имеющие аналога в `.ai`, лежат прямо в `.claude/skills/` (три навыка).

| Навык | Где лежит | Когда включать | Что покрывает |
|---|---|---|---|
| `laravel-best-practices` | `.ai/skills/laravel-best-practices/` + симлинк | **всегда** при любой работе с Laravel | 31 правило в 7 категориях (architecture, Eloquent, controllers/routing, validation, security, performance, API); версия 2.1.0 |
| `laravel-clean-code` | `.ai/skills/laravel-clean-code/` + симлинк | реализация, рефакторинг, review, debugging PHP/Laravel/Livewire/Blade | KISS, YAGNI, DRY, прагматичный SOLID, минимальные правки, конвенции Laravel, правила Livewire, запрет `@php` в Blade; 46 файлов в `rules/` (44 правила + `_sections.md` + `_template.md`); версия 1.3.0 |
| `laravel-specialist` | `.ai/skills/laravel-specialist/` + симлинк | углублённые Eloquent, auth/Sanctum, очереди, Livewire, API, тесты | справочники `references/eloquent.md`, `routing.md`, `queues.md`, `livewire.md`, `testing.md`; версия 1.1.0 |
| `landing-page-design` | `.ai/skills/landing-page-design/` + симлинк | любая landing/marketing/web-UI работа, копирайт, дизайн-ревью | Part A — стратегия, секции, CTA, копирайт, SEO; Part B — типографика, spacing, radius, фон, hero, иконки, motion |
| `tailwindcss-development` | `.claude/skills/tailwindcss-development/` (локальный) | упоминание Tailwind; utility-классы, grid/flex, карточки, формы, responsive, dark mode | Tailwind v4: CSS-first `@theme`, `@import "tailwindcss"`, таблица замен устаревших утилит, gap вместо margin |
| `socialite-development` | `.claude/skills/socialite-development/` (локальный) | OAuth/social login, redirect/callback, scopes, providers, тесты Socialite | встроенные и community-провайдеры, `config/services.php`, `updateOrCreate` + `Auth::login`, `stateless()`, `Socialite::fake()` |
| `configuring-horizon` | `.claude/skills/configuring-horizon/` (локальный) | всё про Horizon в Laravel | супервизоры, балансировка, `horizon:install`, dashboard-gate `viewHorizon`, `horizon:snapshot`, timeout-лестница; 4 reference-файла: `supervisors.md`, `notifications.md`, `tags.md`, `metrics.md` |

Читать навык целиком не нужно: `configuring-horizon` устроен как роутинг-таблица — открывается только файл/секция, которую трогает задача.

## 2. Схема симлинков

Фактическое состояние `.claude/skills/`:

```text
.claude/skills/
├── configuring-horizon/          каталог (локальный навык)
├── socialite-development/        каталог (локальный навык)
├── tailwindcss-development/      каталог (локальный навык)
├── landing-page-design    -> ../../.ai/skills/landing-page-design
├── laravel-best-practices -> ../../.ai/skills/laravel-best-practices
├── laravel-clean-code     -> ../../.ai/skills/laravel-clean-code
└── laravel-specialist     -> ../../.ai/skills/laravel-specialist
```

Ещё один симлинк: `.agents/skills -> ../.claude/skills` — совместимость с агентами, которые ищут навыки в `.agents/`.

Правила:

- **Копия вместо симлинка запрещена.** Два расходящихся источника правды — реальная поломка: субагент может продублировать навык, а `boost:update` молча вернул симлинк.
- Инвариант проверяется гейтом: `.claude/scripts/quality-gate.sh`, шаг «skills: симлинки, не копии» — для каждого `.ai/skills/*` требует существующий `.claude/skills/<name>` и именно симлинк. Гейт падает на копии или отсутствии.
- Переносить нужно **оба каталога**, сохраняя относительные target'ы. Копирование одного `.claude/skills` даёт четыре битых ссылок.
- Клиент без поддержки симлинков: материализовать целевые каталоги в его механизм навыков, **не меняя содержание**; при первой возможности вернуть симлинки.

## 3. `boost.json` — что Boost ставит и обновляет

```json
{
    "agents": ["claude_code", "codex"],
    "cloud": false,
    "guidelines": true,
    "mcp": true,
    "nightwatch": false,
    "packages": ["filament/filament"],
    "sail": true,
    "skills": [
        "laravel-best-practices",
        "configuring-horizon",
        "socialite-development",
        "tailwindcss-development",
        "laravel-clean-code",
        "laravel-specialist"
    ]
}
```

- `skills` — список из **семи** навыков, которыми управляет Boost; `packages` подтягивает guideline'ы установленного пакета (`filament/filament`), `guidelines: true` включает генерацию блока guidelines в `CLAUDE.md`, `mcp: true` — MCP-сервер, `sail: true` — запуск PHP-команд через Sail.
- `config/boost.php` → `guidelines.exclude: ['filament/filament']`: встроенный guideline пакета (237 строк примеров в каждой сессии) не вливается в `CLAUDE.md`; факты, предотвращающие ошибки, вынесены в `.ai/guidelines/filament.md`.
- **Расхождение:** `landing-page-design` есть в `.ai/skills` и симлинкован в `.claude/skills`, но в `boost.json → skills` его нет. Фактический набор шире управляемого списка Boost; гейт симлинков при этом проверяет именно все `.ai/skills`, то есть этот навык тоже обязан оставаться симлинком.
- Команды Boost (в контейнере/Sail): `boost:install`, `boost:update` (обновляет guidelines и skills, `--ignore-skills` — без навыков), `boost:add-skill` (`--list`, `--all`, `--skill=*`), `boost:list-skills`, `boost:mcp` (сам MCP-сервер), `boost:execute-tool`.

## 4. Обязательные навыки и матрица по ролям

- **`laravel-best-practices` — всегда.** Не опция: вызывается в начале любой правки controllers, models, migrations, services, validation, queues, Eloquent. Если существующий код нарушает правило навыка — это флагируется (и предлагается фикс), а не молча копируется.
- **`search-docs` — перед любым вызовом API.** Это не навык, а обязательный инструмент Boost: Laravel 13 / Livewire 4 / Filament 5 отличаются от старых версий, и писать вызов «по памяти», когда документация в одном вызове, нельзя. Навык `laravel-specialist` — углублённый справочник, когда документации мало.
- `laravel-clean-code` включается на реализацию/рефакторинг/review/debugging; его правила (минимальные правки, KISS, запрет `@php`) совпадают с жёсткими правилами проекта, поэтому он безопасен как постоянный фон.
- `landing-page-design` — предметный: на любую web-UI/marketing-работу.

Что требуют определения ролей (декларативно, из `.claude/agents/*.md`):

| Роль | Обязательные навыки | Дополнительно |
|---|---|---|
| `ui-builder` | `laravel-best-practices` | Boost `search-docs`; `landing-page-design` для публичных/marketing-страниц |
| `implementer` | `laravel-best-practices` | `search-docs`; `laravel-specialist` как углубление |
| `db-surgeon` | `laravel-best-practices` | `search-docs`; `laravel-specialist/references/eloquent.md`, `queues.md` |
| `test-writer` | `laravel-best-practices` | `search-docs`; `laravel-specialist/references/testing.md`, `livewire.md` |
| `deep-reasoner`, `plan-keeper`, `fast-worker` | не требуются | опираются на `CLAUDE.md` и свой reference |
| `compliance-checker` | не требуются | `money-paths.txt`, `composer audit`/`npm audit` |

Навык `configuring-horizon` — предметный: включается Horizon-задачей, к конкретной роли не привязан. `landing-page-design` — тоже предметный, вне ролевой матрицы.

## 5. Guidelines vs skills

- `.ai/guidelines/` — четыре исходных блока правил: `environment.md`, `filament.md`, `pillars.md`, `ui-rules.md`. Boost вливает их в `CLAUDE.md` внутри `<laravel-boost-guidelines>`; это не навыки, а всегда-загруженные правила (окружение, Filament, столпы, UI-запреты).
- Навыки загружаются **по триггеру** и могут лежать большим объёмом вне контекста; guidelines — короткие и всегда в контексте. Дублировать guidelines внутрь навыка не нужно.
- `quality-gate.sh` в прогоне без флагов содержит шаг сверки копий скиллов `.claude/` ↔ `.ai/`; фактически он реализован как проверка симлинков (см. § 2).

## 6. Внешние плагины Claude (не часть git)

Навыки и команды приходят не только из репозитория. Локальный срез `~/.claude/plugins/`:

| Плагин | Версия/коммит в срезе | Что даёт |
|---|---|---|
| Superpowers | 7.0.0 | brainstorming, writing/executing plans, TDD, systematic debugging, parallel agents, worktrees, review, verification-before-completion |
| Codex Companion | 1.0.5 | `/codex:review`, adversarial-review, rescue, transfer, result, setup, status, cancel |
| Caveman | `0d95a81d35a9` | caveman-режимы, `cavecrew`-агенты (investigator/builder/reviewer), `/commit`, `/review`, compress/stats |
| Ponytail | 4.8.4 | ponytail, audit, review, gain, debt, help |
| Warp | 2.0.0 | уведомления и интеграция терминала |
| Laravel Boost | `f8c5e7a1dcb7` | MCP-интеграция Boost |
| ELI5 | 1.0.0 | объяснение простыми словами |
| Scroll World | 0.3.0 | дополнительный UI-навык, включён проектной настройкой |
| Typesafe | 0.5.7 | локально включённый навык typesafe-ai |
| Intercom | 0.1.0 | установлен для проекта, выключен local override |

- Наличие плагина не означает обязательности для commit/push: механические проверки реализуют проектные shell-скрипты и `.githooks/`.
- Superpowers по умолчанию пишет планы в `docs/superpowers/` — здесь переопределено: дизайн это раздел внутри `planning/plans/PLAN-{N}-*.md`.
- Плагинные хуки (Superpowers SessionStart, Codex session-lifecycle/stop-review-gate, Warp on-*) живут вне репозитория и одним копированием `.claude/settings.json` не воспроизводятся.

## 7. Перенос на другого агента

- **Все навыки ставятся вместе с обвязкой.** Отдельно взятый `.claude/skills` — битый набор: четыре симлинка указывают в `.ai/skills`, которых нет. Комплект: `.ai/skills` + `.claude/skills` (с симлинками или материализованными копиями) + `boost.json` + `config/boost.php` + `.mcp.json`.
- **Клиентские механизмы различаются:** Claude Code читает `SKILL.md` из `.claude/skills/<name>/` и подгружает по `description`; Codex/DSH/generic не обязаны поддерживать этот каталог — нужен adapter: либо материализовать навыки в их штатное хранилище, либо включать нужный `SKILL.md` в prompt по триггеру.
- **`search-docs` требует Boost MCP.** `.mcp.json` запускает `vendor/bin/sail artisan boost:mcp`; без Sail/контейнера сервер не поднимется, и правило «сначала документация» деградирует до «прочитать официальные docs вручную». Плагин Laravel Boost несёт свой `.mcp.json` с `php artisan boost:mcp` без Sail — эффективный запуск надо проверять, а не предполагать, что глобальный PHP эквивалентен контейнеру.
- **Триггеры переносятся как текст.** `description` навыка — это то, по чему клиент решает «загрузить»; при адаптации нельзя переписывать его в общее «полезный навык».
- **Пользовательские навыки/плагины необязательны.** Девять проектных навыков самодостаточны; плагины из § 6 — расширение, устанавливаемое отдельно.

## 8. Расхождения и пробелы

- `boost.json` не перечисляет `landing-page-design`, хотя навык существует и симлинкован; управляемый и фактический наборы не совпадают.
- `laravel-specialist` в `SKILL.md` описывает «Laravel 10+, PHP 8.2+» — это generic-описание upstream-навыка, а проект живёт на Laravel 13 / PHP 8.5; версии из описания навыка не являются версиями проекта.
- `laravel-clean-code` в метаданных указывает `language: PHP 8.4` — устаревшая метка, фактическое требование проекта `php ^8.5.12`.
- Обязательность навыков заявлена текстом (`CLAUDE.md`, `.ai/guidelines/ui-rules.md`, роли), но hook'а «навык не вызван — блок» нет; фактически это дисциплина агента, а `quality-gate` ловит только последствия (тесты, Pint, Larastan, симлинки).
- Плагинные навыки из § 6 в этот список не входят и в git не переносятся — при переносе их наличие нужно проверять отдельно.

## Источники

- `.ai/skills/*/SKILL.md` — шесть навыков; `rules/`, `references/`, `sections/` внутри них
- `.claude/skills/` — три локальных навыка и шесть симлинков; `.agents/skills`
- `boost.json`; `config/boost.php`
- `.claude/agents/ui-builder.md`, `implementer.md`, `db-surgeon.md`, `test-writer.md` (обязательные навыки по ролям)
- `.ai/guidelines/ui-rules.md` (обязательные навыки), `environment.md`
- `.claude/scripts/quality-gate.sh` (проверка симлинков)
- `CLAUDE.md` § Superpowers-скиллы, § Orchestration workflow
- `outputs/AGENT_HARNESS.md` — § «Навыки, агенты, MCP и внешняя память» (строки 371–527)