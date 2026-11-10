---
id: livewire-queries-with-eloquent
title: Use Eloquent in Livewire, Avoid N+1
category: livewire-architecture
priority: critical
tags: [livewire, eloquent, n+1, eager-loading, queries]
related: [laravel-eloquent-n-plus-one, laravel-eloquent-scopes, livewire-state-minimal]
---

# Use Eloquent in Livewire, Avoid N+1

Inside Livewire `render()` methods, use Eloquent with eager loading and `withCount()`. Do not run raw SQL. Do not loop over results and access relations. Every `render()` runs many times during a session — N+1 problems are amplified in Livewire.

## Bad Example

```php
// ❌ N+1 hidden in render() — fires on every component update
final class OrderList extends Component
{
    use WithPagination;

    public function render(): View
    {
        $orders = DB::table('orders')
            ->where('status', 'active')
            ->orderBy('created_at', 'desc')
            ->paginate(20);

        // Each $order loads customer/items in the Blade view → N+1
        return view('livewire.order-list', compact('orders'));
    }
}
```

```blade
{{-- resources/views/livewire/order-list.blade.php --}}
@foreach ($orders as $order)
    <tr>
        <td>{{ $order->id }}</td>
        <td>{{ $order->customer->name }}</td>  {{-- N+1: query per order --}}
        <td>{{ $order->items->count() }} items</td>  {{-- N+1 --}}
        <td>{{ $order->shippingAddress?->city }}</td>  {{-- N+1 --}}
    </tr>
@endforeach
```

```blade
{{-- ❌ Counts in the loop --}}
@foreach ($orders as $order)
    {{ $order->comments()->count() }} comments
    {{ $order->attachments()->count() }} files
@endforeach
```

## Good Example (Livewire 4 — SFC)

```blade
{{-- ✅ resources/views/livewire/order-list.blade.php --}}
<?php
use App\Models\Order;
use Illuminate\Contracts\Pagination\Paginator;
use Livewire\Attributes\Computed;
use Livewire\Component;
use Livewire\WithPagination;

new class extends Component {
    use WithPagination;

    public string $search = '';
    public string $status = '';

    #[Computed]
    public function orders(): Paginator
    {
        return Order::query()
            ->with(['customer', 'items', 'shippingAddress']) // 3 eager queries total
            ->withCount(['items', 'comments', 'attachments']) // 0 extra queries
            ->when($this->search, fn ($q, $s) => $q->where('reference', 'like', "%{$s}%"))
            ->when($this->status, fn ($q, $s) => $q->where('status', $s))
            ->latest()
            ->paginate(20);
    }
}
?>

<div>
    <input type="text" wire:model="search" />
    <select wire:model="status">...</select>

    @foreach ($this->orders as $order)
        <tr wire:key="order-{{ $order->id }}">
            <td>{{ $order->id }}</td>
            <td>{{ $order->customer->name }}</td>     {{-- preloaded --}}
            <td>{{ $order->items_count }} items</td>  {{-- subquery, no extra query --}}
            <td>{{ $order->shippingAddress?->city }}</td> {{-- preloaded --}}
            <td>{{ $order->comments_count }} comments</td>
        </tr>
    @endforeach

    {{ $this->orders->links() }}
</div>
```

## Use `wire:key` on Loops

```blade
{{-- ✅ wire:key helps Livewire track DOM elements across re-renders --}}
@foreach ($orders as $order)
    <tr wire:key="order-{{ $order->id }}">
        ...
    </tr>
@endforeach
```

## Use preventLazyLoading in Dev

```php
// app/Providers/AppServiceProvider.php
public function boot(): void
{
    if (! app()->isProduction()) {
        Model::preventLazyLoading();
    }
}

// Result: every lazy load in dev (including Livewire) throws an exception
```

## Use `lazy` / `defer` for Components Below the Fold (Livewire 4)

```php
// ✅ #[Lazy] attribute — rendered after the initial page paint (viewport-based)
use Livewire\Attributes\Lazy;
use Livewire\Component;

#[Lazy]
class HeavyReport extends Component
{
    public function placeholder(): string
    {
        return '<div class="animate-pulse">Loading report…</div>';
    }
}

// ✅ #[Defer] — loads right after the initial page load (not viewport-based)
use Livewire\Attributes\Defer;

#[Defer]
class RevenueChart extends Component
{
    // ...
}
```

```blade
<livewire:heavy-report lazy />              {{-- lazy render with placeholder --}}
<livewire:heavy-report lazy.bundle />       {{-- bundled with other deferred components --}}
<livewire:revenue-chart defer />            {{-- deferred until after initial render --}}
```

Server-side equivalents: `#[Lazy(bundle: true)]` and `#[Defer]` on the class instead of attributes in the parent template.

## When to Apply

- Every Livewire `render()` method.
- Every Blade view that loops over Eloquent results.
- Every Livewire action that returns data.
- Every time `wire:model` triggers a re-render.

## Why

1. **Livewire re-renders are frequent** — N+1 hits 10x more than in classic controllers.
2. **User experience** — fast list = happy user.
3. **Server load** — 200 orders × 3 relations = 600 queries vs 4.
4. **Real-time feel** — debounced re-renders stay fast.
5. **Dev safety** — `preventLazyLoading()` catches N+1 in tests.
6. **Laravel-aligned** — eager loading is the framework's intended pattern.
7. **Livewire 4 alignment** — partial re-renders rely on small query sets.
