---
id: {prefix}-{concept}
title: {Full Descriptive Title}
category: {core-principles|solid-principles|laravel-architecture}
priority: critical
tags: [{tag1}, {tag2}, {tag3}, {tag4}]
related: [{rule-id-1}, {rule-id-2}, {rule-id-3}]
---

# {Rule Title}

{One or two sentence summary explaining the principle in Laravel/PHP context. Should be clear and actionable.}

## Bad Example

```php
// ❌ Anti-pattern: {Brief description of what's wrong}
{Anti-pattern Laravel/PHP code}

// Problems:
// 1. {Specific issue 1}
// 2. {Specific issue 2}
// 3. {Specific issue 3}
```

**Why This Is Wrong:**

- {Consequence 1}
- {Consequence 2}
- {Consequence 3}

## Good Example

```php
// ✅ Correct approach: {Brief description}
{Correct Laravel/PHP code}

// Benefits:
// 1. {Benefit 1}
// 2. {Benefit 2}
// 3. {Benefit 3}
```

**Alternative Approach (Optional):**

```php
// Another valid solution: {When this might be preferred}
{Alternative Laravel code}
```

## Why

Explanation of the principle and its benefits in Laravel context:

1. **{Benefit Category 1}**: {Detailed explanation}
2. **{Benefit Category 2}**: {Detailed explanation}
3. **{Benefit Category 3}**: {Detailed explanation}
4. **{Benefit Category 4}**: {Detailed explanation}
5. **{Benefit Category 5}**: {Detailed explanation}
6. **{Benefit Category 6}**: {Detailed explanation}
7. **{Benefit Category 7}**: {Detailed explanation}

## When to Apply

- {Laravel scenario 1}
- {Laravel scenario 2}
- {Laravel scenario 3}
- {Laravel scenario 4}

## When NOT to Apply (Optional)

```php
// Acceptable exception: {Scenario where the rule can be relaxed}
{Acceptable Laravel code with clear reasoning}

// This is acceptable because:
// - {Reason 1}
// - {Reason 2}
```

## Common Mistakes (Optional)

### Mistake 1: {Common Laravel misunderstanding}

```php
// ❌ Wrong
{Wrong Laravel code}
// ✅ Correct
{Correct Laravel code}
```

### Mistake 2: {Another common issue}

```php
// ❌ Wrong
{Wrong Laravel code}
// ✅ Correct
{Correct Laravel code}
```

## Related Principles

- **{Related Rule 1}**: {Brief explanation of relationship}
- **{Related Rule 2}**: {Brief explanation of relationship}
- **{Related Rule 3}**: {Brief explanation of relationship}

## Further Reading (Optional)

- {Laravel docs URL}
- {Article title} - {URL}

---

## Template Guidelines

### Frontmatter

- **id**: `{prefix}-{concept}` — must match filename, kebab-case, unique
- **title**: Full descriptive title
- **category**: One of `core-principles`, `solid-principles`, `laravel-architecture`
- **priority**: `critical` (all rules in this skill are critical)
- **tags**: 3-5 tags for searchability
- **related**: 2-4 related rule IDs

### Content Structure

1. **Title & Summary** — one or two sentences
2. **Bad Example** — anti-pattern with problems listed
3. **Good Example** — correct implementation with benefits
4. **Why** — 5-7 benefits
5. **When to Apply** — practical Laravel scenarios
6. **Optional sections** — When NOT to Apply, Common Mistakes, Related Principles

### Code Examples

- Use PHP 8.4 with strict types: `declare(strict_types=1);`
- Use Laravel 13 idioms
- Mark bad examples with `❌`, good with `✅`
- Keep examples minimal but realistic
- Use real Laravel namespaces: `App\Http\Controllers`, `App\Models`, `App\Jobs`
- Constructor property promotion where appropriate
- Named arguments where helpful

### Writing Style

- Direct and actionable
- Explain "why", not just "what"
- Active voice
- Concise
- Laravel-specific
- Assume intermediate Laravel knowledge

### Length

- Minimum 150 lines (simple rules)
- Target 250-350 lines
- Maximum 500 lines

### Quality Checklist

- [ ] Frontmatter complete
- [ ] Bad example with problems listed
- [ ] Good example with benefits
- [ ] 5+ benefits in "Why"
- [ ] Practical Laravel "When to Apply" scenarios
- [ ] Related rules referenced
- [ ] Realistic Laravel 13 code
- [ ] PHP 8.4 features used (typed properties, enums, readonly)
- [ ] Proofread
