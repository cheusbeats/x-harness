---
id: core-no-speculative-compat
title: No Speculative Compatibility
category: core-principles
priority: critical
tags: [compatibility, deprecation, yagni]
related: [core-yagni, core-minimize-change, core-stay-in-scope]
---

# No Speculative Compatibility

Do not preserve backward compatibility with hypothetical consumers. Backward compatibility is required only when existing consumers depend on it, public API contracts require it, or the user explicitly requests it. Do not retain obsolete behavior "just in case". Do not create migration or compatibility layers without evidence they are required.

## Bad Example

```php
// ❌ Renamed method, kept old one "for safety"
final class OrderService
{
    public function create(array $data): Order
    {
        return $this->createOrder($data); // delegates to new method
    }

    public function createOrder(array $data): Order
    {
        return Order::create($data);
    }

    public function makeOrder(array $data): Order // old name, kept "just in case"
    {
        return $this->createOrder($data);
    }
}

// Problems:
// 1. Three methods for one operation
// 2. No caller uses `makeOrder` (checked via grep)
// 3. Future readers waste time wondering which one to call
// 4. The "compat shim" itself becomes a maintenance burden
```

## Good Example

```php
// ✅ Just rename, delete the old
final class OrderService
{
    public function create(array $data): Order
    {
        return Order::create($data);
    }
}

// If a consumer really depends on the old name:
// 1. Update the consumer
// 2. Delete the old method
// 3. Add a one-line note in CHANGELOG

// Benefits:
// 1. One method, one name, one behavior
// 2. Grep `->makeOrder(` returns 0 — no orphan callers
// 3. Future readers see the current API
// 4. No dead code paths
```

## Why

1. **Dead code is a tax**: every line costs reading time, every method adds surface.
2. **False safety**: keeping the old name doesn't actually help if no one uses it.
3. **Hides the truth**: readers don't know which method is the "real" one.
4. **Tests cover the unused**: tests for `makeOrder` are wasted effort.
5. **Migration guides > compat shims**: a deprecation note is cheaper than dual API.
6. **YAGNI alignment**: don't build for hypothetical consumers.
7. **Refactor friction**: compat shims prevent clean refactors.

## When to Apply

- After renaming a method, class, or column.
- After changing a public API.
- After replacing an implementation.
- After a dependency upgrade.
- When tempted to "keep both for now".

## When NOT to Apply

Backward compatibility is required when:

```php
// ✅ Real consumer: a published Composer package
// ✅ Public API endpoint with documented contract
// ✅ Method called from a queue job that may be in-flight during deploy
// ✅ Library code with semantic versioning
```

The check: **does anything actually call this today?** Use `Grep` to verify. If yes, keep compat for one release. If no, delete.

## How to Verify

Before keeping a compat shim:

1. `Grep` the project for the old name.
2. Check if it's used by a public API contract.
3. Check if any in-flight job/queue could be using it.
4. If 3 are all "no" — delete it.
