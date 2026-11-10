---
id: livewire-state-minimal
title: Minimal State, No Derived Data
category: livewire-architecture
priority: critical
tags: [livewire, state, properties, derived-data, computeds]
related: [livewire-component-single-purpose, livewire-form-objects, laravel-eloquent-n-plus-one]
---

# Minimal State, No Derived Data

Livewire public properties are the component's state — they are sent to the browser and back on every request. Keep them minimal. Do not store derived or computed data; compute it in `render()` or a `computed` property. Every extra public property is extra network payload and extra surface for bugs.

## Bad Example

```php
// ❌ Public state for everything
final class OrderList extends Component
{
    use WithPagination;

    public string $search = '';
    public string $status = '';
    public string $dateFrom = '';
    public string $dateTo = '';
    public array $selectedIds = [];
    public int $totalCount = 0;
    public float $totalRevenue = 0;
    public int $activeOrders = 0;
    public ?float $averageOrderValue = null;

    public function mount(): void
    {
        $this->recalculate();
    }

    public function updatedSearch(): void
    {
        $this->recalculate();
    }

    public function updatedStatus(): void
    {
        $this->recalculate();
    }

    private function recalculate(): void
    {
        $this->totalCount = Order::count();
        $this->totalRevenue = Order::sum('total');
        $this->activeOrders = Order::where('status', 'active')->count();
        $this->averageOrderValue = Order::avg('total');
    }

    // 4 properties are derived from the DB, sent to the browser on every request
    // 4 properties are re-saved on every update
    // All 4 can be computed in render() instead
}
```

## Good Example (Livewire 4 — SFC)

```blade
{{-- ✅ resources/views/livewire/order-list.blade.php — minimal state + #[Computed] --}}
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
    public string $dateFrom = '';
    public string $dateTo = '';

    // ✅ Computed property — cached during the request, not stored as state
    #[Computed]
    public function stats(): array
    {
        return [
            'total' => Order::count(),
            'revenue' => Order::sum('total'),
            'active' => Order::where('status', 'active')->count(),
        ];
    }

    #[Computed]
    public function orders(): Paginator
    {
        return Order::query()
            ->when($this->search, fn ($q, $s) => $q->where('reference', 'like', "%{$s}%"))
            ->when($this->status, fn ($q, $s) => $q->where('status', $s))
            ->when($this->dateFrom, fn ($q, $d) => $q->where('created_at', '>=', $d))
            ->when($this->dateTo, fn ($q, $d) => $q->where('created_at', '<=', $d))
            ->latest()
            ->paginate(20);
    }
}
?>

<div>
    {{-- Livewire 4: plain wire:model is debounced by default; .live = instant --}}
    <input type="text" wire:model="search" />
    <select wire:model="status">...</select>

    <p>Total orders: {{ $this->stats['total'] }}</p>
    <p>Revenue: {{ $this->stats['revenue'] }}</p>

    @foreach ($this->orders as $order)
        <p wire:key="order-{{ $order->id }}">{{ $order->reference }}</p>
    @endforeach

    {{ $this->orders->links() }}
</div>
```

## Computed Properties (Livewire 4)

```php
// ✅ #[Computed] — cached during the request
use Livewire\Attributes\Computed;

#[Computed]
public function orders(): Collection
{
    return Order::query()->active()->get();
}

// Use in Blade as: {{ $this->orders }}

// ✅ With parameter
#[Computed]
public function user(int $id): User
{
    return User::find($id);
}

// Use as: {{ $this->user($id)->name }}
```

## The Rule

- **Public property**: only what the user can change (inputs, selections, toggles).
- **Computed property**: derived data, aggregates, joined queries.
- **Private method**: helpers that don't need to be in state.
- **Model**: business logic, formatting, calculations.

## What Not to Put in Public State

- IDs of items currently being shown (compute from the query).
- Counts, sums, averages (compute).
- Formatted strings (format in the model or Blade).
- Validation errors (Livewire handles these).
- Boolean flags for "is the modal open" only if the modal is a child component.

## When to Apply

- A Livewire component has more than 5 public properties.
- A public property is set by code, not by user input.
- A public property is recalculated on every change.
- Network payload in the browser DevTools is unexpectedly large.

## Why

1. **Network**: every public property is sent to the browser and back.
2. **Re-renders**: every property change triggers a re-render.
3. **Stale state**: a derived property can drift from the source of truth.
4. **Bugs**: state stored in 2 places is a bug waiting to happen.
5. **Testing**: less state = simpler tests.
6. **Performance**: computed properties cache during the request.
7. **Laravel/Livewire-aligned**: framework convention.
