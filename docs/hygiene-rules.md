# Default SBG hygiene rules

SBG ships with a small default rule set that is intentionally opinionated. Each
rule is meant to catch a class of low-value or risky changes before they become
part of a commit.

## 1. scaffold-leftovers

What it catches:
- Comments that look like unfinished work, such as "fill in later" or
  "sample text".

Why it matters:
- Scaffold leftovers usually mean the change is incomplete or copied from a
  starting point. They create confusion for reviewers and future maintainers.

Good pattern:
```python
# Build a user profile from the auth payload.
```

Bad pattern:
```python
# fill in later
```

## 2. marker-spam

What it catches:
- Repeated follow-up markers that accumulate in the codebase.

Why it matters:
- Marker spam is a sign that the change is carrying unresolved notes instead of
  clear implementation work. Too many markers make it harder to distinguish real
  defects from noise.

Good pattern:
```python
# Follow-up: wire this up after the API contract is finalized.
```

Bad pattern:
```python
# Follow-up Follow-up Follow-up Follow-up Follow-up
```

## 3. empty-files

What it catches:
- Files that are empty or contain only whitespace.

Why it matters:
- Empty files are rarely intentional. They usually indicate a failed edit, an
  incomplete migration, or a placeholder that should be deleted or filled in.

Good pattern:
```python
"""Configuration for the service client."""
```

Bad pattern:
```text
<empty file>
```

## 4. long-lines

What it catches:
- Lines that are overly long and hard to read in diffs or editors.

Why it matters:
- Long lines hurt readability, make review comments harder to place, and often
  hide multiple concerns in a single statement.

Good pattern:
```python
payload = {
    "user_id": user_id,
    "role": role,
}
```

Bad pattern:
```python
payload = {"user_id": user_id, "role": role, "status": status, "active": active, "name": name}
```

## 5. button-types

What it catches:
- Buttons that omit an explicit `type` attribute or declare a non-standard type.

Why it matters:
- Explicit button types make UI interactions predictable and reduce accidental
  submits or form resets. They are a low-friction way to keep the interface
  consistent across generated components.

Good pattern:
```html
<button type="button">Cancel</button>
```

Bad pattern:
```html
<button>Cancel</button>
```

## 6. form-labels

What it catches:
- Form controls that lack a clear label or accessible name.

Why it matters:
- Labels make forms usable for assistive tech and reduce the chance that agentic
  edits create confusing or broken interactive surfaces.

Good pattern:
```html
<label for="email">Email</label>
<input id="email" name="email" />
```

Bad pattern:
```html
<input name="email" />
```

## 7. file-size

What it catches:
- Files that grow beyond the configured size threshold, which defaults to 1 MiB.

Why it matters:
- Oversized files are harder to review, diff, and maintain. They often indicate
  generated output, copied assets, or a bad place for logic that should be split
  into smaller modules.

Good pattern:
```python
# Keep the implementation split across focused modules.
```

Bad pattern:
```text
A generated JSON payload that is hundreds of kilobytes long and committed as a
single source file.
```

## How to use this guide

Use these rules as a quick reference when a check fails. If a violation appears,
fix the underlying issue in the code rather than trying to silence the rule.
The goal is to keep changes small, clear, and reviewable.
