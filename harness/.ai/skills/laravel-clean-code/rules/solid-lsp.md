---
id: solid-lsp
title: Liskov Substitution Principle (LSP)
category: solid-principles
priority: critical
tags: [solid, lsp, inheritance, contract, subtype]
related: [solid-ocp, solid-isp, core-composition]
---

# Liskov Substitution Principle (LSP)

Subtypes must preserve the behavioral contract of their parent type. A subclass must be usable wherever the parent class is expected, without the caller needing to know the difference. Do not use inheritance when composition or direct implementation is simpler. Subtypes cannot strengthen preconditions or weaken postconditions.

## Bad Example

```php
// ❌ Square IS-A Rectangle only if you ignore the contract
class Rectangle
{
    public function __construct(protected float $width, protected float $height) {}

    public function setWidth(float $w): void { $this->width = $w; }
    public function setHeight(float $h): void { $this->height = $h; }
    public function area(): float { return $this->width * $this->height; }
}

class Square extends Rectangle
{
    public function setWidth(float $w): void
    {
        $this->width = $w;
        $this->height = $w; // surprise: also changes height
    }
    public function setHeight(float $h): void
    {
        $this->width = $h;
        $this->height = $h; // surprise: also changes width
    }
}

// Problem:
// $rect = new Square(5, 5);
// $rect->setWidth(10);
// echo $rect->area(); // expecting 50, gets 100 — caller is surprised
// Square cannot substitute for Rectangle — LSP violation
```

## Good Example

```php
// ✅ Composition, or separate hierarchies
final readonly class Rectangle
{
    public function __construct(public float $width, public float $height) {}

    public function area(): float
    {
        return $this->width * $this->height;
    }
}

final readonly class Square
{
    public function __construct(public float $side) {}

    public function area(): float
    {
        return $this->side ** 2;
    }
}

// Or, if you genuinely need a polymorphic interface:
interface Shape
{
    public function area(): float;
}

final readonly class Rectangle implements Shape
{
    public function __construct(public float $width, public float $height) {}
    public function area(): float { return $this->width * $this->height; }
}

final readonly class Square implements Shape
{
    public function __construct(public float $side) {}
    public function area(): float { return $this->side ** 2; }
}

// Benefits:
// 1. No false IS-A relationship
// 2. No surprise side effects
// 3. Each type is final, simple, testable
// 4. Polymorphism via interface, not inheritance
```

## The Three LSP Rules

1. **Preconditions cannot be strengthened**: a subtype cannot require more than the parent.
2. **Postconditions cannot be weakened**: a subtype cannot promise less than the parent.
3. **Invariants must be preserved**: a subtype cannot break what the parent guarantees.

## Laravel Example

```php
// ❌ Subclass that throws where parent doesn't
abstract class PaymentGateway
{
    abstract public function charge(Order $order): PaymentResult;
}

final class TestGateway extends PaymentGateway
{
    public function charge(Order $order): PaymentResult
    {
        throw new \RuntimeException('Not implemented in test');
        // LSP violation: callers expect a PaymentResult, get an exception
    }
}

// ✅ Either implement it for real, or use a mock at the test boundary
// Mock the parent in the test, don't extend with broken behavior
```

## When to Apply

- About to use inheritance between two classes — verify the IS-A relationship is real.
- A subclass overrides a method and changes the semantics.
- A subclass throws new exceptions not in the parent's contract.
- A subclass has stricter input validation than the parent.

## When NOT to Apply

When the types are not in a real IS-A relationship:

```php
// ❌ User IS-A Model — yes, real IS-A
// ❌ AdminUser IS-A User — maybe, depends on whether Admin is just a role
// ✅ AdminUser has-a Role — composition, not inheritance
final class User
{
    public function __construct(public Role $role) {}
}
```

## Why

1. **No surprise**: callers don't need to know which subtype they have.
2. **Easier testing**: a mock subtype must behave like the real one.
3. **Less defensive code**: callers don't need to ask "is this a Square?".
4. **Composition over inheritance**: LSP violations usually signal wrong abstraction.
5. **Easier refactoring**: a stable contract allows implementations to change.
6. **Framework trust**: Laravel's contracts (Cache, Mail) rely on LSP.
7. **Fewer bugs**: the worst bugs are subtype surprises.

## Practical Heuristic

If a subclass overrides a method and:
- changes what fields are affected,
- throws a new exception,
- requires more arguments,
- returns a narrower type,
- has different side effects,

it's probably a LSP violation. Prefer composition.
