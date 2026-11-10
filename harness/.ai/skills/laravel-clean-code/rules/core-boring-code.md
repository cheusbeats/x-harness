---
id: core-boring-code
title: Prefer Boring Code
category: core-principles
priority: critical
tags: [boring, readability, predictability, debuggability]
related: [core-kiss, core-comments, core-error-handling]
---

# Prefer Boring Code

Prefer predictable, conventional, obvious code. Optimize for clarity, predictability, debuggability, maintainability, and ease of review — not for sophistication or cleverness. A developer unfamiliar with the implementation should be able to understand its purpose.

## Bad Example

```php
// ❌ Clever metaprogramming
final class OrderFilter
{
    public function __construct(private readonly Builder $query) {}

    public function apply(array $criteria): Builder
    {
        return collect($criteria)
            ->filter(fn ($value) => $value !== null)
            ->reduce(
                fn (Builder $q, mixed $value, string $field) =>
                    method_exists($this, $method = 'where' . Str::studly($field))
                        ? $this->$method($q, $value)
                        : $q,
                $this->query
            );
    }

    private function whereStatus(Builder $q, mixed $value): Builder
    {
        return $q->where('status', $value);
    }
    // ... 10 more methods discovered by name
}

// Problems:
// 1. Method names resolved at runtime via Str::studly
// 2. Behavior depends on array key naming conventions
// 3. IDE cannot help (no static analysis)
// 4. Hard to grep, hard to refactor, hard to debug
```

## Good Example

```php
// ✅ Boring, obvious, greppable
final class OrderFilter
{
    public function apply(Builder $query, OrderFilters $filters): Builder
    {
        return $query
            ->when($filters->status, fn ($q, $status) => $q->where('status', $status))
            ->when($filters->customerId, fn ($q, $id) => $q->where('customer_id', $id))
            ->when($filters->from, fn ($q, $date) => $q->where('created_at', '>=', $date))
            ->when($filters->to, fn ($q, $date) => $q->where('created_at', '<=', $date));
    }
}

// Benefits:
// 1. Static, IDE-friendly
// 2. Easy to step through in a debugger
// 3. Grep "where" — find every filter
// 4. Adding a new filter is a 1-line `->when()`
// 5. No magic method resolution
```

## Why

1. **Easier debugging**: stack traces point to actual code, not closures.
2. **Better IDE support**: autocomplete, refactor, go-to-definition.
3. **Faster onboarding**: boring code reads like prose.
4. **Lower bug rate**: less dynamic dispatch = less surprise.
5. **Cheaper maintenance**: no need to understand a meta-layer to change behavior.
6. **Easier code review**: reviewers don't have to mentally execute the code.
7. **Reversible**: boring code is easy to make clever, hard to make clever code boring.

## When to Apply

- When about to use `__call`, `__invoke`, or reflection for non-framework reasons.
- When about to dispatch a method by string name.
- When about to use eval, `app()->call`, or container magic for non-DI purposes.
- When about to write a closure-heavy pipeline that needs comments to explain.
- When a more direct, sequential version of the code is equally short.

## When NOT to Apply

Boring code is not "no design":

```php
// ❌ Boring gone wrong — duplicated logic
$total1 = $order->items->sum(fn ($i) => $i->price * $i->quantity);
$total2 = $cart->items->sum(fn ($i) => $i->price * $i->quantity);
// ✅ Boring + DRY
$total = fn ($items) => $items->sum(fn ($i) => $i->price * $i->quantity);
```

Boring means obvious. Duplication is not obvious — it's repetition.
