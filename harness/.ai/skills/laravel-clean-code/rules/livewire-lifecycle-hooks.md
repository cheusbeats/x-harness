---
id: livewire-lifecycle-hooks
title: Use Lifecycle Hooks Correctly
category: livewire-architecture
priority: critical
tags: [livewire, lifecycle, mount, hydrate, dehydrate]
related: [livewire-state-minimal, livewire-component-single-purpose, livewire-form-objects]
---

# Use Lifecycle Hooks Correctly

Use Livewire lifecycle hooks for what they are designed for. `mount()` for one-time setup. `hydrate()` / `dehydrate()` for state round-tripping. `updating*` / `updated*` for reacting to property changes. Do not put business logic in `render()`. Do not abuse `mount()` for per-request work.

## The Hooks (Livewire 4)

| Hook | When | Use for |
|------|------|---------|
| `boot()` | Every request, before `mount()`/`hydrate()` | Service injection, low-level setup |
| `mount()` | Once, on first render | Load initial data, accept params, set defaults |
| `hydrate()` | Every subsequent request | Restore non-serializable state (e.g. typed objects) |
| `booted()` | Every request, after `mount()`/`hydrate()` | Final setup once state is ready |
| `updating*()` | Before property change | Validation, sanitization |
| `updated*()` | After property change | Side effects, dependent updates |
| `render()` | Every request | Build the view |
| `dehydrate()` | Every request, after render | Clean up before state is sent to browser |
| `exception()` | On uncaught error | Custom error handling |

## Bad Example

```php
// ❌ Misuse of hooks

final class OrderForm extends Component
{
    public Order $order;
    public string $reference = '';

    public function mount(Order $order): void
    {
        $this->order = $order;
        // ❌ Heavy work in mount — runs on every page load
        Cache::remember("order-form-{$order->id}", 60, fn () => $this->loadExpensiveData());
    }

    public function updatedReference(): void
    {
        // ❌ API call on every keystroke
        $this->referenceSuggestions = Http::get(
            route('suggestions', ['q' => $this->reference]),
        )->json();
    }

    public function render(): View
    {
        // ❌ Business logic in render
        $stats = Order::where('user_id', auth()->id())->selectRaw('count(*) as total, sum(total) as revenue')->first();
        return view('livewire.order-form', compact('stats'));
    }
}

// Problems:
// 1. Cache::remember() in mount — caches per-component, weird semantics
// 2. API call on every keystroke (no debounce)
// 3. Business logic + DB query in render
// 4. mount() is the wrong place for "every page load" work
```

## Good Example

```blade
{{-- ✅ resources/views/livewire/order-form-page.blade.php — correct use of hooks --}}
<?php
use App\Livewire\Forms\OrderForm;
use App\Models\Order;
use Livewire\Component;
use Livewire\WithPagination;

new class extends Component {
    use WithPagination;

    public OrderForm $form;
    public string $search = '';

    // ✅ mount: one-time setup, accept params
    public function mount(?Order $order = null): void
    {
        $this->form->setOrder($order);
    }

    // ✅ hydrate: restore non-serializable state per request (rare)
    public function hydrate(): void
    {
        // e.g. restore a typed object that doesn't survive serialization
    }

    // ✅ updating*: validate or sanitize BEFORE the change
    public function updatingSearch(): void
    {
        $this->resetPage(); // reset pagination when search changes
    }

    // ✅ updated*: react to the change AFTER (use sparingly)
    public function updatedQuantity(): void
    {
        // trigger a side effect — but prefer #[Computed] for derived data
    }
}
?>

<form wire:submit="save">
    <input type="text" wire:model="form.reference" />
    <input type="search" wire:model="search" placeholder="Search orders…" />

    <button type="submit" wire:loading.attr="disabled">Save</button>
</form>
```

The template is the view — nothing else needed in `render()`.

## For Computed / Derived Data, Use `#[Computed]`

```php
// ✅ Don't store derived data — compute on demand
#[Computed]
public function filteredOrders(): Collection
{
    return Order::query()
        ->when($this->search, fn ($q, $s) => $q->where('reference', 'like', "%$s%"))
        ->get();
}

// No need for updated*() to recalculate — computed properties are recomputed on each render
```

## When to Use Each Hook

- **`mount()`**: accept route params, set initial state, load data once.
- **`boot()`**: low-level setup, service registration (rare).
- **`hydrate()`**: restore typed objects (rare — most state is plain scalars).
- **`updating*()`**: reset pagination, validate, sanitize.
- **`updated*()`**: trigger side effects, but prefer `#[Computed]` for derived data.
- **`render()`**: return the view — that's it.
- **`dehydrate()`**: cleanup before state is serialized (rare).

## Common Mistakes

```php
// ❌ Heavy work in mount
public function mount(): void
{
    $this->loadEverything(); // slow on every page load
}

// ✅ Heavy work in render (or computed)
public function render(): View
{
    return view('livewire.x', ['data' => $this->loadExpensive()]);
}
```

```php
// ❌ API call in updated* without debounce
public function updatedSearch(): void
{
    $this->results = Http::get("...?q={$this->search}")->json();
}

// ✅ Debounce in Blade + computed property
// <input wire:model="search" /> — Livewire 4 debounces wire:model by default
#[Computed]
public function results(): array
{
    return $this->search
        ? Http::get("...?q={$this->search}")->json()
        : [];
}
```

```php
// ❌ Logic in render
public function render(): View
{
    $this->doStuff();
    return view('livewire.x');
}

// ✅ Logic in computed
#[Computed]
public function data(): array
{
    // do stuff
    return $data;
}
```

## When to Apply

- Every Livewire component.
- Every `mount()` method.
- Every `render()` method.
- Every `updated*` handler.

## Why

1. **Performance**: hooks have specific costs — use them correctly.
2. **Predictability**: hook order is defined; relying on it is safe.
3. **Testability**: hooks are testable in isolation.
4. **Laravel/Livewire-aligned**: framework convention.
5. **Less state**: computed properties reduce need for `updated*`.
6. **Faster re-renders**: no work in `render()` beyond view building.
7. **Cleaner code**: each hook has one job.
