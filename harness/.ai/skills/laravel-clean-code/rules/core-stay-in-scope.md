---
id: core-stay-in-scope
title: Stay Within Task Scope
category: core-principles
priority: critical
tags: [scope, discipline, focus, unrelated]
related: [core-minimize-change, core-respect-existing, core-final-check]
---

# Stay Within Task Scope

Do not add unrelated improvements. Do not fix unrelated architectural issues merely because they were discovered during implementation. If a serious unrelated issue is found, report it separately rather than silently expanding the implementation scope.

## Bad Example

```php
// ❌ Task: "Add a 'phone' field to the registration form"
// PR: registration form + 23 unrelated changes

// Changed files:
- app/Http/Controllers/Auth/RegisterController.php (added phone)
- resources/views/auth/register.blade.php (added phone input)
+ app/Http/Controllers/Admin/DashboardController.php (refactored to thin controller — unrelated)
+ app/Models/User.php (added HasFactory import — unrelated cleanup)
+ app/Services/PaymentService.php (replaced interface with concrete — unrelated refactor)
+ config/services.php (added new provider config — unrelated new feature)
+ 5 other files

// Problems:
// 1. 9 of 10 changes are unrelated
// 2. Reviewer cannot easily verify the original task
// 3. Each unrelated change requires its own review
// 4. Blocked by other review discussions
// 5. Original task is buried
```

## Good Example

```php
// ✅ Task: "Add a 'phone' field to the registration form"
// PR: only the 3 files needed

// 1. database/migrations/2026_08_07_add_phone_to_users.php
Schema::table('users', function (Blueprint $table) {
    $table->string('phone')->nullable();
});

// 2. app/Http/Requests/RegisterRequest.php
public function rules(): array
{
    return [
        'name' => ['required', 'string', 'max:255'],
        'email' => ['required', 'email', 'unique:users'],
        'password' => ['required', 'confirmed'],
        'phone' => ['nullable', 'string', 'max:32'], // new
    ];
}

// 3. resources/views/auth/register.blade.php
<input type="text" name="phone" value="{{ old('phone') }}">

// Benefits:
// 1. Trivially reviewable
// 2. Original task is clear
// 3. No unrelated risk
// 4. Easy to revert if needed
// 5. Fast to merge
```

## What to Do With Unrelated Discoveries

When you find something unrelated:

```php
// Discovery during task: "I notice the AdminController has a 200-line method"
// Action: do NOT fix it now.
// Action: file a follow-up issue:
//   "Refactor AdminController::index — extracted for future work"
// Action: continue with the original task.
```

## Why

1. **Reviewer focus**: reviewers verify the task, not the universe.
2. **Merge velocity**: small focused PRs merge fast.
3. **Risk containment**: unrelated changes can break unrelated things.
4. **Revert safety**: revert the original task without losing other work.
5. **Mental model**: author has the original task in mind, not the unrelated fix.
6. **Backlog hygiene**: real issues become backlog items, not hidden in PRs.
7. **Respect for team**: don't dump surprises into someone else's review.

## When to Apply

- Every task, every PR, every commit.
- When something "tangential" comes up.
- When you spot an obvious smell in adjacent code.

## The "While I'm Here" Test

When tempted to change unrelated code, ask:

> "If this unrelated change broke production, would the user understand why it's in this PR?"

If no — file a follow-up instead.
