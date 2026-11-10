---
id: laravel-form-request
title: Validation in FormRequest
category: laravel-architecture
priority: critical
tags: [form-request, validation, authorize]
related: [laravel-controller-thin, laravel-policies, core-error-handling]
---

# Validation in FormRequest

Validation logic must live in a dedicated `FormRequest` class, never inline in the controller as `$request->validate(...)`. FormRequest provides separation of concerns, reusability, type safety, automatic authorization, and easier testing.

## Bad Example

```php
// ❌ Inline validation in the controller
final class UserController extends Controller
{
    public function store(Request $request): RedirectResponse
    {
        $validated = $request->validate([
            'name' => 'required|string|max:255',
            'email' => 'required|email|unique:users,email',
            'password' => 'required|string|min:8|confirmed',
            'phone' => 'nullable|string|max:32',
            'birthday' => 'nullable|date|before:today',
            'agree' => 'required|accepted',
        ]);

        $user = User::create($validated);
        Auth::login($user);

        return redirect()->route('home');
    }
}

// Problems:
// 1. Controller mixes validation with dispatch
// 2. Validation cannot be reused
// 3. No automatic authorization
// 4. Hard to test in isolation
// 5. The validation array is inline noise
```

## Good Example

```php
// ✅ Dedicated FormRequest

final class StoreUserRequest extends FormRequest
{
    public function authorize(): bool
    {
        return true; // or: $this->user()->can('create', User::class);
    }

    public function rules(): array
    {
        return [
            'name' => ['required', 'string', 'max:255'],
            'email' => ['required', 'email', Rule::unique('users', 'email')],
            'password' => ['required', Password::min(8)->mixedCase()->numbers()],
            'phone' => ['nullable', 'string', 'max:32'],
            'birthday' => ['nullable', 'date', 'before:today'],
            'agree' => ['required', 'accepted'],
        ];
    }

    public function messages(): array
    {
        return [
            'agree.accepted' => 'You must accept the terms.',
        ];
    }
}

final class UserController extends Controller
{
    public function store(StoreUserRequest $request): RedirectResponse
    {
        $user = User::create($request->validated());
        Auth::login($user);

        return redirect()->route('home');
    }
}

// Benefits:
// 1. Validation is a separate class
// 2. Reusable: same FormRequest for API + web
// 3. Authorization integrated via authorize()
// 4. Custom messages and attributes
// 5. Auto-validated before the controller method runs
// 6. Testable: $this->post('/users', $data) tests validation end-to-end
```

## Use the Array Syntax

Prefer the array syntax (Laravel 9+) over the pipe syntax:

```php
// ✅ Array syntax — easier to read, supports Rule objects
'email' => ['required', 'email', Rule::unique('users', 'email')],

// ⚠️ Pipe syntax still works
'email' => 'required|email|unique:users,email',
```

## Custom Rule Classes

For complex validation, use dedicated rule classes:

```php
// ✅ Complex rule as its own class
final class ValidRussianPhone implements ValidationRule
{
    public function validate(string $attribute, mixed $value, Closure $fail): void
    {
        if (! preg_match('/^\+7\d{10}$/', (string) $value)) {
            $fail('The :attribute must be a valid Russian phone number.');
        }
    }
}

// Used in FormRequest:
'phone' => ['required', new ValidRussianPhone()],
```

## When to Apply

- Every POST, PUT, PATCH endpoint.
- Any endpoint that accepts user input.
- API requests (always).

## When NOT to Apply

- GET endpoints with no input.
- Internal APIs that already trust the caller.
- One-off scripts where Laravel's validator is overkill.

## Why

1. **Separation of concerns**: validation is a distinct responsibility.
2. **Reusability**: same FormRequest across web + API.
3. **Authorization integration**: `authorize()` runs first.
4. **Type safety**: `validated()` returns a clean array.
5. **Testability**: feature test posts invalid data, asserts 422.
6. **Custom messages**: per-rule, per-locale.
7. **Laravel-aligned**: framework convention, expected by the team.
