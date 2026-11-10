# ⚡ НАЧНИ ОТСЮДА

Перед работой в новом чате (и после `git pull` на другой машине) прочитай **`planning/ACTIVE_PLANS.md`** — срез «на сейчас» (таблица активных планов; детали — `registry.sh show <id>` и `## Резюме` плана).
Подъём окружения — `.claude/reference/environment.md`. `planning/README.md` нужен, только когда меняешь сами правила планирования. Task-лист
ассистента живёт в сессии и не переживает `git pull` — источник правды об этапе именно `planning/`.

## Планирование — три реестра

| Реестр | Индекс (корень `planning/`) | Тело |
|---|---|---|
| RM — идея | `ROADMAP.md` | `roadmap/RM-N-*.md` |
| PLAN — план | `ACTIVE_PLANS.md` (в работе), `PLANS.md` (закрытые) | `plans/PLAN-N-*.md`; запись о закрытии — `plans/closed/PLAN-N.md` |
| HF — хотфикс | `HOTFIXES.md` | `hotfixes/HF-N-*.md` |

- **Индексы правит только `.claude/scripts/registry.sh`**: `next-id`, `add <RM|HF|PLAN> …`, `set-status <id> <статус>`, `show <id>`, `check`.
  Edit/Write на индексы блокирует `registry-guard.sh`. Читай индекс и `## Резюме` плана, не тела (`big-read-guard.sh` режет Read > 40 КБ / 300 строк).
- **Куда что.** Есть что проектировать (несколько связанных задач) — план в `planning/plans/PLAN-{N}-kebab.md` (N ≥ 145: `## Резюме` ≤ 15 строк,
  размер 40 КБ предупреждение / 80 КБ блок) + строка через `registry.sh add PLAN`. Правка, для которой план избыточен (багфикс, вёрстка, конфиг,
  зависимость) — хотфикс: ветка `hotfix/*`, файл `hotfixes/HF-N-*.md` и строка `HOTFIXES.md` через `registry.sh add HF`, условие мержа (`merge-gate`).
  Идея «потом» — `RM-N`, **только по прямому слову владельца** («добавь в роадмап»); сам ничего в roadmap не переносишь.
- **Слово владельца.** Закрыть план, добавить идею RM, править хуки/настройки/`CLAUDE.md` (защищённые пути) можно только с маркером
  `owner-ok`, который выдаёт **владелец в своём терминале**: `.claude/scripts/owner-ok.sh close-plan|rm-add|hooks-edit …`. Агент скрипт не
  запускает и в `.claude/state/owner-ok` не пишет (`owner-ok-guard.sh`). Закрытие плана — `registry.sh set-status PLAN-N закрыт` после явного «план закрыт».
- **Закрытые записи не переписываем** (`plans/closed/*` и тела закрытых хотфиксов — побайтно; если в проекте есть `.claude/scripts/verify-*-migration.sh`, pre-push их запускает). Правь план по коду, а не наоборот.
- **Сверка.** `.claude/hooks/plans-drift.sh` (SessionStart) печатает расхождения реестров с git и бюджет стартового набора — разбери до новой работы.
  Перед закрытием плана `.claude/scripts/plan-code-refs.sh planning/plans/PLAN-N-*.md` должен быть пуст.
- **Superpowers-скиллы** по умолчанию пишут в `docs/superpowers/` — здесь НЕ так: дизайн это раздел внутри `planning/plans/PLAN-{N}-*.md`.
- Полные правила, схема, статусы, самоповторное ревью плана и таблица E1–E19 → `.claude/reference/planning-registries.md` (читать по надобности).

## Git workflow

- Только `main` как база. Работа — ветки `feature/PLAN-N-slug` или `hotfix/*` от `main`; **никаких прямых коммитов в `main`**, `develop` не заводим.
  Код (любой путь вне `planning/**`, классы — `.claude/hooks/paths.conf`) правится только на этих ветках (E2).
- **Коммиты на английском**, conventional commits (`feat/fix/docs/…`). Сообщение каждого коммита с кодом называет `PLAN-N` своей ветки
  (на `hotfix/*` — `HF-N`); по этому токену `plans-drift` находит чужую работу. Токен `RM-N` права на код не даёт.
- **Мерж в `main` и публикация `main` — только по слову владельца в чате; прямые правки `main` запрещены.** `main-push-guard.sh` пропускает
  пуш `main` лишь когда впереди `<remote>/main` на основной линии нет прямых коммитов (только мерж-коммиты веток); `+main`, force, `--delete`,
  `--all`/`--mirror`, refspec не из `main` и неразрешимый remote блокируются (общее для Claude и Codex, `.codex/hooks.json`). `merge-gate.sh`
  блокирует `git merge` без полного гейта, ревью, слов владельца и чистых реестров.
- **Перед вопросом владельцу о мерже агент запускает `.claude/scripts/merge-ready.sh <ветка>`; спрашивает слово только при READY (кроме слов
  владельца) — гейты, ревью и проверки после его ответа не гонять.**
- **Ревью кода: ≤2 прохода** — полный и один дельта-проход по строкам, изменённым после находок. Чинятся только БЛОКЕРы; ВАЖНО/МЕЛОЧЬ — сам, без нового прохода. Ревьюеру отдают список закрытого и задачу подтвердить, новых направлений не искать. Деньги — один аудит opus и один Codex параллельно + одна проверка правок. Подробнее — `.claude/reference/planning-registries.md`.
- **`--no-verify` и `-n` агенту запрещены** (`commit-gate.sh`); `core.hooksPath` — `.githooks/` (`install-githooks.sh`).
- **Перед каждым тестом и коммитом — Larastan** (`vendor/bin/sail php vendor/bin/phpstan analyse`); не коммитить, если он падает на изменённых
  файлах. `.claude/scripts/quality-gate.sh` (`--fast` для коммита, `--merge` перед мержем) исполняет это правило и запускается хуком перед `git commit`.
- Перед мержем гонять ВСЁ (полный PHPUnit, Dusk, Larastan, Pint, eslint), не отфильтрованное подмножество.

---

<laravel-boost-guidelines>
=== .ai/environment rules ===

## Окружение проекта — поправки к общим инструкциям

Общие Laravel-инструкции про Sail в этом проекте действуют не везде. Ниже — расхождения,
они важнее общего правила.

- **`npm run build` / `npm run dev` запускаются на ХОСТЕ (macOS), НЕ через sail.**
  `vendor/bin/sail npm install` перезаписывает `node_modules` линуксовыми rolldown-биндингами
  и ломает хостовую сборку. Чинить: на хосте `rm -rf node_modules package-lock.json && npm install`.
  Правки Blade видны только после сборки на хосте.
- **Тесты и Pint — через контейнер horizon**, если sail-сервис `laravel.test` не может занять
  порт 80 (его держит другой локальный проект):
  `docker exec <project>-horizon-1 php artisan test --compact`,
  `docker exec <project>-horizon-1 vendor/bin/pint --dirty --format agent`.
- **После правок джобов / очередей — `docker restart <project>-horizon-1`**,
  иначе воркеры крутят старый код из памяти (кешированные синглтоны). `horizon:status` умеет
  врать «running» по stale-флагу; живые воркеры проверять через
  `docker exec <project>-horizon-1 ps aux | grep horizon:work`.
- **После `git pull` на другой машине — `vendor/bin/sail composer refresh`.** Оборачивает
  `optimize:clear`, `dump-autoload`, `migrate --force`, `queue:restart`. Без этого вылезают
  ошибки «Target [...] is not instantiable» из закешированных DI-биндингов, а воркеры продолжают
  крутить старый код.

## Справочники команд и паттернов

Чтобы не держать примеры в контексте каждой сессии, они вынесены в файлы. Открывать по надобности:

- `.claude/reference/sail-artisan-commands.md` — Sail, Artisan, Composer, npm, Larastan, Pint, тесты.
- `.claude/reference/security-audit-prompt.md` — многоразовый промпт запуска аудита безопасности.
- `.claude/reference/filament-patterns.md` — Filament v5: формы (Get/Set, Section/Grid, Repeater),
  таблицы, экшены, тесты панели.

## Quality Gate

`.claude/scripts/quality-gate.sh` — исполняемая версия правила «Larastan + Pint перед коммитом»:

- без флагов — Larastan → Pint → PHPUnit → eslint → сверка копий скиллов `.claude/` ↔ `.ai/`;
- `--fast` — без полного прогона тестов (≈3 секунды, столько же гоняет хук перед коммитом);
- `--merge` — добавляет Dusk, полный чеклист перед мержем ветки в `main`.

Гейт запускается автоматически перед `git commit` (хук `.claude/hooks/commit-gate.sh`, он же
проверяет ветку и сканирует staged-дифф на секреты). Результат работы субагента тоже
принимается только после прогона гейта.

=== .ai/filament rules ===

## Filament v5 — то, что ломается чаще всего

Полная официальная секция Filament выключена в `config/boost.php` → `guidelines.exclude`:
237 строк примеров в контексте каждой сессии при том, что Filament — админка на 47 файлов из 611.
Здесь остаётся только то, что предотвращает конкретные ошибки. Примеры и рецепты:
`search-docs` (пакет `filament/filament`) и `.claude/reference/filament-patterns.md`
(формы Get/Set, Section/Grid, Repeater, таблицы, экшены, тесты панели).

Всегда инициализировать компоненты статическим `make()`. Большинство конфигурационных методов
принимают `Closure` для динамических значений.

### Correct Namespaces

- Form fields (`TextInput`, `Select`, `Repeater`, etc.): `Filament\Forms\Components\`
- Infolist entries (`TextEntry`, `IconEntry`, etc.): `Filament\Infolists\Components\`
- Layout components (`Grid`, `Section`, `Fieldset`, `Tabs`, `Wizard`, etc.): `Filament\Schemas\Components\`
- Schema utilities (`Get`, `Set`, etc.): `Filament\Schemas\Components\Utilities\`
- Table columns (`TextColumn`, `IconColumn`, etc.): `Filament\Tables\Columns\`
- Table filters (`SelectFilter`, `Filter`, etc.): `Filament\Tables\Filters\`
- Actions (`DeleteAction`, `CreateAction`, etc.): `Filament\Actions\`. Never use `Filament\Tables\Actions\`, `Filament\Forms\Actions\`, or any other sub-namespace for actions.
- Icons: `Filament\Support\Icons\Heroicon` enum (e.g., `Heroicon::PencilSquare`)

### Common Mistakes

- **Never assume public file visibility.** File visibility is `private` by default. Always use `->visibility('public')` when public access is needed.
- **Never assume full-width layout.** `Grid`, `Section`, `Fieldset`, and `Repeater` do not span all columns by default.
- **Use `Select::make('author_id')->relationship('author', 'name')` for BelongsTo fields.** `BelongsToSelect` does not exist.
- **`Repeater` uses `->schema()`, not `->fields()`.**
- **Never add `->dehydrated(false)` to fields that need to be saved.** It strips the value from form state before `->action()` or the save handler runs. Only use it for helper/UI-only fields.
- **Use correct property types when overriding `Page`, `Resource`, and `Widget` properties.** These properties have union types or changed modifiers that must be preserved:
  - `$navigationIcon`: `protected static string | BackedEnum | null` (not `?string`)
  - `$navigationGroup`: `protected static string | UnitEnum | null` (not `?string`)
  - `$view`: `protected string` (not `protected static string`) on `Page` and `Widget` classes

### Artisan

Создавать файлы только Filament-специфичными командами, всегда с `--no-interaction`.
Перед запуском смотреть требуемые опции через `--help`.

=== .ai/pillars rules ===

## Полное покрытие множеств («для каждого X» — значит для КАЖДОГО)

Если задача подразумевает покрытие множества (для каждого типа проблемы, каждой
кнопки, каждого роута), нельзя молча покрыть «основные» и оставить остальное
на fallback. Перед сдачей: (1) перечислить полное множество программно
(enum cases / glob / `route:list`) и сверить покрытие 1:1; (2) закрепить
полноту тестом-перебором, который падает на пропуске (пример:
`test_every_issue_type_has_instruction_file` в TaskSolutionTest);
(3) если подмножество — осознанное решение, сказать об этом явно и сразу,
не дожидаясь вопроса.

## Resource Economy — Столп

**Любая работа делается с минимумом нагрузки на систему и БД.** Это правило сильнее «удобно» и «понятно». Если выбор — между «работает плавно но N×SELECT на запрос» и «работает за 1 batched-запрос», берём второе. По умолчанию проверяем:

- **Batched > per-row.** N INSERT/SELECT/UPDATE на цикл — антипаттерн. Считаем агрегатом / UPSERT'ом / `whereIn(...)`. Один round-trip предпочтительнее десяти.
- **Reuse > re-fetch.** Если данные уже в Page row / ParsedPage / cached payload — используем их, не парсим HTML и не лезем в БД повторно.
- **Throttle того что меняется.** Heartbeat / score / scan_logs — не на каждое событие, а раз в N секунд или N единиц работы. Logging не должен генерить 2000 строк за скан.
- **Cache того что не меняется** — config, enum-derived mappings, immutable lookups. `DashboardCache` уже есть, бамп `VERSION` при изменении формата.
- **Indexes для query-hot путей.** Если делаем новый `WHERE` — проверить что индекс есть; добавить миграцией если нет.
- **Без broadcasting / WebSocket / Redis pub-sub** пока polling работает. `wire:poll` достаточно для UI-обновлений 1×/5 сек.
- **Score / тяжёлые расчёты — только когда нужно.** Не пересчитываем после каждого Issue / Page; делаем один раз в конце фазы или throttle до 1/30 сек.
- **Если делаем «live» что-то** — спросить «можно ли посчитать SQL-агрегатом, а не сервисом который дёргает API/DB N раз?». Чаще всего да.

При проектировании нового кода каждое решение проверяем этим столпом. Если нарушаем — явно обосновываем почему (например, корректность важнее экономии в конкретном случае).

## Query Building — приоритет

**Запрос строим по лестнице, останавливаемся на первой ступени, которая закрывает задачу:**

1. **Eloquent** (`Model::where(...)`, relationships, scopes) — дефолт для доменной логики: чтение/запись по одной сущности, бизнес-инварианты, всё что не set-based.
2. **Query Builder** (`DB::table(...)`) — когда нужен голый SQL-запрос без модели/событий, но синтаксис укладывается в API билдера (join, whereIn, aggregate-функции без window).
3. **Raw SQL** (`DB::statement` / `selectRaw` / `whereRaw`) — только если 1 и 2 физически не выражают нужное: window functions (`OVER PARTITION BY`), `WITH ... UPDATE ... FROM` (CTE-апдейт), рекурсивные CTE, БД-специфичные функции (`split_part`, `strpos` и т.п.). Это не откат к «плохому» варианту — set-based операции обязаны идти через SQL, а не через Eloquent `->get()` + цикл в PHP (нарушение Resource Economy: batched > per-row).

Если поднимаемся на ступень 3 — коротким комментарием у запроса объясняем, чего именно не умеет Eloquent/Builder (пример: «window function + CTE-update, нет в Query Builder API»). Без обоснования raw SQL — повод для ревью-замечания.

=== .ai/ui-rules rules ===

## Обязательные скиллы проекта

- **Always apply the `laravel-best-practices` skill on any Laravel work.** This is not optional — invoke it at the start of any change to controllers, models, migrations, services, validation, queues, or Eloquent. The skill ships 31 rules across 7 categories (architecture, Eloquent, controllers/routing, validation, security, performance, API design); use them as the default reference. If existing code violates a rule, flag it (and offer a fix) rather than silently following the bad pattern.
- **Always use the `search-docs` tool before writing an API call.** Laravel 13, Livewire 4 and Filament 5 differ from older versions in ways that are easy to get wrong from memory. Никогда не писать вызов API по памяти, когда документация в одном тул-колле.

## No native browser dialogs anywhere in user-facing UI

Do NOT use `wire:confirm`, `window.confirm()`, `alert()`, or `prompt()` — they are not styleable, look broken on mobile, and break the app's visual identity. Use the global popup primitives from `resources/views/layouts/app.blade.php`:

- **Confirm dialog**: `<x-confirm-modal>` listens for the `open-confirm` Alpine event. Trigger from any button with `x-on:click="$dispatch('open-confirm', { message: '...', confirmLabel: '...', tone: 'danger'|'warning'|'primary', onConfirm: () => $wire.method(args) })"`.
- **Toast notification**: `<x-toast>` listens for the Livewire `toast` event. From PHP: `$this->dispatch('toast', message: '...', type: 'success'|'error'|'warning'|'info')`. Session flash (`session()->flash('status', ...)`) is also auto-converted to a toast after redirects.
- When adding a new destructive action, default the tone to `danger`; for archival/reversible actions use `warning`; for affirmative confirmations use `primary` (the default).

## NO PHP logic in Blade templates

`@php ... @endphp` blocks are forbidden. Blade is presentation only — variable echoing, directives (`@if`, `@foreach`, `@auth`), and component composition. Anything more belongs elsewhere:

- **Data assembly** (computed properties, derived collections, aggregates): build it in the Livewire component's `render()` or a controller, pass to the view ready-to-use. Не собирать значения в блоке `@php` в начале вьюхи.
- **Display formatting** (currency, dates, severity → CSS class): put in a model accessor, a value-object method, or a dedicated Blade component (`<x-severity-badge :level="..." />`) with backing logic in its class.
- **Conditional CSS classes**: extract to a method on the model or to an Alpine `:class` if it depends on client state. Не вычислять класс тернарником в `@php`.
- **Iteration logic** (sorting, filtering, grouping): pre-process in the component before passing to the view. The view consumes a ready collection.
- **Constants and config**: pass them in from the component, not inlined as a `use`-импорт внутри `@php`.
- **Forms** (any GET/POST that touches the DB): use a FormRequest class with `rules()` / `authorize()` / `messages()`. No inline validation in controllers, no `$request->all()`.
- **Existing `@php` blocks** are technical debt — when you touch a file that contains one, move the logic to the proper layer as part of the same change. Don't add new ones.

=== laravel-boost: общие разделы ===

Foundation / boost / php / sail / tests / laravel-core / pint / phpunit вынесены дословно в `.claude/reference/laravel-boost-guidelines.md`.
Главное из них:

- Все команды — через Sail: `vendor/bin/sail artisan|composer|npm|php …` (исключения для npm и тестов хоста — «Окружение проекта» выше).
- Перед правкой кода — `search-docs` (Boost) по версии пакета; Laravel 13, Livewire 4, Filament 5 отличаются от привычного.
- Файлы создавать `artisan make:*` с `--no-interaction`; PHP: фигурные скобки всегда, типы параметров и возврата, constructor promotion.
- Тесты — PHPUnit (Pest конвертировать), фабрики моделей; запускать узко: `vendor/bin/sail artisan test --compact --filter=…`.
- После PHP-правок — `vendor/bin/sail bin pint --dirty --format agent`. Документацию без запроса не создавать.

</laravel-boost-guidelines>

## Codex: роли, правила, обвязка

Этот файл Codex читает как `AGENTS.md` (симлинк). Всё ниже про Claude действует и для Codex с такими поправками:

- Оркестратор — основной агент Codex. Имена моделей `fable`/`opus`/`sonnet`/`haiku` в таблице ниже — не модели Codex: роль наследует модель родителя.
- Роли из таблицы — те же имена в `.codex/agents/*.toml`; каждая читает свою инструкцию `.claude/agents/<имя>.md` (один источник). Если клиент роль не нашёл — передай субагенту путь к инструкции явно.
- Правила `.claude/rules/*.md` Codex получает хуком SessionStart (`claude-compat.py rules`), хуки — через `.codex/hooks.json` → `.codex/hooks/claude-compat.py` → `.claude/hooks/`, скиллы — `.agents/skills` → `.claude/skills`. Роль, хук или скилл без пары у Codex валит `test_claude_compat`.
- Где нужна отметка ревью opus, вторая отметка Codex её не заменяет. Новые и изменённые хуки Codex включает после доверия владельца через `/hooks`.
- Codex работает в основном чекауте (или `.claude/worktrees/*`): гейт исполняется в контейнере sail, внешний worktree туда не смонтирован.

## Orchestration workflow

You (Opus, set via `.claude/settings.json` → `"model"`) are the orchestrator. Plan, decompose, synthesize. Show the plan before executing. Write code yourself only for trivial one-liners; everything else is delegated. Keep your own context lean — subagents return conclusions, not transcripts.

Delegation map (agent definitions in `.claude/agents/`; first matching row wins):

| Task | Agent | Model |
|---|---|---|
| Architecture, complex debugging, algorithms, plan review | `deep-reasoner` | fable; if unavailable, respawn with model override `opus` |
| **UI**: Livewire page, Blade view, component, table, drawer, chart | `ui-builder` | sonnet |
| **DB**: migrations, indexes, slow/N+1/per-row queries | `db-surgeon` | sonnet |
| **Tests**: PHPUnit, Dusk, enumeration tests for «for every X» | `test-writer` | sonnet |
| **planning/**: drift findings, registry rows (`registry.sh`), HF entries, closing a plan | `plan-keeper` | sonnet |
| **Audit before shipping**: 152-ФЗ exposure, `composer`/`npm audit`, secrets in diff | `compliance-checker` | sonnet |
| Implementing a decided feature/fix that fits none of the above | `implementer` | sonnet |
| Mechanical work with an exact spec: renames, boilerplate, formatting, running commands | `fast-worker` | haiku; spawn with model override `sonnet` when the spec is fuzzy or needs judgment |
| Locate code («where is X», «who calls Y», map a directory) | `cavecrew-investigator` / `Explore` | — |
| Diff/branch review | Codex (read-only), else `cavecrew-reviewer` or `/code-review`; who reviews what — `.claude/rules/working-rules.md` | — |
| Fresh perspective, second opinion, stuck | Codex (`/codex:rescue --background`) | GPT — peer of deep-reasoner |

Domain agents exist to keep large documents out of the orchestrator's context: `ui-builder` loads
the project UI skill in its own window, `plan-keeper` works through `registry.sh` and plan summaries
in its own. Delegate the whole slice, not a fragment of it — a subagent that hands back a question
means the spec was thin, and a subagent spawned for a two-line edit costs more than it saves.

Below this table sits a cheaper rung for work too small to justify even a `fast-worker` spawn: see
`.claude/reference/local-workers.md` (read it when the `local-workers` MCP server is available; if it is not, this rung does not exist). Route there first when a task fits its bounded-step shape;
promote to the table above only when it needs judgment, broader context, or repo-wide reach.

Rules of engagement:

- Parallelize independent subtasks in one message; sequence only real dependencies.
- Every delegation carries: goal, exact file paths, acceptance criteria, what NOT to touch.
- A subagent returning a question means the spec was underspecified — fix the spec, don't blindly upgrade the model.
- **Verify before accepting.** A subagent's report is a claim, not a result. Run `.claude/scripts/quality-gate.sh` (Larastan → Pint → PHPUnit → eslint) before calling delegated work done; re-delegate on failure with the gate output as the spec. Same gate runs automatically before `git commit`.
- High-stakes decisions: task deep-reasoner + Codex on the same problem in parallel, synthesize the best of both without showing either the other's answer.

