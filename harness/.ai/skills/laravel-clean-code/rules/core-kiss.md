---
id: core-kiss
title: Keep It Simple (KISS)
category: core-principles
priority: critical
tags: [kiss, simplicity, overengineering]
related: [core-yagni, core-boring-code, core-premature-abstraction]
---

# Keep It Simple (KISS)

Prefer the simplest correct solution. Complexity is a cost that must be paid back with concrete value. If a plain function or a single Eloquent query solves the problem, do not build a class hierarchy.

## Bad Example

```php
// ❌ Over-engineered order total calculation
interface PricingStrategyInterface
{
    public function calculate(Order $order): Money;
}

abstract class AbstractPricingStrategy implements PricingStrategyInterface
{
    public function calculate(Order $order): Money
    {
        $subtotal = $this->subtotal($order);
        $discount = $this->discount($subtotal, $order);
        $tax = $this->tax($subtotal - $discount, $order);

        return new Money($subtotal - $discount + $tax);
    }

    abstract protected function subtotal(Order $order): int;
    abstract protected function discount(int $subtotal, Order $order): int;
    abstract protected function tax(int $amount, Order $order): int;
}

final class StandardPricingStrategy extends AbstractPricingStrategy
{
    protected function subtotal(Order $order): int
    {
        return $order->items->sum(fn ($i) => $i->price * $i->quantity);
    }
    // ... etc
}

final class PricingService
{
    public function __construct(private readonly PricingStrategyInterface $strategy) {}

    public function price(Order $order): Money
    {
        return $this->strategy->calculate($order);
    }
}

// Problems:
// 1. One pricing rule (standard) behind 4 abstractions
// 2. Three subclasses for one use case
// 3. Container binding required for a static calculation
```

## Good Example

```php
// ✅ Simple: a single static method or model method
final class Order extends Model
{
    public function total(): int
    {
        return $this->items->sum(fn (OrderItem $i) => $i->price * $i->quantity);
    }
}

// Or, if logic is shared:
final readonly class Pricing
{
    public static function subtotal(Order $order): int
    {
        return $order->items->sum(fn (OrderItem $i) => $i->price * $i->quantity);
    }
}

// Benefits:
// 1. One file, one method, no container wiring
// 2. Trivial to test: `expect((new Order)->total())->toBe(100)`
// 3. No premature strategy
```

## Why

1. **Easier to read**: less indirection = faster comprehension.
2. **Easier to test**: fewer collaborators = fewer mocks.
3. **Easier to refactor**: less code to change when requirements shift.
4. **Fewer bugs**: every abstraction layer is a place for bugs.
5. **Faster onboarding**: new developers can read the code top-to-bottom.
6. **Lower maintenance cost**: no orphan interfaces, no dead strategies.
7. **Reversible**: when complexity is genuinely needed, it's easier to add than to remove.

## When to Apply

- When about to introduce an interface, abstract class, or strategy.
- When tempted to add a Service class for a one-liner.
- When designing a class with one method.
- When the project does not already have the pattern you are about to introduce.

## When NOT to Apply

KISS does not mean "dumb it down":

```php
// ❌ Not KISS — it's "dumb it down"
$total = 0;
foreach ($order->items as $item) {
    $total = $total + ($item->price * $item->qty);
}
// ✅ KISS — clear one-liner
$total = $order->items->sum(fn ($i) => $i->price * $i->quantity);
```

KISS is about removing unnecessary indirection, not removing clarity.
