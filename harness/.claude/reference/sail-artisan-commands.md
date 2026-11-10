# Sail & Artisan Command Reference

All PHP/Composer/Node commands run through Docker via `vendor/bin/sail`. Never run them bare.

## Service Management

```bash
vendor/bin/sail up -d       # Start services in background
vendor/bin/sail stop        # Stop all containers
vendor/bin/sail open        # Open app in browser (http://localhost)
```

## Post-Pull Refresh

After `git pull` on another machine, run once:
```bash
vendor/bin/sail composer refresh
```
Wraps: `artisan optimize:clear`, `composer dump-autoload`, `artisan migrate --force`, `artisan queue:restart`.
Fixes "Target is not instantiable" DI errors and forces queue workers to reload code.

## Artisan

**Discovery:**
```bash
vendor/bin/sail artisan list
vendor/bin/sail artisan [command] --help
```

**Routes & Config:**
```bash
vendor/bin/sail artisan route:list --method=GET --name=users --path=api
vendor/bin/sail artisan config:show app.name
vendor/bin/sail artisan config:show database.default
```

**Make (models, migrations, tests):**
```bash
vendor/bin/sail artisan make:model ModelName --migration
vendor/bin/sail artisan make:test --phpunit TestName       # Feature test (default)
vendor/bin/sail artisan make:test --phpunit --unit TestName # Unit test
vendor/bin/sail artisan make:class ClassName
```
Always pass `--no-interaction` to ensure CI-safe behavior.

**Tinker (PHP REPL):**
```bash
vendor/bin/sail artisan tinker --execute 'Your::code();'
# Single quotes prevent shell expansion. Double quotes for PHP strings inside:
vendor/bin/sail artisan tinker --execute 'User::where("active", true)->count();'
```

## Composer

```bash
vendor/bin/sail composer install
vendor/bin/sail composer dump-autoload
vendor/bin/sail composer refresh
```

## Node / Frontend

```bash
vendor/bin/sail npm run dev          # Watch & rebuild
vendor/bin/sail npm run build        # Production build
vendor/bin/sail composer run dev     # Both npm dev + php artisan serve in one
```

If Vite manifest error: run `vendor/bin/sail npm run build` or `npm run dev`.

## PHP Static Analysis & Formatting

**Larastan (static type checker):**
```bash
vendor/bin/sail php vendor/bin/phpstan analyse
# or if alias exists:
vendor/bin/sail composer larastan
```
Run **before every commit and before every test**. Non-negotiable.

**Pint (code formatter):**
```bash
vendor/bin/sail bin pint --dirty --format agent    # Fix only changed files
# Never use --test; Pint should fix, not report.
```

## Tests

```bash
# All tests — parallel (paratest, one testing_test_N DB per process; ~3.5 min instead of ~15),
# then the race tests (group serial-db, shared `testing` DB) sequentially. Never two full runs at once.
vendor/bin/sail artisan test --compact --parallel --processes=8 --exclude-group=serial-db
vendor/bin/sail artisan test --compact --group=serial-db

# Single file
vendor/bin/sail artisan test --compact tests/Feature/ExampleTest.php

# Filter by test name
vendor/bin/sail artisan test --compact --filter=testName
```

**Run minimal subset before finalizing**, then ask user if full suite should run.

---

## Key Rules

- **All commands via `vendor/bin/sail`.** No bare `php`, `artisan`, `npm`, `composer`.
- **`--no-interaction` on all make: commands** for CI safety.
- **Larastan before commit.** Non-negotiable gate.
- **Post-pull: `sail composer refresh`** immediately on a fresh clone or after `git pull` on a new machine.
