# Contributing

## Portability Rules

- Keep changes portable across Windows, Linux, and macOS.
- Prefer `pathlib` and normalized paths over platform-specific string concatenation.
- Avoid hardcoding drive-letter assumptions or shell-specific behavior in core code.
- Keep launcher behavior (`run_chat.bat`, `run_chat.sh`) functionally equivalent.

## Shared File Contract

- Shared storage format is a compatibility contract across clients.
- Before changing shared files, update:
  - `docs/shared-file-contract.md`
  - `docs/compatibility-policy.md`
  - `docs/shared-file-examples/`
  - conformance tests (`tests/test_contract.py`)

## Development Workflow

- Run quality checks before opening a PR:
  - Windows: `check.bat`
  - Linux/macOS: `./check.sh`
- Keep PRs focused and include schema/compat notes for storage-format changes.
