---
id: laravel-policies
title: Authorization in Policies
category: laravel-architecture
priority: critical
tags: [policy, authorization, security, gate]
related: [laravel-controller-thin, laravel-form-request, laravel-blade-no-php]
---

# Authorization in Policies

Authorization checks must live in `Policy` classes, not in controllers, FormRequests, or Blade `@if` blocks. Use `authorize()` in FormRequest or `$this->authorize()` in the controller. Use `@can` in Blade, not `@if (auth()->user()->can(...))`. Never check roles directly in the view — use a Gate or Policy method.

## Bad Example

```php
// ❌ Authorization in the controller, duplicated in Blade
final class OrderController extends Controller
{
    public function show(int $id): View
    {
        $order = Order::findOrFail($id);

        if ($order->user_id !== auth()->id() && ! auth()->user()->isAdmin()) {
            abort(403);
        }

        return view('orders.show', compact('order'));
    }
}
```

```blade
@if ($order->user_id === auth()->id() || auth()->user()->isAdmin())
    <a href="{{ route('orders.edit', $order) }}">Edit</a>
@endif
```

```php
// Problems:
// 1. Same authorization logic in 2 places
// 2. "isAdmin" definition is unclear — where does it live?
// 3. Adding a new role (e.g. "manager") requires editing 2+ files
// 4. Easy to forget the check on a new endpoint
// 5. Blade `@if` shows business logic in the view
```

## Good Example

```php
// ✅ Policy class owns the rules
final class OrderPolicy
{
    public function view(User $user, Order $order): bool
    {
        return $order->user_id === $user->id || $user->isAdmin();
    }

    public function update(User $user, Order $order): bool
    {
        return $order->user_id === $user->id
            && $order->status === OrderStatus::Pending;
    }
}

// Controller — single call
final class OrderController extends Controller
{
    public function show(Order $order): View
    {
        $this->authorize('view', $order);
        return view('orders.show', compact('order'));
    }
}

// Or in FormRequest:
final class UpdateOrderRequest extends FormRequest
{
    public function authorize(): bool
    {
        return $this->user()->can('update', $this->route('order'));
    }
}
```

```blade
@can('update', $order)
    <a href="{{ route('orders.edit', $order) }}">Edit</a>
@endcan
```

## Auto-Discovery

Laravel auto-resolves policies by convention:

```php
// App\Models\Order → App\Policies\OrderPolicy
// Auto-resolved when you call $this->authorize('view', $order)

// Or register manually in AuthServiceProvider:
protected $policies = [
    Order::class => OrderPolicy::class,
];
```

## Use Gates for Actions That Aren't Model-Bound

```php
// ✅ Gate for a non-model action
Gate::define('access-admin', fn (User $user) => $user->isAdmin());

// In a controller:
if (! Gate::allows('access-admin')) {
    abort(403);
}

// Or as middleware:
Route::middleware(['auth', 'can:access-admin'])->group(function () { ... });

// In Blade:
@can('access-admin')
    <a href="{{ route('admin.dashboard') }}">Admin</a>
@endcan
```

## Policy Conventions

| Method | Convention |
|--------|------------|
| `view` | Can the user see this model? |
| `create` | Can the user create a new instance? |
| `update` | Can the user edit this model? |
| `delete` | Can the user delete this model? |
| Custom | `cancel(User $user, Order $order)` — name the action |

## When to Apply

- Every controller method that touches a model.
- Every Blade view that shows actions on a model.
- Every API endpoint with a model parameter.
- Every FormRequest that mutates a model.

## When NOT to Apply

- Public routes (login, register, home).
- Routes that only authenticated users can hit (use `auth` middleware).
- Trivial middleware-only checks (e.g. `throttle:10,1`).

## Why

1. **Centralized**: one place per model.
2. **Reusable**: controller + Blade + middleware all use the same rule.
3. **Testable**: `assertGuest()->cannot('view', $order)`.
4. **Discoverable**: all rules for Order live in OrderPolicy.
5. **Laravel-aligned**: framework convention.
6. **Auto-resolved**: no manual registration needed.
7. **Secure by default**: `$this->authorize()` is harder to forget.
