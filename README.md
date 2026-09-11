# Agent Skill Adapter

Universal adapter and compiler between agent skill standards.

## Development

Prerequisites:
- Python >= 3.10
- [uv](https://github.com/astral-sh/uv)

### Quickstart

```bash
make install
make check
```

### Makefile Targets

- `make install`: Install dependencies and development tools.
- `make lint`: Run ruff linter and format checker.
- `make format`: Auto-format code and fix safe lint issues.
- `make test`: Run test suite with pytest.
- `make check`: Run all validation gates (lint, typecheck, test).
