# 06 — Окружение: Sail, контейнеры, БД, команды

**Что это:** как реально устроено окружение разработки Laravel-профиля — Sail и контейнер horizon, БД, полный справочник команд и Horizon.
**Когда читать:** перед подъёмом окружения, при выборе команды (sail vs `docker exec` vs хост), после `git pull` на новой машине и перед мержем.
**Срез:** 30.10.2026. Источники — `compose.yaml`, `composer.json`, `phpunit.xml`, `.env.dusk.local`, `tests/DuskTestCase.php`, `CLAUDE.md`, `.claude/reference/environment.md`, `.claude/reference/sail-artisan-commands.md`, `outputs/AGENT_HARNESS.md`.

## 1. Стек (фактические версии)

| Компонент | Версия / требование | Источник |
|---|---|---|
| PHP | `^8.5.12` (в образах `php:8.5-fpm-alpine` и Sail `8.5`) | `composer.json` |
| Laravel | `^13.7` (locked v13.38.0) | `composer.json`, `composer.lock` |
| Livewire | v4.4.8 | `composer.lock` |
| Filament | v5.10.3 | `composer.lock` |
| Horizon | v5.50.1 | `composer.lock` |
| PostgreSQL | 17 (`postgres:17`) | `compose.yaml` |
| Redis | `redis:alpine` | `compose.yaml` |
| PHPUnit / paratest | 12.5.40 / 7.20.0 | `composer.lock` |
| Larastan / PHPStan | 3.13.2, level 5 | `composer.lock`, `phpstan.neon` |
| Pint / Sail / Dusk | 1.32.1 / 1.69.0 / 8.7.2 | `composer.lock` |
| Node/npm | локально — хост | `.ai/guidelines/environment.md` |

## 2. Sail и контейнеры

`compose.yaml` (корень проекта) поднимает сервисы:

| Сервис | Образ/команда | Назначение |
|---|---|---|
| `laravel.test` | Sail `sail-8.5/app`; порт `${APP_PORT:-80}:80`, Vite `${VITE_PORT:-5173}:${VITE_PORT:-5173}` | web/php-fpm, основной контейнер Sail |
| `horizon` | `php artisan horizon`, `restart: unless-stopped`, `stop_grace_period: 60s` | отдельный worker-пул Horizon; без него очереди не разбираются |
| `scheduler` | `php artisan schedule:work` | локальные scheduled-команды |
| `pgsql` | `postgres:17`, порт `${FORWARD_DB_PORT:-5432}` | БД |
| `redis` | `redis:alpine`, порт `${FORWARD_REDIS_PORT:-6379}` | очереди, кеш |
| `mailpit` | `axllent/mailpit`, порты 1025/8025 | почта в dev |
| `selenium` | `selenium/standalone-chromium` | браузер для Dusk |

Сеть — `sail`, тома — `sail-pgsql`, `sail-redis`. Контейнеры получают имена `<проект>-<сервис>-1`; обвязка вычисляет имя как **`<project>-horizon-1`**, где `<project>` — `COMPOSE_PROJECT_NAME` либо имя каталога основного checkout в нижнем регистре (см. `quality-gate.sh`).

- Поднять всё: `vendor/bin/sail up -d` — обязательно с контейнером `horizon`.
- Остановить: `vendor/bin/sail stop`; открыть приложение: `vendor/bin/sail open`.
- Sail-сервис `laravel.test` может не занять порт 80 (его держит другой локальный проект) — тогда PHP-команды идут через `docker exec <project>-horizon-1 …`, он поднят всегда.

## 3. Жёсткие правила окружения

Источник: `.ai/guidelines/environment.md` (влит в `CLAUDE.md`, раздел об окружении). Эти правила сильнее общих Laravel-инструкций про Sail.

1. **npm только на хосте (macOS).** `vendor/bin/sail npm install` перезаписывает `node_modules` линуксовыми rolldown-биндингами и ломает хостовую сборку. `npm run build` / `npm run dev` — на хосте. Починка: на хосте `rm -rf node_modules package-lock.json && npm install`. Правки Blade видны только после сборки на хосте.
2. **Тесты и Pint — через контейнер horizon**, если `laravel.test` не может занять порт 80:
   `docker exec <project>-horizon-1 php artisan test --compact`,
   `docker exec <project>-horizon-1 vendor/bin/pint --dirty --format agent`.
3. **После правок воркеров / синкеров / очередей — `docker restart <project>-horizon-1`**, иначе воркеры крутят старый код из памяти (кешированные синглтоны). `horizon:status` умеет врать «running» по stale-флагу; живые воркеры проверять через `docker exec <project>-horizon-1 ps aux | grep horizon:work`.
4. **После `git pull` на другой машине — `vendor/bin/sail composer refresh`.** Без этого вылезают ошибки «Target [...] is not instantiable» из закешированных DI-биндингов, а воркеры продолжают крутить старый код.

## 4. `composer refresh`

`refresh` — обёртка над `optimize:clear`, `dump-autoload`, `migrate --force`, `queue:restart` (`CLAUDE.md`, `.claude/reference/sail-artisan-commands.md`). Проектный `composer.json → scripts.refresh` может быть шире (бэкфиллы, `horizon:terminate`): для агента `composer refresh` — единственная команда пост-пулла; не собирать её из частей.

## 5. Базы данных

| Назначение | БД | Где задано |
|---|---|---|
| Dev | `DB_DATABASE` из `.env`, `DB_CONNECTION=pgsql`, `DB_HOST=pgsql`, `DB_PORT=5432` | `.env`, `compose.yaml` |
| PHPUnit | `DB_DATABASE=testing` | `phpunit.xml` (`APP_ENV=testing`, `CACHE_STORE=array`, `QUEUE_CONNECTION=sync`, `SESSION_DRIVER=array`, `MAIL_MAILER=array`) |
| Параллельные PHPUnit | `testing_test_N` — по одной БД на процесс (paratest) | комментарий в `quality-gate.sh`, `.claude/reference/sail-artisan-commands.md` |
| Dusk | `app_dusk` (`.env.dusk.local`: `DB_CONNECTION=pgsql`, `APP_URL=http://laravel.test`) | `.env.dusk.local`, `tests/DuskTestCase.php` |

- **Dusk использует свою БД.** `DuskTestCase::ALLOWED_DATABASES = ['app_dusk', 'testing']` — allowlist, потому что один раз `.env.dusk.local` указывал на рабочую БД и прогон Dusk стёр рабочие данные. `$exceptTables = ['plans']`: `plans` засеяна миграцией, а `DatabaseTruncation` её иначе вычищает.
- **Параллельный прогон:** гейт по умолчанию берёт 6 процессов (`GATE_PHPUNIT_PROCESSES`), reference — 8; больше процессов упирается в `max_connections` Postgres (~100) рядом с dev-приложением. Сначала `--exclude-group=serial-db`, затем отдельно `--group=serial-db` (гонки пишут в общую `testing` БД). Два полных прогона одновременно не запускать.
- **Никогда не чистить БД:** `migrate:fresh`, `db:wipe`, деструктивные миграции на заполненной таблице — только с явного согласия. Это столп проекта.
- `artisan --env=testing` без `.env.testing` может попасть в dev-БД: имя окружения не доказывает безопасный DSN. Проверять конфигом, а не флагом.

## 6. Полный справочник команд

### 6.1 Sail (жизненный цикл)

```bash
vendor/bin/sail up -d          # поднять все сервисы, включая horizon
vendor/bin/sail stop           # остановить контейнеры
vendor/bin/sail open           # открыть приложение в браузере
```

### 6.2 Artisan

```bash
vendor/bin/sail artisan list
vendor/bin/sail artisan [command] --help
vendor/bin/sail artisan route:list --method=GET --name=users --path=api
vendor/bin/sail artisan config:show app.name
vendor/bin/sail artisan config:show database.default
vendor/bin/sail artisan make:model ModelName --migration
vendor/bin/sail artisan make:test --phpunit TestName        # Feature (default)
vendor/bin/sail artisan make:test --phpunit --unit TestName # Unit
vendor/bin/sail artisan make:class ClassName
vendor/bin/sail artisan make:migration --no-interaction
vendor/bin/sail artisan tinker --execute 'User::where("active", true)->count();'
vendor/bin/sail artisan migrate --force
vendor/bin/sail artisan optimize:clear
vendor/bin/sail artisan queue:restart
vendor/bin/sail artisan horizon:terminate
vendor/bin/sail artisan horizon:status
vendor/bin/sail artisan site-pages:check-slugs      # шаг quality-gate
vendor/bin/sail artisan boost:list-skills           # навыки Boost
```

`--no-interaction` обязателен для `make:*` (CI-safe). В контейнере horizon те же команды — `docker exec <project>-horizon-1 php artisan …`.

### 6.3 Composer

```bash
vendor/bin/sail composer install
vendor/bin/sail composer dump-autoload
vendor/bin/sail composer refresh        # после git pull на новой машине
vendor/bin/sail composer audit          # аудит зависимостей (compliance-checker)
```

### 6.4 Frontend — только хост

```bash
npm run build      # production-сборка Vite; нужна, чтобы правки Blade были видны
npm run dev        # watch
npm run lint       # eslint resources/js (шаг quality-gate, на хосте)
```

Если Vite manifest error — `npm run build` или `npm run dev` на хосте. Sail-npm не использовать: он ломает `node_modules`.

### 6.5 Larastan и Pint

```bash
vendor/bin/sail php vendor/bin/phpstan analyse          # Larastan, обязательно перед тестом и коммитом
vendor/bin/sail bin pint --dirty --format agent         # форматирует изменённые файлы
```

Pint **чинит**, а не отчитывается: `--test` не использовать. Конфиг Larastan — `phpstan.neon` (level 5, `paths: app`, baseline, `parseModelCastsMethod: true`, один процесс).

### 6.6 Тесты

```bash
# полный прогон: parallel (paratest, БД testing_test_N на процесс), затем serial-db
vendor/bin/sail artisan test --compact --parallel --processes=8 --exclude-group=serial-db
vendor/bin/sail artisan test --compact --group=serial-db

# один файл / фильтр по имени
vendor/bin/sail artisan test --compact tests/Feature/ExampleTest.php
vendor/bin/sail artisan test --compact --filter=testName
```

Сначала минимальный набор, перед мержем — ВСЁ (полный PHPUnit, Dusk, Larastan, Pint, eslint), не отфильтрованное подмножество.

### 6.7 Dusk

```bash
npm run build                                    # на ХОСТЕ, иначе Dusk проверит вчерашний бандл
docker exec <project>-horizon-1 php artisan dusk   # или vendor/bin/sail artisan dusk
```

Dusk работает по `public/build`; `DuskTestCase::guardAgainstStaleFrontendBundle()` падает с инструкцией, если бандл не собран, — `npm run build` из контейнера не запускается. Нужен сервис `selenium` (в compose он есть).

### 6.8 Quality Gate и git-хуки

```bash
.claude/scripts/quality-gate.sh            # Larastan → site-pages:check-slugs → Pint → PHPUnit (+serial-db) → eslint → симлинки
.claude/scripts/quality-gate.sh --fast     # без полного прогона тестов (~3 с; это же гоняет хук перед git commit)
.claude/scripts/quality-gate.sh --merge    # + npm run build и Dusk (с белым списком путей)
.claude/scripts/quality-gate.sh --dusk-plan # только решение run|skip для Dusk
.claude/scripts/install-githooks.sh        # core.hooksPath=.githooks; хуки: commit-msg, post-merge, pre-commit, pre-push
```

Полный `--merge` пишет отметку `.claude/state/gates/<branch>.merge-passed` (только при чистом дереве) — её проверяет `merge-gate.sh`. Dusk в обычный прогон не входит намеренно: у него своя БД `app_dusk`, которую он truncate'ит.

## 7. Horizon

- Очереди в Redis (`QUEUE_CONNECTION=redis`); дашборд `/horizon` требует admin-пользователя, статус должен быть **Active**.
- Супервизоры задаются в `config/horizon.php`, потолки — через `HORIZON_*_MAX_PROCESSES`.
- Таймаут-лестница строго: job `timeout` < Horizon `timeout` < `retry_after` (например 180 < 210 < 300). Неверный порядок приводит к повтору до того, как Horizon успел таймаутнуть.
- После правок кода воркеров/синкеров/очередей — `docker restart <project>-horizon-1`. Живость воркеров — `ps aux | grep horizon:work`, не `horizon:status`.

## 8. Требуется vs фактически

| Утверждение | Где заявлено | Как обстоит фактически |
|---|---|---|
| «Все PHP/Composer/Node-команды через Sail, никаких голых `php`/`artisan`/`npm`» | `.claude/reference/sail-artisan-commands.md` «Key Rules» | сам гейт и правила окружения используют `docker exec <project>-horizon-1 …`, когда 80-й порт занят; npm — на хосте. Это не нарушение, а зафиксированное исключение |
| `vendor/bin/sail npm run dev/build` | `sail-artisan-commands.md`, § Node/Frontend | противоречит `.ai/guidelines/environment.md`: npm только на хосте, sail-npm ломает `node_modules`. Действует правило окружения |
| `composer refresh` = optimize:clear + dump-autoload + migrate + queue:restart | `CLAUDE.md`, `sail-artisan-commands.md` | скрипт проекта может быть шире документации |
| Полные тесты: `--processes=8` | `sail-artisan-commands.md` | гейт по умолчанию 6 процессов (`GATE_PHPUNIT_PROCESSES`, ограничение `max_connections` Postgres) |
| PHP 8.4 | тексты `.claude/agents/*`, `laravel-clean-code` | `composer.json`: `php ^8.5.12` |
| Dusk должен входить в проверку перед мержем | «перед мержем гонять ВСЁ» | Dusk — только `quality-gate.sh --merge` (или вручную); в `--fast` и в хуке коммита его нет |
| `horizon:status` показывает состояние воркеров | общепринято | может врать «running» по stale-флагу; проверять `ps aux \| grep horizon:work` |
| Git-хуки подключены | `.githooks/` | подключаются `.claude/scripts/install-githooks.sh` (`core.hooksPath=.githooks`); SessionStart предупреждает, если не подключены |

## Источники

- `compose.yaml`
- `composer.json` (scripts `refresh`, `dev`, `test`), `composer.lock` (версии); `package.json`
- `phpunit.xml`; `phpstan.neon`; `.env.dusk.local`; `tests/DuskTestCase.php`
- `CLAUDE.md` — § Git workflow, раздел об окружении, § Superpowers
- `.ai/guidelines/environment.md`; `.claude/reference/environment.md`; `.claude/reference/sail-artisan-commands.md`
- `config/horizon.php` (супервизоры, environments); `.claude/scripts/quality-gate.sh`; `.claude/scripts/install-githooks.sh`; `.githooks/`
- `.claude/agents/db-surgeon.md`, `test-writer.md`, `ui-builder.md`, `fast-worker.md` (правила npm/контейнера)
- `outputs/AGENT_HARNESS.md` — строки 371–527 (инвентаризация, приоритеты), 559–950 (полные роли)