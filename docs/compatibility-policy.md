# Shared File Compatibility Policy

## Scope

This policy applies to **shared cross-client files** only:
- `rooms/<room>/messages.jsonl`
- `rooms/<room>/presence/<presence-id>`
- `memory/global.jsonl`

Local/internal files are documented in `docs/local-file-contract.md` and versioned with application releases, not cross-client schema guarantees.

## Policy Name

Strict Reader + Additive Writer

## Rules

1. Required fields are strict.
- Readers reject/skip rows missing required invariants for that shared file type.

2. Unknown optional fields are tolerated.
- Readers must not fail when additive optional fields appear.

3. New fields are additive first.
- Introduce new fields as optional before any required adoption.

4. Breaking schema changes require explicit versioning.
- For event rows, bump schema version and update docs/examples/tests together.

5. Writers remain conservative.
- Writers emit canonical field shapes and valid enums.
- Writers do not emit known-invalid field shapes.

## Change Checklist for Shared Format Updates

- Update `docs/shared-file-contract.md`.
- Update `docs/shared-file-examples/*`.
- Update conformance tests.
- Note compatibility impact in PR description.
