---
id: solid-dip
title: Dependency Inversion Principle (DIP)
category: solid-principles
priority: critical
tags: [solid, dip, di, abstraction, container]
related: [solid-isp, laravel-service-container, core-premature-abstraction]
---

# Dependency Inversion Principle (DIP)

Separate high-level business rules from infrastructure when this provides a concrete benefit. Depend on abstractions (interfaces), not concretions — when the abstraction has 2+ implementations or is needed for testability. Do not automatically introduce interfaces, repositories, adapters, ports, or service layers when a direct dependency is sufficient and appropriate.

## Bad Example

```php
// ❌ High-level policy directly depends on low-level implementation
final class OrderService
{
    public function __construct()
    {
        $this->gateway = new StripeGateway(env('STRIPE_KEY')); // new = hardcoded
        $this->mailer = new SmtpMailer(env('MAIL_HOST'));     // new = hardcoded
    }

    public function place(Order $order): void
    {
        $this->gateway->charge($order);
        $this->mailer->send('order@x.com', 'New order', $order);
    }
}

// Problems:
// 1. OrderService knows about Stripe (concrete)
// 2. OrderService knows about Smtp (concrete)
// 3. Cannot swap to another gateway without editing OrderService
// 4. Cannot test OrderService without a real Stripe account
// 5. Two reasons to change: business logic + integration choice
```

## Good Example (When 2+ Implementations Exist)

```php
// ✅ Depend on abstractions when there's real choice

interface PaymentGateway
{
    public function charge(Order $order): PaymentResult;
}

interface Mailer
{
    public function send(string $to, string $subject, string $body): void;
}

final class OrderService
{
    public function __construct(
        private readonly PaymentGateway $gateway,
        private readonly Mailer $mailer,
    ) {}

    public function place(Order $order): void
    {
        $this->gateway->charge($order);
        $this->mailer->send('order@x.com', 'New order', "Order #$order->id");
    }
}

// In a service provider:
$this->app->bind(PaymentGateway::class, StripeGateway::class);
$this->app->bind(Mailer::class, SmtpMailer::class);

// In tests: bind a fake
$this->app->bind(PaymentGateway::class, FakePaymentGateway::class);

// Benefits:
// 1. OrderService doesn't know about Stripe
// 2. Swap gateway by changing one binding
// 3. Test with fakes
// 4. Each integration is replaceable
```

## When to Apply DIP

Apply DIP only when **at least one** of these is true:

1. **2+ implementations exist or are imminent** (Stripe + YooKassa, SMTP + SES).
2. **A test needs to mock the dependency** (real implementation hits network, DB, filesystem).
3. **The integration is volatile** (third-party API, may change).
4. **The business logic is genuinely independent** from the integration.

If none of these — do not apply DIP. Use the concrete directly.

## When NOT to Apply (Pragmatic)

```php
// ❌ DIP for a single concrete with no test need
interface UserRepository
{
    public function find(int $id): ?User;
}

final class EloquentUserRepository implements UserRepository
{
    public function find(int $id): ?User
    {
        return User::find($id);
    }
}

// ✅ Just use the model
User::find($id);
// Test with: User::factory()->create()
```

DIP is for **real abstraction**, not for "testability theater".

## Laravel's Built-in DIP

Laravel already does DIP for you via the container:

```php
// Type-hint the contract in the constructor
public function __construct(
    private readonly Illuminate\Contracts\Cache\Repository $cache,
) {}

// Bind in a service provider
$this->app->bind(
    Illuminate\Contracts\Cache\Repository::class,
    fn () => Cache::driver('redis'),
);
```

You don't need a custom interface if Laravel's contract already exists.

## DIP vs DI

- **DIP**: the design principle (depend on abstractions).
- **DI (Dependency Injection)**: the technique (pass dependencies from outside).

Laravel's container does DI. Whether you need an interface (DIP) is a separate question.

## Why

1. **Replaceable**: swap implementations without editing the consumer.
2. **Testable**: replace with fakes in tests.
3. **Stable**: business logic doesn't change when integrations change.
4. **Laravel-aligned**: the container is built for this.
5. **YAGNI alignment**: only when 2+ implementations exist.
6. **Honest**: the interface documents the real abstraction.
7. **Faster debugging**: when Stripe is down, you know it's the gateway, not the business.

## The Test

Before creating an interface:

1. Will there be 2+ implementations? (Stripe + YooKassa)
2. Is the dependency volatile? (3rd-party API)
3. Do tests need a fake? (Mail::fake() already exists — check Laravel first)
4. Is the abstraction stable? (won't change every sprint)

If 1, 2, 3 are "no" — do not create the interface.
