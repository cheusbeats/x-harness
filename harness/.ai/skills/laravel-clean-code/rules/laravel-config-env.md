---
id: laravel-config-env
title: Use config(), Never env() Outside config/
category: laravel-architecture
priority: critical
tags: [config, env, cache, security]
related: [core-boring-code, laravel-migrations, core-error-handling]
---

# Use config(), Never env() Outside config/

Inside the application code (controllers, services, jobs, listeners, Blade), always read config values via `config('app.name')`, never `env('APP_NAME')`. The only place `env()` is allowed is inside files in the `config/` directory. After `php artisan config:cache`, `env()` returns `null` outside config/ — making the app silently fail.

## Bad Example

```php
// ❌ env() in a controller
final class SitemapController extends Controller
{
    public function index(): Response
    {
        $url = env('APP_URL') . '/sitemap.xml'; // null when config is cached
        return response(file_get_contents(public_path('sitemap.xml')))
            ->header('Content-Type', 'application/xml');
    }
}

// ❌ env() in a service
final class MailService
{
    public function send(string $to, string $subject): void
    {
        $host = env('MAIL_HOST'); // null when config is cached
        // ...
    }
}

// ❌ env() in a Blade view
<a href="{{ env('APP_URL') }}/terms">Terms</a>

// Problems:
// 1. After `config:cache`, env() returns null in app code
// 2. App silently uses wrong values
// 3. Hard to debug — no error, just wrong behavior
// 4. Vendor packages can't override
// 5. Tests can't easily mock env
```

## Good Example

```php
// ✅ env() ONLY inside config/ files

// config/app.php
return [
    'name' => env('APP_NAME', 'Laravel'),
    'url' => env('APP_URL', 'http://localhost'),
    'debug' => env('APP_DEBUG', false),
];

// config/mail.php
return [
    'host' => env('MAIL_HOST', 'smtp.mailgun.org'),
    'port' => env('MAIL_PORT', 587),
];

// ✅ App code uses config()
final class SitemapController extends Controller
{
    public function index(): Response
    {
        $url = config('app.url') . '/sitemap.xml';
        return response(file_get_contents(public_path('sitemap.xml')))
            ->header('Content-Type', 'application/xml');
    }
}

final class MailService
{
    public function send(string $to, string $subject): void
    {
        $host = config('mail.host');
        // ...
    }
}
```

```blade
{{-- ✅ Blade uses config() --}}
<a href="{{ config('app.url') }}/terms">Terms</a>
```

## The Rule

- `env()` — only in `config/*.php` files.
- `config()` — everywhere else (controllers, services, jobs, views, providers, tests).

## Why This Matters

When you run `php artisan config:cache` (production best practice):

- Laravel loads `config/*.php` once and caches them.
- `env()` outside `config/*.php` is **null** because the `.env` file isn't loaded anymore.
- App code that uses `env()` silently returns null.

The error is silent. The bug is subtle. The fix is easy: use `config()`.

## Add a Test

```php
// tests/Feature/EnvUsageTest.php
it('does not use env() outside config files', function () {
    $files = File::allFiles(app_path());
    $violations = [];

    foreach ($files as $file) {
        if (preg_match('/\benv\(/', $file->getContents())) {
            $violations[] = $file->getRelativePathname();
        }
    }

    expect($violations)->toBeEmpty(
        "Files using env() outside config/: " . implode(', ', $violations),
    );
});
```

## When to Apply

- Every read of a `.env` value in app code.
- Every third-party service URL / API key.
- Every flag / toggle / driver selection.

## When NOT to Apply

- Inside `config/*.php` — `env()` is the right call.
- Inside `bootstrap/app.php` (early bootstrap).
- Inside a test that needs to set a runtime env value (`config()->set(...)` is preferred).

## Why

1. **Config cache works**: `php artisan config:cache` is safe.
2. **Predictable**: same value in all environments via config.
3. **Testable**: `config()->set()` works, `env()->set()` is messy.
4. **Vendor-friendly**: packages can override via their config.
5. **Documented**: config files are the documented surface.
6. **Laravel-aligned**: framework convention.
7. **Catches bugs early**: a linter / test can enforce the rule.
