---
id: laravel-eloquent-scopes
title: Reuse Query Logic via Scopes
category: laravel-architecture
priority: critical
tags: [eloquent, scopes, query, dry]
related: [core-dry, laravel-eloquent-n-plus-one, core-respect-existing]
---

# Reuse Query Logic via Scopes

Repeated Eloquent query logic should live in a local or global scope on the model. Do not duplicate `where('status', 'active')` across controllers. Scopes make the query readable, testable, and reusable, and they keep the controller thin.

## Bad Example

```php
// ❌ Same query logic in 3 controllers
final class OrderController extends Controller
{
    public function index(): View
    {
        $orders = Order::where('status', 'active')
            ->where('total', '>', 0)
            ->whereHas('customer', fn ($q) => $q->where('blocked', false))
            ->paginate(20);
        return view('orders.index', compact('orders'));
    }
}

final class ReportController extends Controller
{
    public function active(): View
    {
        $orders = Order::where('status', 'active')
            ->where('total', '>', 0)
            ->whereHas('customer', fn ($q) => $q->where('blocked', false))
            ->get();
        return view('reports.active', compact('orders'));
    }
}

final class DashboardController extends Controller
{
    public function stats(): array
    {
        $count = Order::where('status', 'active')
            ->where('total', '>', 0)
            ->whereHas('customer', fn ($q) => $q->where('blocked', false))
            ->count();
        return ['active_orders' => $count];
    }
}

// Problems:
// 1. Same 3-line query in 3 places
// 2. "Active" has 3 conditions; easy to forget one
// 3. To change the rule, edit 3 files
// 4. The query is the actual domain rule
```

## Good Example

```php
// ✅ Local scopes on the model
final class Order extends Model
{
    public function scopeActive(Builder $query): Builder
    {
        return $query
            ->where('status', OrderStatus::Active)
            ->where('total', '>', 0)
            ->whereHas('customer', fn ($q) => $q->where('blocked', false));
    }

    public function scopeForCustomer(Builder $query, User $customer): Builder
    {
        return $query->where('customer_id', $customer->id);
    }
}

// Usage in controllers — readable and DRY
final class OrderController extends Controller
{
    public function index(): View
    {
        $orders = Order::active()->latest()->paginate(20);
        return view('orders.index', compact('orders'));
    }
}

final class ReportController extends Controller
{
    public function active(): View
    {
        $orders = Order::active()->get();
        return view('reports.active', compact('orders'));
    }
}

final class DashboardController extends Controller
{
    public function stats(): array
    {
        return ['active_orders' => Order::active()->count()];
    }
}

// Benefits:
// 1. "Active" rule lives in one place
// 2. Order::active() reads like prose
// 3. To change the rule, edit one file
// 4. Testable: test the scope in isolation
// 5. Composable: Order::active()->forCustomer($user)
```

## Local vs Global Scopes

```php
// ✅ Local scope — opt-in
public function scopeActive(Builder $query): Builder
{
    return $query->where('status', OrderStatus::Active);
}
// Use: Order::active()->get();

// ⚠️ Global scope — applies to ALL queries on the model
// Use sparingly: only for genuinely universal rules
protected static function booted(): void
{
    static::addGlobalScope(new TenantScope);
}
// Use: Order::all() — already scoped to current tenant
```

## When to Use Scopes

- The same WHERE clause appears in 3+ places.
- The query encodes a domain concept (active, paid, expired, visible).
- A query needs to be unit-testable in isolation.
- You want to chain query logic: `Order::active()->paid()->forCustomer($u)`.

## When NOT to Use Scopes

```php
// ❌ Scope for a one-off query
public function scopeCreatedInLastWeek(Builder $query): Builder
{
    return $query->where('created_at', '>=', now()->subWeek());
}

// ✅ Inline if used once
$orders = Order::where('created_at', '>=', now()->subWeek())->get();
```

## Scope Conventions

| Pattern | Purpose |
|---------|---------|
| `scopeActive` | Boolean-style filter |
| `scopeForUser($user)` | Parameterized scope |
| `scopeWithRelations` | Default eager load (e.g. always load `customer`) |
| `scopeOrderBy` | Sort helper |
| `scopeVisibleTo($user)` | Auth-aware scope |

## Why

1. **DRY for queries**: one definition, many call sites.
2. **Readable**: `Order::active()->paid()` reads like English.
3. **Testable**: test scopes in isolation, no controller needed.
4. **Composable**: chain scopes like the query builder.
5. **Eager-loadable**: `with()` chains in scopes.
6. **Laravel-idiomatic**: framework feature, expected by the team.
7. **Refactor-friendly**: change one scope, all callers updated.
