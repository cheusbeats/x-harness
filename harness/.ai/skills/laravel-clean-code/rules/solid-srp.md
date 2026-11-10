---
id: solid-srp
title: Single Responsibility Principle (SRP)
category: solid-principles
priority: critical
tags: [solid, srp, responsibility, cohesion]
related: [core-premature-abstraction, core-kiss, laravel-controller-thin, laravel-form-request]
---

# Single Responsibility Principle (SRP)

Keep responsibilities cohesive. Separate code when responsibilities genuinely change for different reasons. Do not fragment cohesive code into many tiny classes solely to satisfy SRP formally. A class has one reason to change when the same actor does not cause both kinds of change.

## Bad Example

```php
// ❌ Controller + Validator + Mailer + Repository in one class
final class UserController extends Controller
{
    public function store(Request $request): RedirectResponse
    {
        $this->validate($request, [
            'email' => 'required|email|unique:users',
            'password' => 'required|min:8',
        ]);

        if (User::where('email', $request->email)->exists()) {
            throw new \Exception('Duplicate');
        }

        $user = new User();
        $user->email = $request->email;
        $user->password = bcrypt($request->password);
        $user->save();

        Mail::to($user)->send(new WelcomeEmail($user));
        event(new UserRegistered($user));
        Log::info('User registered', ['id' => $user->id]);

        return redirect('/dashboard');
    }
}

// Problems:
// 1. Validation logic lives in the controller
// 2. Business rules inline
// 3. Side effects (email, event, log) in HTTP layer
// 4. Hard to test — 5 things happen in one method
// 5. 4 reasons to change: HTTP, validation, business, side effects
```

## Good Example

```php
// ✅ Each layer has one responsibility

// 1. FormRequest — validation only
final class StoreUserRequest extends FormRequest
{
    public function authorize(): bool { return true; }

    public function rules(): array
    {
        return [
            'email' => ['required', 'email', Rule::unique('users', 'email')],
            'password' => ['required', Password::min(8)],
        ];
    }
}

// 2. Controller — dispatch only
final class UserController extends Controller
{
    public function store(StoreUserRequest $request): RedirectResponse
    {
        $user = User::create($request->validated());

        UserRegistered::dispatch($user);

        return redirect()->route('dashboard');
    }
}

// 3. Listener — side effects only
final class SendWelcomeEmail
{
    public function handle(UserRegistered $event): void
    {
        Mail::to($event->user)->send(new WelcomeEmail($event->user));
    }
}

// Benefits:
// 1. Each class has one reason to change
// 2. Validation lives with the request
// 3. Side effects live in a listener
// 4. Controller is trivially testable
// 5. Each part can be tested in isolation
```

## When to Apply

- A class has 3+ clearly distinct responsibilities.
- A method has both "decide what to do" and "do it" mixed.
- A class imports more than 3 namespaces not from a parent.
- A method has multiple early returns that are really "validate this" or "check that".

## When NOT to Apply (Pragmatic)

```php
// ❌ SRP gone wrong: 3 lines split into 3 classes
final class UserNameFormatter
{
    public static function format(string $name): string
    {
        return trim(ucfirst($name));
    }
}

// ✅ Inline the formatting
$name = trim(ucfirst($request->input('name')));
// or, if used in 3+ places, a tiny method on the User model
```

SRP is about **reasons to change**, not line count.

## The "Two Hats" Test

A class has more than one responsibility if the same class changes for **two unrelated reasons**:

```php
// User class:
// - Changes when the user schema changes (developers)
// - Changes when the auth flow changes (security team)
// - Changes when the email template changes (marketing)
// → Multiple responsibilities → split
```

## Why

1. **Easier to change**: a single change touches one file.
2. **Easier to test**: each class is testable in isolation.
3. **Easier to understand**: one class, one job, one mental model.
4. **Parallel work**: different teams can own different responsibilities.
5. **Reusable**: side effects (events) can be reused by other entry points.
6. **Laravel-aligned**: FormRequest, Listener, Resource are all SRP in action.
7. **Faster debugging**: stack trace points to one layer.
