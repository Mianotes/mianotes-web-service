# Testing

Run checks from the repository root.

## Unit and API tests

```bash
pytest
```

The test suite covers the current API behavior, auth flow, notes, folders, tags,
search, MCP helpers, parser adapter behavior, and synchronous Mia prompts.
Automated tests use temporary data folders and do not write to the local
`data/` directory.

## Manual tests with temporary storage

Use the temporary storage wrapper when you want to run manual smoke tests,
seed data, or start a throwaway service instance:

```bash
./scripts/with-temp-storage.sh pytest
```

The wrapper creates a temporary Mianotes data folder, points the service at a
temporary `mia.db`, runs the command, and removes the temporary folder when the
command exits.

To start a disposable local service:

```bash
./scripts/with-temp-storage.sh bash -lc 'mianotes-web-service init-db && mianotes-web-service --host 127.0.0.1 --port 8299'
```

Anything created during that run is removed when the service stops.

## Linting

```bash
ruff check .
```

Ruff enforces the configured Python lint rules in `pyfolder.toml`.

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
