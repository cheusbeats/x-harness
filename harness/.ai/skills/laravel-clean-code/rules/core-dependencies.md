---
id: core-dependencies
title: Avoid New Dependencies When Possible
category: core-principles
priority: critical
tags: [dependencies, composer, yagni, minimal]
related: [core-arch-decision-test, core-yagni, core-kiss]
---

# Avoid New Dependencies When Possible

Do not add a new Composer dependency when the problem can be reasonably solved with PHP, the standard library, or existing project dependencies. Add a dependency only when it provides a concrete advantage that justifies its maintenance, security, and operational cost.

## Bad Example

```php
// ❌ Adding nesbot/carbon for "DateTime" when PHP has DateTimeImmutable
// composer.json
{
    "require": {
        "nesbot/carbon": "^2.0", // added for one date diff
        "ramsey/uuid": "^4.0",   // PHP 8.3+ has uuid_create() / Ramsey is overkill
        "spatie/array-to-xml": "^1.0" // PHP can build XML in 5 lines
    }
}

// In code:
$diff = Carbon::parse($start)->diffInDays(Carbon::parse($end));
// vs. native:
$diff = (new DateTimeImmutable($start))->diff(new DateTimeImmutable($end))->days;

// Problems:
// 1. 3 new packages for problems PHP solves natively
// 2. Each adds update surface, security risk, install time
// 3. Each is a "small thing" that compounds
// 4. Composer audit becomes noisy
```

## Good Example

```php
// ✅ Use PHP and Laravel built-ins

// 1. Native DateTimeImmutable
$diff = (new DateTimeImmutable($start))->diff(new DateTimeImmutable($end))->days;

// 2. Laravel's Str::uuid() (already in the framework)
use Illuminate\Support\Str;
$id = Str::uuid();

// 3. Laravel's Arr::toXml() (already in the framework) or a 5-line helper
use Illuminate\Support\Arr;
$xml = Arr::toXml(['order' => $order->toArray()]);

// composer.json — UNCHANGED

// Benefits:
// 1. No new packages
// 2. No new version pins
// 3. No new security audit items
// 4. No new contributor dependency
// 5. Faster install
```

## When a Dependency IS Justified

A new dependency is justified when it provides a concrete, recurring, non-trivial capability:

```php
// ✅ Justified: spatie/laravel-permission
// Reason: complex authorization (roles + permissions + teams) that would take
// 500+ lines to reimplement correctly with tests

// ✅ Justified: intervention/image
// Reason: image manipulation, format conversion, watermarking — well-tested library

// ✅ Justified: league/csv
// Reason: streaming CSV export/import, edge cases (BOM, escaping, encoding)

// The check:
// - Would I reimplement this in 100+ lines? Probably yes → consider dependency
// - Is the library widely used and maintained? Yes → safer
// - Is it solving a problem I face more than once? Yes → more justified
```

## The Decision Checklist

Before adding a Composer package:

1. Can PHP 8.4 stdlib solve this?
2. Can Laravel's built-in helpers/classes solve this?
3. Does an existing project dependency already solve this?
4. Is the problem complex enough to justify the dependency?
5. Is the library actively maintained?
6. Is the library widely used (low risk of abandonment)?
7. Will removing it later be cheap?

If 1, 2, or 3 is "yes" — do not add the dependency.

## Why

1. **Security**: every dependency is a potential CVE.
2. **Maintenance**: every dependency has its own release cadence.
3. **Install time**: more packages = slower CI, slower deploys.
4. **Lock-in**: dependencies leak into your code's design.
5. **Cost**: 100 small dependencies > 5 well-chosen ones.
6. **YAGNI alignment**: dependencies for hypothetical needs = waste.
7. **Simplicity**: less to know, less to upgrade.

## When to Apply

- Before `composer require`.
- During architecture discussion when someone says "there's a package for that".
- When reviewing a PR that adds a dependency.
- When the package would be used in only one place.

## When NOT to Apply

- When the problem is genuinely complex and well-served by a library.
- When reimplementing would be a security risk (e.g., crypto).
- When the team already depends on the package.
- When the package is a Laravel official package (Sanctum, Horizon, Scout, etc.).
