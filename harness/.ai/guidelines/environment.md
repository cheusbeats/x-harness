## Окружение проекта — поправки к общим инструкциям

Общие Laravel-инструкции про Sail в этом проекте действуют не везде. Ниже — расхождения,
они важнее общего правила.

- **`npm run build` / `npm run dev` запускаются на ХОСТЕ (macOS), НЕ через sail.**
  `vendor/bin/sail npm install` перезаписывает `node_modules` линуксовыми rolldown-биндингами
  и ломает хостовую сборку. Чинить: на хосте `rm -rf node_modules package-lock.json && npm install`.
  Правки Blade видны только после сборки на хосте.
- **Тесты и Pint — через контейнер horizon**, если sail-сервис `laravel.test` не может занять
  порт 80 (его держит другой локальный проект; `<project>` — имя compose-проекта, по умолчанию имя каталога):
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
