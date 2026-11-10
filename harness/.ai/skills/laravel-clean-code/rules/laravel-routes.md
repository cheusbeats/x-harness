---
id: laravel-routes
title: Thin, Named, Grouped Routes
category: laravel-architecture
priority: critical
tags: [routes, routing, middleware, naming]
related: [laravel-controller-thin, laravel-policies, laravel-form-request]
---

# Thin, Named, Grouped Routes

Routes must be named, grouped by middleware, and never contain business logic. Use `route()` in views and redirects, never hard-coded URLs. Group related routes and apply middleware at the group level. Prefer single-action controllers (`__invoke`) when a controller has only one method.

## Bad Example

```php
// ❌ Unnamed routes, no grouping, no middleware
Route::get('/admin/users', [AdminUserController::class, 'index']);
Route::get('/admin/users/create', [AdminUserController::class, 'create']);
Route::post('/admin/users', [AdminUserController::class, 'store']);
Route::get('/admin/users/{id}/edit', [AdminUserController::class, 'edit']);
Route::put('/admin/users/{id}', [AdminUserController::class, 'update']);
Route::delete('/admin/users/{id}', [AdminUserController::class, 'destroy']);

Route::get('/admin/orders', [AdminOrderController::class, 'index']);
Route::post('/admin/orders/{id}/cancel', [AdminOrderController::class, 'cancel']);

// In a Blade view:
<a href="/admin/users/{{ $user->id }}/edit">Edit</a>

// Problems:
// 1. No route names — view hard-codes URL
// 2. No middleware grouping — every route needs it added individually
// 3. If URL changes, every Blade reference breaks
// 4. Easy to forget middleware on a new route
// 5. Hard to see all admin routes in one glance
// 6. CRUD pattern repeated manually
```

## Good Example

```php
// ✅ Grouped, named, middleware applied once
Route::middleware(['auth', 'verified'])
    ->prefix('admin')
    ->name('admin.')
    ->group(function () {
        Route::resource('users', AdminUserController::class);
        // → admin.users.index, admin.users.create, admin.users.store,
        //   admin.users.show, admin.users.edit, admin.users.update, admin.users.destroy

        Route::post('orders/{order}/cancel', [AdminOrderController::class, 'cancel'])
            ->name('orders.cancel');
    });

// API routes
Route::middleware(['auth:sanctum', 'throttle:api'])
    ->prefix('api/v1')
    ->name('api.v1.')
    ->group(__DIR__ . '/api/v1.php');

// In a Blade view:
<a href="{{ route('admin.users.edit', $user) }}">Edit</a>
<a href="{{ route('orders.show', $order) }}">View</a>

// In a controller:
return redirect()->route('orders.show', $order);
```

## Resource Routes

```php
// ✅ Resource routing generates 7 routes with one line
Route::resource('orders', OrderController::class);
// → orders.index, orders.create, orders.store, orders.show,
//   orders.edit, orders.update, orders.destroy

// Limit to specific actions
Route::resource('orders', OrderController::class)->only(['index', 'show']);
Route::resource('reports', ReportController::class)->except(['destroy']);

// API-flavored (no create/edit, only the JSON actions)
Route::apiResource('orders', OrderController::class);
// → orders.index, orders.store, orders.show, orders.update, orders.destroy
```

## Single-Action Controllers

```php
// ✅ When a controller has only one method
final class ShowDashboard extends Controller
{
    public function __invoke(): View
    {
        return view('dashboard', ['stats' => $this->stats()]);
    }
}

// Route:
Route::get('/dashboard', ShowDashboard::class)->name('dashboard');
```

## Livewire Full-Page Routes (Livewire 4)

```php
// ✅ Livewire 4 routes full-page components directly — no controller needed

// SFC / view-based components are referenced by name:
Route::livewire('/orders', 'order-list')->name('orders.index');

// MFC / class-based components are referenced by class:
Route::livewire('/orders/create', OrderForm::class)
    ->middleware('auth')
    ->name('orders.create');

// Works inside groups like any other route:
Route::middleware('auth')->group(function () {
    Route::livewire('/profile', 'profile')->name('profile');
});
```

## Route Conventions

| Pattern | Convention |
|---------|------------|
| Names | `kebab-case.sub-resource.action` (e.g. `admin.users.index`) |
| URLs | `kebab-case` (e.g. `/admin/user-profiles`) |
| Parameters | `{user}`, `{order}` (model binding by name) |
| Middleware | Group level, not per-route |
| Auth | `Route::middleware(['auth', 'verified'])` group |

## Model Binding

```php
// ✅ Implicit binding — type-hint the model
Route::get('/users/{user}', [UserController::class, 'show']);
// Controller: public function show(User $user)

// ✅ Custom key
Route::get('/users/{user:slug}', [UserController::class, 'show']);

// ✅ Explicit binding in a provider
Route::bind('order', fn ($id) => Order::where('uuid', $id)->firstOrFail());
```

## When to Apply

- Every route definition.
- Every view link / form action.
- Every redirect in a controller.

## Why

1. **Discoverability**: `php artisan route:list` shows the full surface.
2. **Refactor safety**: rename a route, the URL follows.
3. **Middleware consistency**: applied once at the group level.
4. **URLs are API**: changing them is a breaking change.
5. **Laravel-aligned**: framework convention.
6. **Resource routes**: 7 routes with one line.
7. **Type safety**: model binding is automatic.
