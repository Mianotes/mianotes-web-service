# Testing

Run checks from the repository root.

## Unit and API tests

```bash
pytest
```

The test suite covers the current API behavior, auth flow, notes, topics, tags,
search, MCP helpers, parser adapter behavior, and Mia job stubs.

## Linting

```bash
ruff check .
```

Ruff enforces the configured Python lint rules in `pyproject.toml`.

## Compile check

```bash
python -m compileall -q src tests
```

Use this to catch syntax errors across the source and test tree.

## Full local check

```bash
python -m compileall -q src tests
pytest
ruff check .
```

## Notes

Tests should not require real OpenAI credentials or a local LLM server. Code
that calls external model providers should be isolated behind service boundaries
and tested with fakes or mocks.

Parser tests should avoid requiring live network access. URL behavior should be
tested by faking the HTTP fetch boundary and verifying that local files are
passed to MarkItDown.
