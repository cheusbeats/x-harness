---
id: laravel-service-container
title: Bind Only What You Actually Swap
category: laravel-architecture
priority: critical
tags: [container, di, binding, swap, yagni]
related: [solid-dip, core-yagni, core-arch-decision-test]
---

# Bind Only What You Actually Swap

The Laravel service container is great. Most of the time you don't need to bind anything — type-hinted classes are auto-resolved. Bind only when you need to swap the implementation (testing, multi-driver, third-party integration). A binding for a single concrete class is ceremony.

## Bad Example

```php
// ❌ Binding a single concrete class
final class UserService
{
    public function __construct(private readonly UserRepository $users) {}
}

final class UserRepository
{
    public function find(int $id): ?User { return User::find($id); }
}

// In a service provider:
$this->app->bind(UserRepository::class); // pointless
$this->app->singleton(UserService::class); // pointless

// Problems:
// 1. UserRepository has one implementation — no need to bind
// 2. Auto-resolution already works
// 3. The binding adds no flexibility
// 4. The author "just in case" registered everything
```

## Good Example

```php
// ✅ Most things need no binding — type-hint and Laravel resolves

final class UserService
{
    public function __construct(private readonly UserRepository $users) {}
}

final class UserRepository
{
    public function find(int $id): ?User { return User::find($id); }
}

// No binding needed. The container auto-resolves both.
// Constructor injection happens automatically.

// Bind ONLY when swapping is a real concern
$this->app->bind(PaymentGateway::class, function () {
    return match (config('payments.default')) {
        'stripe' => new StripeGateway(config('payments.stripe.key')),
        'yookassa' => new YooKassaGateway(config('payments.yookassa.shop_id')),
    };
});
```

## When to Bind

Apply a binding in a service provider when **at least one** of these is true:

1. **Multiple implementations** of an interface exist (Stripe / YooKassa).
2. **Runtime configuration** decides the implementation (config('cache.default')).
3. **Test fakes** need to be swappable (`Mail::fake()` is already this for Mail).
4. **Singleton lifecycle** is required (e.g. expensive connections).
5. **Contextual binding**: two consumers need different implementations.

```php
// ✅ Singleton — expensive connection
$this->app->singleton(RedisManager::class, fn () => new RedisManager(config('database.redis')));

// ✅ Contextual — different consumer gets different impl
$this->app->when(PhotoController::class)
    ->needs(Filesystem::class)
    ->give(S3Filesystem::class);

$this->app->when(BackupController::class)
    ->needs(Filesystem::class)
    ->give(LocalFilesystem::class);
```

## When NOT to Bind

- Single concrete class with no interface — auto-resolved.
- Eloquent model — `app(User::class)` works without binding.
- FormRequest / Resource — Laravel handles these.
- Service class with no interface — auto-resolved.
- Anything in the same "tier" of your app.

## Laravel's Built-in Bindings

Laravel already binds the most useful contracts:

```php
// Already bound — no action needed
$this->app->make(Illuminate\Contracts\Cache\Repository::class); // works
$this->app->make(Illuminate\Contracts\Mail\Mailer::class);     // works
$this->app->make(Illuminate\Contracts\Queue\Factory::class);    // works
```

If Laravel binds it, you don't need to.

## The 4-Question Test

Before adding a binding, ask:

1. Is there more than one implementation today?
2. Will the implementation be chosen at runtime via config?
3. Is the binding's lifecycle meaningfully different (singleton vs new)?
4. Is the binding contextual (one consumer gets one impl, another gets another)?

If all 4 are "no" — do not add the binding.

## Why

1. **YAGNI**: most bindings are never used.
2. **Laravel's auto-resolution**: handles 95% of cases.
3. **Less ceremony**: no `register()` boilerplate.
4. **Easier refactoring**: no binding to update when class is renamed.
5. **Type safety**: type-hints in the constructor are enough.
6. **Faster onboarding**: developers don't have to read providers to find classes.
7. **Honest engineering**: bindings signal real abstraction.
