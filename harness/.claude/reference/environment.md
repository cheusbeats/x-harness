# Локальное окружение — подъём и проверка (вынесено из planning/STATUS.md, PLAN-145)

Поправки про npm на хосте, тесты в контейнере horizon, рестарт воркеров и `composer refresh` — в CLAUDE.md («Окружение проекта»). Здесь только то, чего там нет.

- Поднять всё: `vendor/bin/sail up -d`, включая контейнер `horizon`: без него очередь `scans` не разбирается и сканы висят в `queued`.
- Очереди — Horizon (Redis; роли `scans` / `psi` / `metrics` / `default`, `QUEUE_CONNECTION=redis`). Дашборд `/horizon` (нужен admin-юзер), статус должен быть **Active**.
- Git-хуки: `.claude/scripts/install-githooks.sh` (SessionStart предупредит, если не подключены).
- Прогон тестов: `vendor/bin/sail artisan test --compact`; перед финалом `vendor/bin/sail bin pint --dirty --format agent`.
- Прод-раздача и вынос воркеров — `planning/plans/PRODUCTION_SCALING.md`.
- «Срез на сейчас» — `planning/ACTIVE_PLANS.md` (таблица активных планов) и `.claude/scripts/registry.sh show <id>`; отдельного STATUS-файла нет.
