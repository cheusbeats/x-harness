---
id: laravel-eloquent-n-plus-one
title: Avoid N+1 with Eager Loading
category: laravel-architecture
priority: critical
tags: [eloquent, n+1, eager-loading, performance]
related: [laravel-eloquent-scopes, laravel-resource, laravel-blade-no-php]
---

# Avoid N+1 with Eager Loading

Every relation accessed in a loop without eager loading is an N+1 query. Use `with()`, `load()`, `withCount()` to load relations up front. Use `preventLazyLoading()` in non-production environments to catch every N+1 in dev.

## Bad Example

```php
// ❌ N+1 — 1 query for orders, N queries for customers
final class OrderController extends Controller
{
    public function index(): View
    {
        $orders = Order::all(); // 1 query
        return view('orders.index', compact('orders'));
    }
}
```

```blade
{{-- resources/views/orders/index.blade.php --}}
@foreach ($orders as $order)
    <tr>
        <td>{{ $order->id }}</td>
        <td>{{ $order->customer->name }}</td>  {{-- N+1: 1 query per order --}}
        <td>{{ $order->items->count() }}</td>  {{-- N+1: 1 query per order --}}
    </tr>
@endforeach
```

```php
// Total queries for 100 orders: 1 + 100 + 100 = 201 queries
```

## Good Example

```php
// ✅ Eager load relations up front
final class OrderController extends Controller
{
    public function index(): View
    {
        $orders = Order::query()
            ->with(['customer', 'items'])  // 1 extra query each
            ->withCount('items')           // 1 subquery, no extra query per order
            ->latest()
            ->paginate(20);

        return view('orders.index', compact('orders'));
    }
}
```

```blade
{{-- Blade is unchanged — but no N+1 happens --}}
@foreach ($orders as $order)
    <tr>
        <td>{{ $order->id }}</td>
        <td>{{ $order->customer->name }}</td>  {{-- already loaded --}}
        <td>{{ $order->items_count }}</td>     {{-- already counted --}}
    </tr>
@endforeach
```

```php
// Total queries for 100 orders: 1 + 1 + 1 + 1 = 4 queries
```

## Enable preventLazyLoading in Dev

```php
// app/Providers/AppServiceProvider.php
public function boot(): void
{
    if (! app()->isProduction()) {
        Model::preventLazyLoading(); // throws on any lazy load in dev/test
        Model::preventSilentlyDiscardingAttributes(true);
    }
}

// Result: every N+1 in dev becomes an exception → fixed before merge
```

## Common N+1 Sources

```php
// ❌ Accessing a relation in the loop
@foreach ($orders as $order)
    {{ $order->customer->name }}        // N+1
    {{ $order->items->sum('total') }}   // N+1
    {{ $order->shippingAddress?->city }} // N+1
    {{ $order->tags->pluck('name')->join(', ') }} // N+1
@endforeach

// ❌ Counting in the loop
@foreach ($orders as $order)
    {{ $order->items()->count() }}      // N+1
    {{ $order->comments()->count() }}   // N+1
@endforeach

// ❌ Accessing nested relations
@foreach ($orders as $order)
    @foreach ($order->items as $item)
        {{ $item->product->name }}      // N+1 even if items was eager-loaded
    @endforeach
@endforeach
```

## Solutions

```php
// 1. Eager load nested
$orders = Order::with(['items.product', 'customer'])->get();

// 2. Count via subquery (no extra query per order)
$orders = Order::withCount('items')->get();
// Use: $order->items_count

// 3. Select only what you need
$orders = Order::with(['customer:id,name'])->get();

// 4. Use lazy eager loading if the relation is needed conditionally
$orders = Order::all();
if ($needDetails) {
    $orders->load('items.product');
}
```

## When to Apply

- Every controller method that returns a list with relations.
- Every Resource collection that accesses a relation.
- Every Blade view that loops and reads a relation.
- Every `pluck`, `count`, or `exists` on a relation in a loop.

## How to Detect

```php
// 1. DB::listen in dev
DB::listen(fn ($query) => logger($query->sql, $query->bindings));

// 2. Laravel Telescope / Debugbar — show query count per request

// 3. preventLazyLoading() — turn it on in dev, every N+1 throws
Model::preventLazyLoading(! app()->isProduction());
```

## Why

1. **Performance**: 201 queries → 4 queries for the same data.
2. **Predictable latency**: independent of result count.
3. **Database load**: 50x fewer round-trips.
4. **Dev-time safety**: `preventLazyLoading()` catches N+1 in CI.
5. **Cheap fix**: adding `with()` is a 1-line change.
6. **Laravel-aligned**: eager loading is the framework's intended pattern.
7. **Detectable**: Telescope / Debugbar make N+1 obvious.
