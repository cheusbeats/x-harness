---
id: core-dry
title: DRY Without Dogma
category: core-principles
priority: critical
tags: [dry, duplication, knowledge, single-source]
related: [core-premature-abstraction, solid-srp, core-kiss]
---

# DRY Without Dogma

Eliminate duplication of **knowledge and business rules**. Do not eliminate every syntactic similarity. Two pieces of code that look alike but represent different concepts should remain separate. Abstract shared knowledge, not similar syntax.

## Bad Example

```php
// ❌ Forced abstraction over coincidental similarity
final class ValidatorHelper
{
    public static function checkAtLeast18(int $value, string $field): void
    {
        if ($value < 18) {
            throw new ValidationException("$field must be at least 18");
        }
    }

    public static function checkAtLeast1Kg(int $value, string $field): void
    {
        if ($value < 1) {
            throw new ValidationException("$field must be at least 1");
        }
    }
}

// Problems:
// 1. "Must be at least 18" and "must be at least 1" are different domain rules
// 2. Helper hides the actual rule behind a generic name
// 3. If voting age changes to 16, the kg validator still compiles
// 4. Caller has no idea what `checkAtLeast18` actually checks
```

## Good Example

```php
// ✅ Domain rules are explicit, with their own home
final class RegisterUserRequest extends FormRequest
{
    public function rules(): array
    {
        return [
            'age' => ['required', 'integer', 'min:18'], // voting age rule
        ];
    }
}

final class AddProductRequest extends FormRequest
{
    public function rules(): array
    {
        return [
            'weight_kg' => ['required', 'integer', 'min:1'], // warehouse rule
        ];
    }
}

// Or, if the threshold is genuinely shared:
final readonly class MinimumAge
{
    public const VOTING = 18;
    public const ALCOHOL = 21;
}

// Benefits:
// 1. Rules live where they are used
// 2. Each rule can change independently
// 3. No surprise when one constant changes
// 4. Validation framework is already an abstraction
```

## Why

1. **Coupling cost**: shared abstraction = coupled change.
2. **Wrong DRY hides intent**: helper names become vague.
3. **Real DRY is about knowledge, not syntax**: same business rule = DRY; same shape = coincidence.
4. **Local duplication is cheap**: copy-paste of 5 lines is cheaper than wrong abstraction.
5. **Laravel already abstracts**: FormRequest, Eloquent scopes, config files are the right DRY.
6. **Refactor later**: easy to extract when 3rd use case appears.
7. **Testability**: explicit rules are easier to test than generic helpers.

## When to Apply

- Same business rule expressed in two places (price calculation, status transition, tax rate).
- Same magic number/string in two places (move to `const` or `config()`).
- Same Eloquent query in two places (move to local scope or query builder method).
- Same validation rule in two places (move to FormRequest).

## When NOT to Apply

```php
// ❌ Forced DRY over coincidence
$isValidAge = fn ($n) => $n >= 18;
$isValidCount = fn ($n) => $n >= 18; // "coincidentally same threshold"
// ✅ Honest duplication
$isVotingAge = fn ($n) => $n >= 18;
$isBulkOrderQuantity = fn ($n) => $n >= 18;
```

## Rule of Three (Laravel Edition)

Wait for 3 real call sites in the **same domain concept** before extracting:

- 3 controllers building the same Eloquent query → local scope.
- 3 FormRequests sharing the same rule → custom Rule class.
- 3 jobs calling the same API → ApiClient service.
