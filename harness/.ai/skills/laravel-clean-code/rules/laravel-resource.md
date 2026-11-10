---
id: laravel-resource
title: API Output via Resources
category: laravel-architecture
priority: critical
tags: [resource, api, serialization, response]
related: [laravel-controller-thin, laravel-eloquent-n-plus-one]
---

# API Output via Resources

API responses must go through `JsonResource` / `ResourceCollection` classes. Do not return Eloquent models, raw arrays, or `$model->toArray()` directly from controllers. Resources give a stable API contract, hide internal fields, and prevent leaking sensitive data.

## Bad Example

```php
// ❌ Returning model directly
final class UserController extends Controller
{
    public function show(User $user): JsonResponse
    {
        return response()->json($user);
    }
}

// Problems:
// 1. Leaks password hash, remember_token, email_verified_at
// 2. Leaks every new column added to users table
// 3. No control over field naming (id vs userId)
// 4. Cannot add computed fields
// 5. No conditional fields (admin sees more)
```

## Good Example

```php
// ✅ Dedicated Resource
final class UserResource extends JsonResource
{
    public function toArray(Request $request): array
    {
        return [
            'id' => $this->id,
            'name' => $this->name,
            'email' => $this->when(! $this->resource->is($request->user()), $this->email),
            'created_at' => $this->created_at?->toIso8601String(),
            'roles' => RoleResource::collection($this->whenLoaded('roles')),
            'orders_count' => $this->whenCounted('orders'),
        ];
    }
}

// Collection resource for lists
final class UserCollection extends ResourceCollection
{
    public $collects = UserResource::class;
}

// Controller
final class UserController extends Controller
{
    public function show(User $user): UserResource
    {
        return new UserResource($user->load('roles'));
    }

    public function index(): UserCollection
    {
        return new UserCollection(User::query()->paginate(20));
    }
}

// Benefits:
// 1. Stable contract — internal column changes don't break the API
// 2. Sensitive fields hidden by default
// 3. Computed fields are easy to add
// 4. Conditional fields with when() / mergeWhen()
// 5. whenLoaded() prevents N+1 leakage
// 6. Collections handle pagination meta
```

## Resource Conventions

| Pattern | Use |
|---------|-----|
| `JsonResource` | Single model → object |
| `ResourceCollection` | List of models |
| `whenLoaded()` | Include relation only if eager-loaded |
| `whenCounted()` | Include count only if withCount was called |
| `additional()` | Add metadata (e.g. links, totals) |
| `wrap('data')` | Customize the top-level key |

## Hide Sensitive Fields

```php
// ✅ Hide fields explicitly
public function toArray(Request $request): array
{
    return [
        'id' => $this->id,
        'name' => $this->name,
        'email' => $this->email,
        // password, remember_token, etc. NOT included
    ];
}

// Or, ban entire attributes at the model level
protected $hidden = ['password', 'remember_token'];
```

## When to Apply

- Every API endpoint.
- Every external-facing response.
- Any JSON response that leaves the application.

## When NOT to Apply

- Internal admin pages (Filament handles this).
- HTML responses (Blade views).
- Webhook payloads (use a dedicated DTO / array).

## Why

1. **API stability**: internal refactor doesn't break clients.
2. **Security**: prevent accidental data leaks.
3. **Performance**: prevent accidental relation loads.
4. **Documentation**: Resource = API schema.
5. **Conditional fields**: easy with `when()`.
6. **Laravel-aligned**: framework convention.
7. **Testability**: assert exact response shape.
