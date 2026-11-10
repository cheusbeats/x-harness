---
id: solid-ocp
title: Open/Closed Principle (OCP)
category: solid-principles
priority: critical
tags: [solid, ocp, extension, strategy]
related: [core-premature-abstraction, solid-lsp, solid-isp, laravel-events]
---

# Open/Closed Principle (OCP)

Make extension safe when extension is an actual requirement. Do not create extensibility infrastructure before real extension cases exist. A class is open for extension but closed for modification — meaning new behavior is added by adding new code, not by editing old code that already works.

## Bad Example

```php
// ❌ Switch on type to add new behavior
final class OrderProcessor
{
    public function process(Order $order): void
    {
        switch ($order->type) {
            case 'standard':
                $this->chargeStandard($order);
                break;
            case 'subscription':
                $this->chargeSubscription($order);
                break;
            case 'preorder':
                $this->chargePreorder($order);
                break;
            // To add 'gift': edit this class, add a case, add a method
        }
    }
}

// Problems:
// 1. Every new order type edits the processor
// 2. Switch grows unbounded
// 3. Tests multiply per case
// 4. High risk: editing existing, working code
```

## Good Example

```php
// ✅ Extend by adding a new class
interface OrderProcessor
{
    public function process(Order $order): void;
}

final class StandardOrderProcessor implements OrderProcessor
{
    public function process(Order $order): void
    {
        $this->charge($order);
    }
}

final class SubscriptionOrderProcessor implements OrderProcessor
{
    public function process(Order $order): void
    {
        $this->chargeRecurring($order);
    }
}

// Resolution happens once, at the boundary (e.g. action, container, route)
final class ProcessOrderAction
{
    public function __construct(
        private readonly StandardOrderProcessor $standard,
        private readonly SubscriptionOrderProcessor $subscription,
    ) {}

    public function execute(Order $order): void
    {
        match ($order->type) {
            'standard' => $this->standard->process($order),
            'subscription' => $this->subscription->process($order),
            default => throw new \InvalidArgumentException("Unknown type: $order->type"),
        };
    }
}

// Or, simpler: use Laravel's container tag pattern
// Or, simplest: events — every processor is a listener on OrderPlaced

// Benefits:
// 1. New order type = new class, no edits to existing
// 2. Existing processors stay untouched
// 3. Each processor is testable in isolation
// 4. The switch lives in one place (boundary)
```

## When to Apply

- The `match`/`switch` already has 3+ cases that grow over time.
- A new requirement would force editing a class that has been stable for months.
- Multiple unrelated callers need different behaviors on the same input.

## When NOT to Apply (Pragmatic)

```php
// ❌ OCP gone wrong: interface + 1 implementation
interface PasswordHasher
{
    public function hash(string $password): string;
    public function verify(string $password, string $hash): bool;
}

final class BcryptPasswordHasher implements PasswordHasher { /* ... */ }

// ✅ Use Laravel's built-in Hash facade
Hash::make($password);
Hash::check($password, $user->password);
```

OCP is for **real extension** — when 2+ implementations exist or are imminent. Not for one.

## Laravel's Built-in OCP

Laravel already implements OCP for you:

- **Events / Listeners**: extend by adding a listener, not by editing the dispatcher.
- **Notifications**: extend via channels.
- **Service Container**: swap implementations via bindings.
- **Middleware**: extend by adding, not by editing the kernel.

Reach for these before building a custom OCP system.

## Why

1. **Stable code stays stable**: less risk of regressions.
2. **Parallel work**: different people can add different extensions.
3. **Testability**: each extension is a small, focused class.
4. **Plugin-friendliness**: third parties can extend without forking.
5. **Real DRY**: the boundary is fixed, the implementations vary.
6. **YAGNI alignment**: only when 2+ implementations exist.
7. **Laravel-native**: events and container already give you OCP.
