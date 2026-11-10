---
id: livewire-no-direct-queries
title: No DB Queries Outside render() and Methods
category: livewire-architecture
priority: critical
tags: [livewire, queries, performance, debounce]
related: [livewire-queries-with-eloquent, livewire-state-minimal, livewire-form-objects]
---

# No DB Queries Outside render() and Methods

Do not call `Model::` queries from Blade templates. Every `{{ $order->relation }}` or `@foreach (Model::all() as $x)` in a Blade view is a query that fires on every re-render. Use `render()` or `#[Computed]` properties to load data, and pass it to the view as a variable.

## Bad Example

```blade
{{-- ❌ Query in Blade --}}
@foreach (Order::where('status', 'active')->get() as $order)
    <p>{{ $order->reference }}</p>
@endforeach

{{-- ❌ Count in Blade --}}
<p>{{ Order::count() }} total orders</p>

{{-- ❌ Relation access in Blade (N+1) --}}
@foreach ($orders as $order)
    <p>{{ $order->customer->name }}</p> {{-- query per order --}}
@endforeach

{{-- ❌ Query in @php (forbidden by laravel-blade-no-php anyway) --}}
@php
    $related = Product::where('category_id', $product->category_id)->get();
@endphp
```

## Good Example

```blade
{{-- ✅ resources/views/livewire/order-list.blade.php — data loads in #[Computed], template only renders --}}
<?php
use App\Enums\OrderStatus;
use App\Models\Order;
use Illuminate\Database\Eloquent\Collection;
use Livewire\Attributes\Computed;
use Livewire\Component;

new class extends Component {
    #[Computed]
    public function orders(): Collection
    {
        return Order::query()
            ->with('customer')                  // eager load
            ->withCount('items')                // no extra query
            ->where('status', OrderStatus::Active)
            ->latest()
            ->get();
    }

    #[Computed]
    public function totalCount(): int
    {
        return Order::count();
    }
}
?>

<div>
    @foreach ($this->orders as $order)
        <p wire:key="order-{{ $order->id }}">
            {{ $order->customer->name }} -- {{ $order->reference }}
        </p>
    @endforeach

    <p>Total: {{ $this->totalCount }}</p>
</div>
```

## Common Patterns to Avoid in Blade

| Pattern | Why it's bad | Fix |
|---------|--------------|-----|
| `Model::all()` in Blade | Query on every render | `#[Computed] orders()` |
| `$model->relation` in loop | N+1 | `->with('relation')` |
| `Model::count()` in Blade | Query on every render | `#[Computed] count()` |
| `Model::where(...)->get()` in Blade | Same as above | `#[Computed]` |
| `Model::find($id)->prop` in Blade | Query + relation | `#[Computed] model(int $id)` |

## Debounce Expensive Updates

```blade
{{-- Livewire 4: plain wire:model is debounced by default — one request per pause, not per keystroke --}}
<input type="text" wire:model="search" />

{{-- .live = network update on every keystroke --}}
<input type="text" wire:model.live="name" />

{{-- .live with an explicit debounce window --}}
<input type="text" wire:model.live.debounce.300ms="query" />
```

```php
// ✅ Protect server-side state from client tampering
#[\Livewire\Attributes\Locked]
public array $cache = [];
```

## Use `wire:key` to Avoid Re-renders

```blade
{{-- ✅ wire:key tells Livewire which DOM elements are stable --}}
@foreach ($this->orders as $order)
    <tr wire:key="order-{{ $order->id }}">
        ...
    </tr>
@endforeach
```

## When to Apply

- Every Blade view rendered by Livewire.
- Every `@foreach` in a Livewire view.
- Every `Model::` call in any template.
- Every re-render that's slow.

## Why

1. **Performance**: queries in Blade = queries on every keystroke.
2. **N+1**: hidden in templates, hard to find.
3. **Testability**: queries in `render()` are easy to test.
4. **Eager loading**: preloaded in `render()`, used in Blade.
5. **Debuggability**: stack trace points to a method, not a view.
6. **Laravel-aligned**: MVC — controller/component loads, view renders.
7. **Livewire 4 alignment**: `#[Computed]` is the recommended pattern.
