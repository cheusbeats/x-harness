---
id: laravel-blade-no-php
title: No @php Directives in Blade
category: laravel-architecture
priority: critical
tags: [blade, php, view, separation, anti-pattern]
related: [laravel-controller-thin, laravel-resource, laravel-policies, core-kiss]
---

# No `@php` Directives in Blade

**Mandatory rule.** Blade templates must not contain `@php ... @endphp` directives. Logic in a view belongs in a controller, a View Composer, a Blade Component, a helper, or an Eloquent accessor — never inline as PHP. `@php` is an escape hatch that breaks the separation of concerns, makes views untestable, and turns Blade into a procedural mess.

## Bad Example

```blade
{{-- ❌ @php used for view-side calculations --}}
@php
    $total = 0;
    foreach ($order->items as $item) {
        $total += $item->price * $item->quantity;
    }
    $discount = $total > 1000 ? $total * 0.1 : 0;
    $final = $total - $discount;
@endphp

<div>
    Subtotal: {{ $total }}<br>
    Discount: {{ $discount }}<br>
    Total: {{ $final }}
</div>
```

```blade
{{-- ❌ @php for conditionals --}}
@php
    $canEdit = auth()->user()->can('update', $order) && $order->status === 'pending';
@endphp

@if ($canEdit)
    <a href="{{ route('orders.edit', $order) }}">Edit</a>
@endif
```

```blade
{{-- ❌ @php for "one-off" data shaping --}}
@php
    $formattedDate = \Carbon\Carbon::parse($order->created_at)->format('d.m.Y H:i');
@endphp

<p>{{ $formattedDate }}</p>
```

```php
// Problems:
// 1. View has business logic (discount calculation, auth check, date formatting)
// 2. Logic is not testable without rendering a view
// 3. The same logic is duplicated across views
// 4. Blade becomes a procedural script
// 5. Reviewers must mentally execute PHP to verify the view
// 6. @php blocks can hide serious bugs (typos, division by zero, etc.)
```

## Good Example

```blade
{{-- ✅ Logic in the model --}}
@foreach ($order->items as $item)
    <tr>
        <td>{{ $item->name }}</td>
        <td>{{ $item->quantity }}</td>
        <td>{{ $item->formatted_subtotal }}</td>
    </tr>
@endforeach

<tr>
    <td colspan="2">Subtotal:</td>
    <td>{{ $order->formatted_subtotal }}</td>
</tr>
<tr>
    <td colspan="2">Discount:</td>
    <td>{{ $order->formatted_discount }}</td>
</tr>
<tr>
    <td colspan="2"><strong>Total:</strong></td>
    <td><strong>{{ $order->formatted_total }}</strong></td>
</tr>
```

```php
// app/Models/Order.php
final class Order extends Model
{
    public function getSubtotalAttribute(): int
    {
        return $this->items->sum(fn (OrderItem $i) => $i->price * $i->quantity);
    }

    public function getDiscountAttribute(): int
    {
        return $this->subtotal > 1000 ? (int) ($this->subtotal * 0.1) : 0;
    }

    public function getTotalAttribute(): int
    {
        return $this->subtotal - $this->discount;
    }

    public function getFormattedSubtotalAttribute(): string
    {
        return number_format($this->subtotal / 100, 2, ',', ' ') . ' ₽';
    }

    public function getFormattedDiscountAttribute(): string
    {
        return number_format($this->discount / 100, 2, ',', ' ') . ' ₽';
    }

    public function getFormattedTotalAttribute(): string
    {
        return number_format($this->total / 100, 2, ',', ' ') . ' ₽';
    }

    public function getCreatedAtFormattedAttribute(): string
    {
        return $this->created_at->format('d.m.Y H:i');
    }

    public function canBeEdited(): bool
    {
        return $this->status === OrderStatus::Pending;
    }
}
```

```blade
{{-- ✅ Authorization via @can (NOT @php) --}}
@can('update', $order)
    @if ($order->canBeEdited())
        <a href="{{ route('orders.edit', $order) }}">Edit</a>
    @endif
@endcan
```

```blade
{{-- ✅ Or use a Blade Component for reusability --}}
<x-order-summary :order="$order" />

{{-- resources/views/components/order-summary.blade.php --}}
<div>
    <p>Subtotal: {{ $order->formatted_subtotal }}</p>
    <p>Discount: {{ $order->formatted_discount }}</p>
    <p>Total: {{ $order->formatted_total }}</p>
</div>
```

## Where the Logic Goes

| View-side need | Where it goes |
|----------------|---------------|
| Calculation (subtotal, total) | Eloquent accessor on the model |
| Formatting (date, money) | Accessor on the model, or a Blade Component |
| Auth check | `@can` directive, or Policy method |
| Conditional rendering | `@if` directly on the condition, or a Component |
| Complex data prep | Controller (passed as a variable), or View Composer |
| Reusable UI piece | Blade Component (`<x-...>`) |
| Loop with complex logic | Custom Blade directive (rare) or Component |

## Allowed Blade Directives

```blade
{{-- ✅ These are fine --}}
@if / @else / @elseif
@foreach / @forelse / @for
@can / @cannot / @canany
@auth / @guest
@isset / @empty
@switch / @case
@include / @extends / @section / @yield
@props / @aware / @once (Components)
@csrf / @method
{{-- ❌ This is forbidden --}}
@php / @endphp
```

## One Exception: Truly Trivial One-Offs

```blade
{{-- ⚠️ The only acceptable use is for a trivial inline computation that is genuinely view-only and never duplicated --}}
@php $isEven = count($items) % 2 === 0; @endphp
@if ($isEven)
    <p>Even number of items</p>
@endif
```

Even in this case, prefer:

```php
// ✅ Push it to the controller or a small helper
$isEven = count($items) % 2 === 0;
```

**Default: no `@php`**. If you really need it, justify it in a code review.

## Lint Rule

Add this to `pint.json` or a custom check:

```php
// tests/Feature/BladeNoPhpTest.php
it('does not use @php directives in Blade files', function () {
    $files = File::allFiles(resource_path('views'));
    $violations = [];

    foreach ($files as $file) {
        if (preg_match('/@php\b/', $file->getContents())) {
            $violations[] = $file->getRelativePathname();
        }
    }

    expect($violations)->toBeEmpty(
        "Blade files using @php: " . implode(', ', $violations),
    );
});
```

## When to Apply

- Every Blade template.
- Every `@php ... @endphp` block in the codebase.
- Every PR that touches a view file.

## Why

1. **Separation of concerns**: views render, models calculate.
2. **Testability**: accessors can be unit-tested; `@php` cannot.
3. **Reusability**: an accessor works in API, web, queue, CLI.
4. **Readability**: `@foreach ($items as $item)` > `@php foreach (...) @endphp`.
5. **Framework-aligned**: Laravel's design is to push logic to PHP, not Blade.
6. **Refactor safety**: a calculation in a model can be reused; in a view it cannot.
7. **Bugs are hidden in @php**: a typo in a view is harder to catch than a typo in a model.
