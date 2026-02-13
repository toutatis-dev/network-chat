# Shared File Compatibility Policy

## Policy Name

Strict Reader + Additive Writer

## Rules

1. Required fields are strict.
- Readers reject/skip rows missing required invariants for that file type.

2. Unknown optional fields are tolerated.
- Readers must not fail when additional optional fields appear.

3. New fields are additive first.
- Introduce new fields as optional before any required adoption.

4. Breaking schema changes require explicit versioning.
- For event rows, bump schema version and update docs/examples/tests together.

5. Writers should remain conservative.
- Writers emit current canonical schema fields and valid enums.
- Writers must not emit known-invalid field shapes.

## Change Checklist for Shared Format Updates

- Update `docs/shared-file-contract.md`.
- Update `docs/shared-file-examples/*`.
- Update conformance tests.
- Note compatibility impact in PR description.
