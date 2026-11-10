---
id: livewire-events-communication
title: Component Communication via Events
category: livewire-architecture
priority: critical
tags: [livewire, events, dispatch, listen, communication]
related: [livewire-component-single-purpose, laravel-events, livewire-state-minimal]
---

# Component Communication via Events

Components communicate via `dispatch()` and `#[On(...)]` listeners. Do not pass data between components via parent props unless the child truly is a "dumb" view. Use events for cross-component actions (refresh, save, delete), and use Alpine.js for purely client-side UI state.

## Bad Example

```php
// ❌ Parent owns all state, children just dispatch to it
final class OrderPage extends Component
{
    public array $cartItems = [];
    public array $shippingOptions = [];
    public array $paymentMethods = [];
    public string $couponCode = '';
    public string $notes = '';
    public int $currentStep = 1;
    public bool $showConfirmModal = false;
    public array $selectedItems = [];

    // 8 public properties for 3 child components
    // Each child action = a method on the parent
    public function addToCart(int $productId): void { /* ... */ }
    public function removeFromCart(int $itemId): void { /* ... */ }
    public function applyCoupon(): void { /* ... */ }
    public function nextStep(): void { /* ... */ }
    public function previousStep(): void { /* ... */ }
    public function showConfirm(): void { /* ... */ }
    public function confirmOrder(): void { /* ... */ }
}
```

## Good Example

```blade
{{-- ✅ resources/views/livewire/cart-item.blade.php — 1. child component, dispatches actions --}}
<?php
use App\Models\CartLine;
use Livewire\Component;

new class extends Component {
    public CartLine $line;

    public function remove(): void
    {
        $this->line->delete();
        $this->dispatch('cart-updated');
    }
}
?>

<div>
    <span>Line #{{ $line->id }} — qty {{ $line->quantity }}</span>
    <button type="button" wire:click="remove">Remove</button>
</div>
```

```blade
{{-- ✅ resources/views/livewire/cart-summary.blade.php — 2. listens to events, recomputes --}}
<?php
use App\Models\CartLine;
use Livewire\Attributes\Computed;
use Livewire\Attributes\On;
use Livewire\Component;

new class extends Component {
    public int $cartId;

    #[On('cart-updated')]
    #[On('coupon-applied')]
    public function refresh(): void
    {
        unset($this->total); // clear the cached computed value
    }

    #[Computed]
    public function total(): int
    {
        return CartLine::where('cart_id', $this->cartId)->sum('subtotal');
    }
}
?>

<p>Total: {{ $this->total }}</p>
```

```blade
{{-- ✅ resources/views/livewire/coupon-input.blade.php — 3. dispatches when applied --}}
<?php
use App\Models\Coupon;
use Livewire\Component;

new class extends Component {
    public string $code = '';

    public function apply(): void
    {
        $coupon = Coupon::where('code', $this->code)->first();

        if (! $coupon) {
            $this->addError('code', 'Invalid coupon.');
            return;
        }

        $this->dispatch('coupon-applied', couponId: $coupon->id);
        $this->reset('code');
    }
}
?>

<div>
    <input type="text" wire:model="code" />
    @error('code') <span>{{ $message }}</span> @enderror
    <button type="button" wire:click="apply">Apply</button>
</div>
```

```blade
{{-- ✅ resources/views/livewire/cart-page.blade.php — 4. parent just composes children, no business logic --}}
<?php
use App\Models\CartLine;
use Illuminate\Support\Collection;
use Livewire\Attributes\Computed;
use Livewire\Component;

new class extends Component {
    public int $cartId;

    #[Computed]
    public function lines(): Collection
    {
        return CartLine::where('cart_id', $this->cartId)->get();
    }
}
?>

<div>
    @foreach ($this->lines as $line)
        <livewire:cart-item :line="$line" wire:key="line-{{ $line->id }}" />
    @endforeach

    <livewire:coupon-input />
    <livewire:cart-summary :cart-id="$cartId" />

    <button type="button" wire:click="$dispatch('checkout')">Checkout</button>
</div>
```

Note the v4 convention: component tags are always closed (`<livewire:coupon-input />`).

## Event Patterns

```php
// Dispatch from component
$this->dispatch('order-saved', orderId: $order->id);
$this->dispatch('order-saved', orderId: $order->id)->to(OrderList::class); // to a specific component
$this->dispatch('order-saved')->self(); // to self

// Listen
use Livewire\Attributes\On;

#[On('order-saved')]
public function refreshList(int $orderId): void
{
    // ...
}
```

```blade
{{-- Listen from Alpine/JS inside a template --}}
<div x-data x-init="$wire.on('order-saved', ({ orderId }) => { /* ... */ })"></div>
```

## When to Use Events vs Props

| Need | Use |
|------|-----|
| Child needs data from parent | Props (`:cart-id="$cartId"`) |
| Child notifies parent of action | Event (`$this->dispatch('cart-updated')`) |
| Sibling components need to coordinate | Event bus |
| Form submission result needs to refresh another component | Event |
| Pure client-side UI (open/close modal) | Alpine.js (no Livewire roundtrip) |

## Avoid Polling Where Possible

```php
// ❌ Polling for state changes
public function poll(): void
{
    $this->refreshData();
}

// <livewire:order-list wire:poll.5s />

// ✅ Event-driven — only refresh when something happens
#[On('order-saved')]
public function refresh(): void
{
    // recompute
}
```

## When to Apply

- Two sibling components need to react to the same event.
- A child component needs to notify its parent of an action.
- A form submission should refresh a list in another component.
- Multiple components show the same data and need to stay in sync.

## Why

1. **Decoupled**: children don't know about each other.
2. **Testable**: each component is testable with synthetic events.
3. **Performant**: no polling, no re-render storms.
4. **Laravel-aligned**: events/listeners pattern.
5. **Livewire 4 feature**: `dispatch`, `#[On]`, `$wire.on()` are first-class.
6. **Reusable**: the same child works in any parent.
7. **Predictable**: event names are the contract.
