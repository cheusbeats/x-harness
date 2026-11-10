---
id: livewire-component-single-purpose
title: One Component, One Concern
category: livewire-architecture
priority: critical
tags: [livewire, component, single-responsibility, srp]
related: [laravel-controller-thin, solid-srp, livewire-state-minimal, livewire-form-objects]
---

# One Component, One Concern

A Livewire component must have one clear concern. If a component's name needs "And" in it (e.g. `OrderFormAndList`), split it. A component that handles 3 unrelated UI states (form, list, modal) should be 3 components. Reuse via `<livewire:...>` nesting, not by stuffing everything in one class.

## Bad Example

```php
// ❌ One component does form, list, modal, filters
final class OrderManager extends Component
{
    use WithPagination;

    public string $search = '';
    public string $status = '';
    public string $name = '';
    public string $email = '';
    public ?int $editingId = null;
    public bool $showDeleteModal = false;
    public array $selectedOrders = [];

    public function mount(): void { /* ... */ }
    public function createOrder(): void { /* ... */ }
    public function updateOrder(): void { /* ... */ }
    public function deleteOrder(): void { /* ... */ }
    public function bulkDelete(): void { /* ... */ }
    public function export(): void { /* ... */ }
    public function updatedSearch(): void { /* ... */ }
    public function updatedStatus(): void { /* ... */ }
    public function openDeleteModal(int $id): void { /* ... */ }
    public function closeDeleteModal(): void { /* ... */ }
    public function render(): View { /* 30 lines of query building */ }
}

// Problems:
// 1. 13 public properties, 11 public methods
// 2. 3 unrelated concerns (form, list, bulk actions)
// 3. State of one concern affects others (e.g. validation in form breaks list)
// 4. Test must set up all 13 properties even for one behavior
// 5. Reviewer must understand the whole thing to review any change
// 6. Any property change re-renders the whole component
```

## Good Example (Livewire 4 — SFC format, the default)

In Livewire 4 the default component format is SFC (Single File Component): one Blade file in `resources/views/livewire/` that holds the PHP class (`new class extends Component`) and the template together.

```blade
{{-- ✅ 1. SFC — resources/views/livewire/order-list.blade.php --}}
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
            ->with('customer')
            ->when($this->search, fn ($q, $s) => $q->where('reference', 'like', "%{$s}%"))
            ->when($this->status, fn ($q, $s) => $q->where('status', $s))
            ->latest()
            ->paginate(20);
    }
}
?>

<div>
    <input type="text" wire:model="search" placeholder="Search reference..." />

    <select wire:model="status">
        <option value="">All statuses</option>
        <option value="active">Active</option>
        <option value="cancelled">Cancelled</option>
    </select>

    @foreach ($this->orders as $order)
        <div wire:key="order-{{ $order->id }}">
            {{ $order->reference }} — {{ $order->customer->name }}
        </div>
    @endforeach

    {{ $this->orders->links() }}
</div>
```

```blade
{{-- ✅ 2. SFC — resources/views/livewire/order-form.blade.php --}}
<?php
use App\Models\Order;
use Livewire\Attributes\Validate;
use Livewire\Component;

new class extends Component {
    #[Validate('required|string|max:32')]
    public string $reference = '';

    #[Validate('required|email')]
    public string $customer_email = '';

    #[Validate('required|integer|min:1')]
    public int $quantity = 1;

    public function save(): void
    {
        $this->validate();

        $order = Order::create($this->only(['reference', 'customer_email', 'quantity']));

        $this->dispatch('order-saved', orderId: $order->id);
        $this->reset();
    }
}
?>

<div>
    <form wire:submit="save">
        <input type="text" wire:model="reference" />
        @error('reference') <span>{{ $message }}</span> @enderror

        <input type="email" wire:model="customer_email" />
        @error('customer_email') <span>{{ $message }}</span> @enderror

        <input type="number" wire:model="quantity" min="1" />

        <button type="submit">Save</button>
    </form>
</div>
```

```blade
{{-- ✅ 3. SFC — resources/views/livewire/confirm-delete.blade.php --}}
<?php
use App\Models\Order;
use Livewire\Attributes\On;
use Livewire\Component;

new class extends Component {
    public bool $show = false;
    public ?int $orderId = null;

    #[On('request-delete')]
    public function open(int $orderId): void
    {
        $this->orderId = $orderId;
        $this->show = true;
    }

    public function confirm(): void
    {
        Order::find($this->orderId)?->delete();
        $this->dispatch('order-deleted');
        $this->show = false;
    }
}
?>

<div>
    @if ($show)
        <div role="alertdialog">
            <p>Delete order #{{ $orderId }}?</p>
            <button type="button" wire:click="confirm">Delete</button>
            <button type="button" wire:click="$set('show', false)">Cancel</button>
        </div>
    @endif
</div>
```

```blade
{{-- Usage in a parent view — component tags MUST be closed in Livewire 4 --}}
<div>
    <livewire:order-list />
    <livewire:order-form />
    <livewire:confirm-delete />
</div>
```

### Full-Page Components (Livewire 4)

```php
// ✅ Livewire 4 full-page routing — no controller needed

// SFC / view-based components are referenced by name:
Route::livewire('/orders', 'order-list')->name('orders.index');

// MFC / class-based components are referenced by class:
Route::livewire('/orders/create', OrderForm::class)
    ->middleware('auth')
    ->name('orders.create');
```

## Component Formats (Livewire 4)

Livewire 4 supports four formats. Before creating a component, check existing files and match the established convention (per `core-respect-existing`). Convert between formats with `php artisan livewire:convert <name>`:

| Format | Files | Create command | When |
|--------|-------|----------------|------|
| SFC (default) | `resources/views/livewire/foo.blade.php` (PHP class + template) | `php artisan make:livewire foo` | New components |
| MFC | `app/Livewire/Foo.php` + `resources/views/livewire/foo.blade.php` | `php artisan make:livewire foo --mfc` | Large templates, teams that separate concerns |
| Class-based | `app/Livewire/Foo.php` with `render()` returning a view | `php artisan make:livewire foo --class` | v3-style / explicit separation |
| View-based | `resources/views/livewire/foo.blade.php` (Blade-only, functional state) | manual | Trivial static-ish components |

The single-purpose rule applies to every format: SFC or not, one component = one concern.

## When to Split

A component is too big when:

- The name needs "And" or "Manager" or "Hub".
- Public properties serve unrelated concerns.
- `render()` has multiple queries for different things.
- Methods are unrelated to each other.
- One concern's state is affected by another (e.g. form's `$editingId` affects list's filters).

## Component Naming

```php
// ✅ Focused
OrderList, OrderForm, ConfirmDelete, ProductSearch, CartSummary

// ❌ God component
OrderManager, OrderPage, OrderDashboard, OrderHub
```

## When to Apply

- A component has more than 5 public properties serving different concerns.
- A component has more than 3 public action methods (`save`, `update`, `delete`, etc.).
- The component is hard to name without "Manager" / "And" / "Hub".

## Why

1. **Testability**: each component is testable in isolation.
2. **State isolation**: form validation does not break the list.
3. **Re-render efficiency**: only the affected component re-renders.
4. **Reusability**: small components are reused across pages.
5. **Readability**: each component is a 1-page file.
6. **Laravel-aligned**: Livewire is designed for small components.
7. **Livewire 4 alignment**: islands, partial re-renders, and `defer`/`lazy` loading all work best with small, focused components.
