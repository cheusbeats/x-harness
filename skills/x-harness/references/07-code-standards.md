# 07 — Стандарты кода, UI, тесты и безопасность

> **Что это.** Переносимая выжимка инженерных правил: Resource Economy, лестница запросов, Filament v5, UI/Blade, PHP/Laravel, тесты и безопасность.
> **Когда читать.** Перед любой правкой PHP/Blade/Livewire/Filament, перед тестом, коммитом, ревью и мержем; при вопросе «как здесь принято».
> **Статус.** Источник истины — файлы из §11. Если текст расходится с исполняемым скриптом или кодом, прав код; расхождение фиксируется, а не замалчивается.

## 0. Два маркера: «требуется» и «фактически»

- **требуется** — правило объявлено в инструкциях проекта и обязательно для агента.
- **фактически** — что реально исполняет hook, script, linter или тест.

Правило без механической проверки остаётся правилом, но держится на ревью. Нельзя выдавать декларацию за enforcement: если ниже сказано «механической проверки нет», нарушение поймает человек/ревьюер, а не гейт.

## 1. Resource Economy — столп

**Любая работа делается с минимумом нагрузки на систему и БД.** Это правило сильнее «удобно» и «понятно»: между «плавно, но N×SELECT» и «один batched-запрос» выбираем второе. Проверяем по умолчанию:

- **Batched > per-row.** N INSERT/SELECT/UPDATE в цикле — антипаттерн. Считаем агрегатом, UPSERT'ом, `whereIn(...)`. Один round-trip предпочтительнее десяти.
- **Reuse > re-fetch.** Данные уже в Page row / ParsedPage / cached payload — используем их, не парсим HTML и не лезем в БД повторно.
- **Throttle того, что меняется.** Heartbeat / score / scan_logs — не на каждое событие, а раз в N секунд или N единиц работы. Логирование не должно генерировать 2000 строк за скан.
- **Cache того, что не меняется** — config, enum-derived mappings, immutable lookups. `DashboardCache` уже есть; при изменении формата бампаем `VERSION`.
- **Indexes для query-hot путей.** Новый `WHERE` — проверить, что индекс есть; если нет, добавить миграцией.
- **Без broadcasting / WebSocket / Redis pub-sub**, пока работает polling. `wire:poll` достаточно для UI-обновлений 1×/5 сек.
- **Score / тяжёлые расчёты — только когда нужно.** Не пересчитываем после каждого Issue/Page: один раз в конце фазы или throttle до 1/30 сек.
- **«Live»-функция** — сначала спросить: «можно ли посчитать SQL-агрегатом, а не сервисом, который дёргает API/DB N раз?» Чаще всего да.

При проектировании нового кода каждое решение проверяется этим столпом. Нарушаем — явно обосновываем почему (например, корректность важнее экономии в конкретном случае). Источник: `.ai/guidelines/pillars.md`.

**Фактически:** отдельного хука/линтера на Resource Economy нет — это проектное решение, которое проверяется ревью и тестами. `db-surgeon` привлекается для миграций, индексов и запросов, которые медленные, N+1 или per-row.

## 2. Query Building — лестница

Запрос строим по лестнице и **останавливаемся на первой ступени, которая закрывает задачу**:

| Ступень | Чем | Когда | Пример |
|---|---|---|---|
| 1 | **Eloquent** — `Model::where(...)`, relationships, scopes | дефолт для доменной логики: чтение/запись по одной сущности, бизнес-инварианты, всё не set-based | `Project::where('account_id', $id)->with('pages')` |
| 2 | **Query Builder** — `DB::table(...)` | нужен голый SQL без модели/событий, но синтаксис укладывается в API билдера (join, whereIn, aggregate без window) | `DB::table('pages')->whereIn('project_id', $ids)->count()` |
| 3 | **Raw SQL** — `DB::statement`, `selectRaw`, `whereRaw` | только если 1 и 2 физически не выражают нужное: window functions (`OVER PARTITION BY`), `WITH ... UPDATE ... FROM` (CTE-апдейт), рекурсивные CTE, БД-специфичные функции (`split_part`, `strpos` и т.п.) | `UPDATE ... FROM (WITH ...)` |

Правила:

- Raw SQL — **не откат к «плохому» варианту**: set-based операции обязаны идти через SQL, а не через Eloquent `->get()` + цикл в PHP (это нарушение Resource Economy: batched > per-row).
- Поднялись на ступень 3 — **коротким комментарием у запроса** объясняем, чего именно не умеет Eloquent/Builder (пример: «window function + CTE-update, нет в Query Builder API»).
- Raw SQL без обоснования — повод для ревью-замечания.

**Фактически:** механической проверки комментария/ступени нет; ловится ревью. Источник: `.ai/guidelines/pillars.md`.

## 3. Полное покрытие множеств

Если задача подразумевает покрытие множества («для каждого типа проблемы», «для каждой кнопки», «для каждого роута»), нельзя молча покрыть «основные» и оставить остальное на fallback.

Перед сдачей:

1. **Перечислить полное множество программно** — `enum cases`, `glob`, `route:list` — и сверить покрытие 1:1.
2. **Закрепить полноту тестом-перебором**, который падает на пропуске. Пример: `test_every_issue_type_has_instruction_file` в `TaskSolutionTest`.
3. Если подмножество — осознанное решение, **сказать об этом явно и сразу**, не дожидаясь вопроса.

**Фактически:** единственный механизм — тест-перебора; универсального хука на «полноту» нет. Источник: `.ai/guidelines/pillars.md`.

## 4. Filament v5

### 4.1 Контекст и обязательная документация

Полная официальная секция Filament выключена в `config/boost.php` → `guidelines.exclude` (там `filament/filament`): иначе примеры раздувают контекст каждой сессии. Вместо неё — этот раздел, `search-docs` (пакет `filament/filament`) и `.claude/reference/filament-patterns.md`.

Всегда инициализировать компоненты статическим `make()`. Большинство конфигурационных методов принимают `Closure` для динамических значений.

### 4.2 Пространства имён

| Что | Namespace |
|---|---|
| Form fields (`TextInput`, `Select`, `Repeater`) | `Filament\Forms\Components\` |
| Infolist entries (`TextEntry`, `IconEntry`) | `Filament\Infolists\Components\` |
| Layout (`Grid`, `Section`, `Fieldset`, `Tabs`, `Wizard`) | `Filament\Schemas\Components\` |
| Schema utilities (`Get`, `Set`) | `Filament\Schemas\Components\Utilities\` |
| Table columns (`TextColumn`, `IconColumn`) | `Filament\Tables\Columns\` |
| Table filters (`SelectFilter`, `Filter`) | `Filament\Tables\Filters\` |
| Actions (`DeleteAction`, `CreateAction`) | `Filament\Actions\` |
| Icons | `Filament\Support\Icons\Heroicon` enum (например, `Heroicon::PencilSquare`) |

**Actions — только `Filament\Actions\`.** Никогда `Filament\Tables\Actions\`, `Filament\Forms\Actions\` или другой под-namespace.

### 4.3 Частые ошибки

- **Не предполагать public-видимость файлов.** По умолчанию visibility = `private`; нужен публичный доступ — `->visibility('public')`.
- **Не предполагать full-width.** `Grid`, `Section`, `Fieldset`, `Repeater` по умолчанию не занимают все колонки; нужен `->columnSpanFull()`.
- **BelongsTo:** `Select::make('author_id')->relationship('author', 'name')`. `BelongsToSelect` не существует.
- **`Repeater` использует `->schema()`, не `->fields()`.**
- **`->dehydrated(false)`** — только для helper/UI-only полей. На сохраняемых полях он вырезает значение из form state до `->action()`/save.
- **Типы свойств при переопределении `Page`, `Resource`, `Widget`** сохранять: `$navigationIcon`: `protected static string | BackedEnum | null`; `$navigationGroup`: `protected static string | UnitEnum | null`; `$view`: `protected string` (не `static` у `Page`/`Widget`).

### 4.4 Паттерны из filament-patterns.md

| Паттерн | Суть |
|---|---|
| `Get` | читать значение другого поля: `visible(fn (Get $get): bool => ...)` |
| `Set` | менять другое поле при live-изменении; на текстовых входах `->live(onBlur: true)`, чтобы не на каждое нажатие |
| `Section` + `Grid` | компоновка; детям задавать `->columnSpan()`/`->columnSpanFull()` |
| `Repeater` | HasMany inline: `->relationship()` (без аргументов — по имени поля), `->schema([...])`, `->columns(2)` |
| Колонка | вычисление через `->state(fn (User $record): string => ...)` |
| Фильтр | `SelectFilter::make('status')->options(Enum::class)`; `SelectFilter::make('author')->relationship('author', 'name')`; кастом — `Filter::make('x')->query(fn (Builder $q) => ...)` |
| Action | `Action::make('updateEmail')->schema([...])->action(fn (array $data, User $record) => $record->update($data))` |

    use Filament\Forms\Components\Select;
    use Filament\Forms\Components\TextInput;
    use Filament\Schemas\Components\Utilities\Get;
    use Filament\Schemas\Components\Utilities\Set;

    Select::make('type')->options(CompanyType::class)->required()->live(),

    TextInput::make('company_name')->required()
        ->visible(fn (Get $get): bool => $get('type') === 'business'),

    TextInput::make('title')->required()->live(onBlur: true)
        ->afterStateUpdated(fn (Set $set, ?string $state) => $set('slug', Str::slug($state ?? ''))),

### 4.5 Artisan

- Файлы создавать **только Filament-специфичными командами** (`artisan make:filament-*`), всегда с `--no-interaction`.
- Перед запуском смотреть требуемые опции: `vendor/bin/sail artisan <команда> --help`.
- `artisan list` — список доступных команд.

### 4.6 Тесты панели

**Расхождение, важное при переносе.** `.claude/reference/filament-patterns.md` написан на Pest (`livewire()`, `use function Pest\...`) и заявляет требование `pestphp/pest-plugin-livewire`. В проекте Pest не установлен: в `composer.json` есть только `allow-plugins.pestphp/pest-plugin`, пакета `pestphp/*` в `composer.lock`/vendor нет; обязателен PHPUnit 12. Поэтому примеры из reference переводим на PHPUnit:

- `Livewire::test(Component::class, ['record' => $id])` вместо `livewire(...)`;
- `Livewire::actingAs($user)->test(Page::class)`;
- `callAction(TestAction::make(EditAction::class)->table('key'), [...])` для действий таблицы;
- `assertHasNoFormErrors()`, `assertNotified()`, `assertCanSeeTableRecords(...)`.

Рабочий образец PHPUnit-теста панели: `tests/Feature/SitePages/SiteSettingsTest.php`. Перед тестом — `$this->actingAs(...)` (или `Livewire::actingAs`). Для edit-страниц: `['record' => $user->id]`, `->call('save')` (не `create`) и без `assertRedirect()` — edit-страницы не редиректят.

## 5. UI-правила

### 5.1 Обязательные навыки

- **`laravel-best-practices`** — всегда при любой Laravel-работе (controllers, models, migrations, services, validation, queues, Eloquent). 31 правило в 7 категориях; нарушение в существующем коде — flag + предложить фикс, а не копировать плохой паттерн.
- **`search-docs` перед написанием API-вызова** — Laravel 13, Livewire 4, Filament 5 отличаются от старых версий; не писать API по памяти, когда документация в тул-колле. Без Boost MCP — официальная документация нужной версии.

### 5.2 Никаких нативных браузерных диалогов

Запрещены `wire:confirm`, `window.confirm()`, `alert()`, `prompt()` — они не стилизуются, ломаются на мобильных и разрушают визуальную идентичность. Вместо них — глобальные примитивы из `resources/views/layouts/app.blade.php`:

- **Confirm:** `<x-confirm-modal>` слушает Alpine-событие `open-confirm`. Триггер с кнопки: `x-on:click="$dispatch('open-confirm', { message: '...', confirmLabel: '...', tone: 'danger'|'warning'|'primary', onConfirm: () => $wire.method(args) })"`.
- **Toast:** `<x-toast>` слушает Livewire-событие `toast`. Из PHP: `$this->dispatch('toast', message: '...', type: 'success'|'error'|'warning'|'info')`. `session()->flash('status', ...)` автоматически превращается в toast после редиректа.
- **Тон:** destructive — `danger`; архивное/обратимое — `warning`; подтверждение — `primary` (по умолчанию).

### 5.3 Никакой PHP-логики в Blade

`@php ... @endphp` запрещены. Blade — только presentation: вывод переменных, директивы (`@if`, `@foreach`, `@auth`), композиция компонентов. Всё остальное — в слой:

- **Сборка данных** (computed properties, derived collections, агрегаты) — в Livewire `render()`/controller, во view приходит готовое. Не собирать значения в `@php` в начале вьюхи.
- **Форматирование** (валюта, даты, severity → CSS-класс) — model accessor, value-object method или Blade-компонент (`<x-severity-badge :level="..." />`) с логикой в классе.
- **Условные CSS-классы** — метод модели или Alpine `:class`, если зависит от клиентского состояния. Не тернарник в `@php`.
- **Итерационная логика** (сортировка, фильтрация, группировка) — предобработка в компоненте; view потребляет готовую коллекцию.
- **Константы и конфиг** — передать из компонента, не инлайнить `use`-импорт в `@php`.
- **Формы**, любые GET/POST с БД — `FormRequest` с `rules()` / `authorize()` / `messages()`. Никакой inline-валидации в контроллерах, никакого `$request->all()`.
- **Существующие `@php`** — техдолг: трогаешь файл — выноси логику в правильный слой в той же правке. Новые не добавлять.

### 5.4 Enforcement UI-правил

**Требуется** всё перечисленное в 5.1–5.3. **Фактически:** отдельного хука/линтера на `@php`, нативные диалоги или uppercase нет; `eslint.config.js` покрывает только `resources/js/**/*.js`. Нарушения ловит ревью (для UI — `ui-builder`), а не гейт.

## 6. Laravel/PHP стандарты

### 6.1 Версии (сверять с `composer.lock` при переносе)

| Пакет | Версия на дату снимка |
|---|---|
| PHP | 8.5 (в `composer.json` требование `^8.5.12`) |
| laravel/framework | v13.38.0 |
| filament/filament | v5.10.3 |
| livewire/livewire | v4.4.8 |
| phpunit/phpunit | 12.5.40 |
| larastan/larastan | v3.13.2 |
| laravel/pint | v1.32.1 |
| laravel/dusk | v8.7.2 |
| Horizon 5, Sanctum 4, Socialite 5, Tailwind 4, ESLint 10 | по guideline проекта |

Коды/флаги и версии не выдумывать: смотреть `composer.lock`, `package.json`, `vendor/bin/* --version`.

### 6.2 Конвенции проекта

- Следовать существующим конвенциям приложения: при создании/правке файла смотреть соседние файлы на структуру, подход, нейминг.
- Описательные имена переменных/методов: `isRegisteredForDiscounts`, а не `discount()`.
- Перед новым компонентом — проверить существующие и переиспользовать.
- Держаться существующей структуры каталогов; новые базовые папки — только с одобрения. Зависимости без одобрения не менять.
- Не удалять тесты/тестовые файлы без одобрения — это не временные helper'ы.
- Не создавать verification scripts/tinker, если функциональность уже покрыта тестами.
- API: по умолчанию Eloquent API Resources + версионирование, если существующие API-роуты не диктуют иное.
- Ссылки на другие страницы — named routes + `route()`.
- Ответы — краткие, по делу, без объяснения очевидного.

### 6.3 PHP

- Фигурные скобки у всех control structures, даже для однострочного тела.
- PHP 8 constructor property promotion: `public function __construct(public GitHub $github) { }`. Пустых zero-parameter `__construct()` не оставлять (кроме private).
- Явные return types и type hints всех параметров: `function isAccessible(User $user, ?string $path = null): bool`.
- TitleCase для ключей enum: `FavoritePerson`, `BestLake`, `Monthly`.
- PHPDoc-блоки предпочтительнее inline-комментариев; inline — только для исключительно сложной логики. Array shape type definitions — в PHPDoc.

### 6.4 Создание файлов, модели, URL

- Файлы — `artisan make:*` с `--no-interaction` и правильными `--options`; сначала `--help`.
- Новые модели — вместе с фабрикой и сидером; спросить, нужно ли ещё что-то.
- Для тестовых моделей — фабрики и их custom states, а не ручная сборка. Faker — `$this->faker->word()` или `fake()->randomDigit()` по конвенции файла.
- Миграция — одно понятное изменение; последствия для БД объяснять по-русски (предсказуемость схемы, понятные joins).
- Если действительно нужна новая pivot-таблица — имя `pivot_<entity>_<entity>`.

### 6.5 Sail, Pint, Quality Gate

- PHP/Artisan/Composer — через Sail: `vendor/bin/sail artisan|composer|php …`. Исключения окружения: `npm run build`/`npm run dev` — на хосте macOS; при конфликте порта 80 тесты/Pint — `docker exec <project>-horizon-1 …`.
- После правок PHP — `vendor/bin/sail bin pint --dirty --format agent`. Не использовать `--test`-режим Pint (он только проверяет) — запускать исправляющий `--format agent`.
- Перед каждым тестом и коммитом — Larastan: `vendor/bin/sail php vendor/bin/phpstan analyse` (полный гейт — `.claude/scripts/quality-gate.sh`, `--fast` для коммита, `--merge` перед мержем; подробности — 02/03).
- `.claude/scripts/quality-gate.sh` также проверяет `site-pages:check-slugs`, eslint и симлинки скиллов `.claude/skills` ↔ `.ai/skills` — копия вместо симлинка запрещена.
- ViteException «Unable to locate file in Vite manifest» — на хосте `npm run build` (или `npm run dev`, `composer run dev`), не через Sail.

### 6.6 Документация

Создавать документацию только по явному запросу пользователя. Superpowers-скиллы по умолчанию пишут в `docs/superpowers/` — здесь это не так: дизайн и планы живут в `planning/plans/PLAN-{N}-*.md` (см. 01).

## 7. Тесты

- **Только PHPUnit** (классы). Встреченный Pest конвертировать. Создание: `vendor/bin/sail artisan make:test --phpunit --no-interaction {Name}` (в окружении с занятым портом — `docker exec <project>-horizon-1 php artisan make:test --phpunit --no-interaction {Name}`); `--unit` — для unit, большинство тестов — Feature.
- **Каждое изменение программно протестировано**: новый тест или обновление существующего, затем прогон затронутых тестов.
- Покрывать happy path, failure path и edge cases. Тест, который не может упасть, — не тест; для фикса подтвердить падение на pre-fix поведении.
- **Узкий прогон:** `vendor/bin/sail artisan test --compact --filter=testName`; файл — `vendor/bin/sail artisan test --compact tests/Feature/ExampleTest.php`; всё — `vendor/bin/sail artisan test --compact`.
- **Dusk** — для интерактивной UI-фичи, в темпе Feature-теста. Своя БД `app_dusk`, которую Dusk truncate'ит; `DuskTestCase` несёт allowlist. Перед Dusk — `npm run build` на хосте.
- **Никогда не вайпать БД**: никаких `migrate:fresh`/`db:wipe` кроме собственной БД Dusk и без причины. PHPUnit использует `testing`.
- Перед тестом — Larastan; перед мержем — полный набор (PHPUnit, Dusk, Larastan, Pint, eslint), не отфильтрованное подмножество.
- «Для каждого X» — тест-перебор (см. §3).
- **Фактически:** последовательность Larastan → site-slugs → Pint → PHPUnit → eslint → symlink-инвариант исполняет `quality-gate.sh`; хук `commit-gate` гоняет `--fast` (без полного прогона тестов) перед коммитом.

## 8. Безопасность

### 8.1 152-ФЗ — на каждой фиче

Приложение обрабатывает данные пользователей, поэтому ПД могут утекать «сбоку». Для изменения под ревью ответить явно на пять вопросов:

1. **Какие ПД затрагиваются?** Имена, email, телефоны, адреса, IP, cookies, любой идентификатор человека — включая ПД, случайно попавшие в HTML страниц или query-string URL.
2. **Каково правовое основание?** Договор с клиентом, согласие, законный интерес — назвать.
3. **Хранится ли в России?** Первичное хранение ПД граждан РФ должно быть на инфраструктуре в РФ; флажок на всё, что уводит данные наружу, включая сторонние сервисы.
4. **Оператор или обработчик?** Роль проекта для этих данных и покрывает ли её договор с клиентом.
5. **Есть ли скрытый сбор?** Сбор данных о посетителях без их ведома — самая острая грань.

Новый код не должен возвращать ПД в URL, строку лога, cache key или error report.

### 8.2 Секреты и `scan-secrets.sh`

Сканер читает добавленные строки диффа со stdin и имеет три независимых правила:

1. Длинный литерал (12+ символов) в присваивании «секретному» имени (`api_key`, `secret`, `password`, `passwd`, `passphrase`, `private_key`, `access_token`, `auth_token`, `client_secret`).
2. Заголовок PEM приватного ключа: `-----BEGIN [A-Z ]*PRIVATE KEY-----`.
3. Узнаваемые формы токенов: `sk-…`, `gh[pousr]_…`, `github_pat_…`, `AKIA…`, `xox[baprs]-…`, JWT `eyJ….…`.

Пропускаются индирекции (`env(`, `config(`, `getenv(`, `${…}`, `$var`, `<placeholder>`, `your_…`, `change_me`, `xxx`, `***`) и строки с явной пометкой `not-a-secret` (для фикстур/документации).

    git diff --cached -U0 | .claude/scripts/scan-secrets.sh   # 0 — чисто, 1 — найдено (строки в stderr)
    .claude/scripts/scan-secrets.sh --self-test               # 15 проб, проверка самого сканера

**Фактически:** сканер вызывает `commit-gate` (агентский PreToolUse на `git commit`, он же в Codex-адаптере). Нативный `.githooks/pre-commit` секреты **не** сканирует — коммит владельца из терминала в обход агентского гейта на секреты не проверяется. Ложное срабатывание: убрать фрагмент из диффа или попросить владельца закоммитить в своём терминале. Источники: `.claude/scripts/scan-secrets.sh`, `.claude/hooks/commit-gate.sh`, `.githooks/pre-commit`.

### 8.3 Денежные пути

`.claude/hooks/money-paths.txt` — маски fnmatch по полному пути (`*` захватывает и `/`; строка, заканчивающаяся на `/`, — префикс каталога). Если дифф ветки трогает любой путь, перед мержем нужны **обе** отметки ревью — `opus` и `codex`.

- По имени (шаблон, дополняется путями проекта): `app/*Payment*`, `app/*Billing*`, `app/*Refund*`, `app/*Invoice*`, `app/*Subscription*`, `app/*Balance*`, `app/*Price*`, `app/*Tariff*`; в `database/factories/` и `database/migrations/` — те же слова; `config/*billing*`, `config/*payment*`.
- Полноту держит тест `test_every_money_keyword_file_is_money` (`.claude/hooks/test_merge_gate.py`): новый файл с денежным словом в имени без строки в `money-paths.txt` роняет тест.

    .claude/scripts/mark-reviewed.sh --full  --by opus|codex <branch> "итог"   # полное ревью вершины
    .claude/scripts/mark-reviewed.sh --delta --by opus|codex <branch> "итог"   # только правки после полного

**Фактически:** обе отметки требует `merge-gate` (E12, `merge_checks.py`); на коммит это не распространяется. Деньги дополнительно: один аудит `opus` и один Codex параллельно, затем одна проверка правок.

### 8.4 Роль `compliance-checker`

Отдельный субагент (sonnet) для аудита перед релизом: пять вопросов 152-ФЗ, `docker exec <project>-horizon-1 composer audit`, `npm audit` на хосте, скан диффа на секреты (включая фикстуры, тестовые данные, комментарии), auth/authorize у новых роутов, реальный `authorize()` у FormRequest, mass-assignment, новые исходящие вызовы с данными клиента. **Report, not fix:** findings возвращаются оркестратору. Формат: `severity | file:line | what is wrong | what would fix it`, severity — `blocker` (не шипить), `risk` (только с записанным решением), `note`. Чистая категория называется прямо («no PD touched»); blocker нельзя смягчать до note.

## 9. Контекст-гигиена, документация, минимальные правки

### 9.1 Контекст-гигиена (alwaysApply)

- Перед чтением файла спросить: нужен весь файл или конкретные строки? Читать диапазоном (`offset`/`limit`) или через grep, не целиком.
- В контекст выводить только решающую строку вывода, не весь лог: `| tail -3` вместо голого прогона.
- Три неудачные попытки подряд по одной причине — остановиться и сменить подход, а не повторять четвёртую. Если подход неясен — сказать и спросить.
- Долгую механическую работу отдавать субагенту: его транскрипт не оседает в основном контексте, возвращается только вывод.
- Контекст на исходе — сказать прямо и предложить `/compact` с фокус-подсказкой (Claude-специфичная команда; в другом клиенте — штатное сжатие/новая сессия). Сам агент её не запускает.

### 9.2 Документация

Создавать документацию только по явному запросу. Не создавать verification-скрипты, если тесты уже покрывают функциональность. Планы и дизайн — в `planning/`, не в `docs/superpowers/`.

### 9.3 Минимальные правки

Делать **наименьшее связное изменение**, которое полностью решает задачу. Не трогать посторонний код, не делать opportunistic refactoring. Критерий: «это изменение обязательно для задачи?» Если да — включить; если нет — отдельно. Багфикс должен выглядеть как багфикс, маленькая фича — как маленький сфокусированный дифф. Минимальность не отменяет обязательных спутников фичи (миграция + fillable + правило FormRequest + тест — это не scope creep).

## 10. Быстрый чек-лист перед сдачей

- [ ] Правка минимальна и не трогает постороннее; в Blade нет `@php`, нативных диалогов и PHP-логики.
- [ ] Новые запросы — по лестнице; set-based не разложен в PHP-цикл; raw SQL обоснован комментарием.
- [ ] Filament — правильный namespace, `make()`, `->schema()`, корректные типы свойств.
- [ ] Тесты: PHPUnit, фабрики, happy/failure/edge; «для каждого X» — перебор; БД не вайпалась.
- [ ] Larastan и Pint прогнаны; Quality Gate не отключён.
- [ ] 152-ФЗ: ПД не вернулись в URL/лог/cache/ошибку; секретов в диффе нет; денежные пути — оба ревью.
- [ ] Документация не создавалась без запроса.

## 11. Источники

| Файл | Что взято |
|---|---|
| `CLAUDE.md` (стр. 96–218) | Filament, столпы, UI-правила, конспект Boost, окружение, деньги — два ревью |
| `.ai/guidelines/pillars.md` | Resource Economy, Query Building, полное покрытие множеств |
| `.ai/guidelines/ui-rules.md` | обязательные навыки, диалоги/toast, запрет PHP в Blade |
| `.ai/guidelines/filament.md` | namespace, частые ошибки, artisan |
| `.ai/guidelines/environment.md` | npm на хосте, horizon-контейнер, restart после очередей, composer refresh |
| `.claude/reference/filament-patterns.md` | Get/Set, Section/Grid, Repeater, таблицы, actions, тесты (Pest — см. §4.6) |
| `.claude/reference/laravel-boost-guidelines.md` | foundation/boost/php/sail/tests/laravel-core/pint/phpunit |
| `.claude/rules/context-hygiene.md` | контекст-гигиена |
| `.claude/rules/working-rules.md` | рабочие правила Claude/Codex: БД и тесты, кто что ревьюит |
| `.claude/hooks/money-paths.txt` | денежные маски и каталоги |
| `.claude/scripts/scan-secrets.sh` | правила сканера, `--self-test`, формат запуска |
| `.claude/hooks/commit-gate.sh`, `.claude/hooks/merge-gate.sh`, `.claude/hooks/merge_checks.py`, `.claude/hooks/test_merge_gate.py` | enforcement секретов и денег (E12) |
| `.githooks/pre-commit` | факт: секреты нативным git-хуком не сканируются |
| `.claude/agents/compliance-checker.md` | роль, 152-ФЗ, аудит зависимостей, формат findings |
| `.claude/agents/test-writer.md` | PHPUnit, фабрики, Dusk, запрет wipe БД |
| `.ai/skills/laravel-clean-code/rules/core-minimize-change.md` | минимальные правки |
| `config/boost.php`, `boost.json`, `composer.json`, `composer.lock` | exclude Filament, список скиллов, версии и отсутствие Pest |
| `.claude/scripts/quality-gate.sh` | состав гейта, место Larastan/Pint/тестов |
| `tests/Feature/SitePages/SiteSettingsTest.php` | рабочий PHPUnit-образец теста Filament-панели |
