# Theming and customisation

This page is the home for customisation guidance.

Mianotes has two kinds of customisation:

- runtime configuration for the web service, parser, storage, and model providers;
- static publishing themes used when notes are exported as documentation sites.

Treat the main web app visual design as application code. Static site publishing themes use a small theme boundary.

## Static publishing themes

Mianotes ships four static publishing themes:

| Theme ID | Name | Purpose |
|---|---|---|
| `mialight` | Mialight | Default light documentation theme. |
| `miadocs` | Miadocs | Polished article-reading theme for published notes and documentation. |
| `opencode` | OpenCode | Geeky developer documentation theme with terminal-style code blocks. |
| `miadark` | Miadark | Dark documentation theme. |

Theme assets live in:

```text
src/mianotes_web_service/publishing/themes/<theme-id>/
```

Each theme directory contains:

```text
theme.json
styles.css
site.js
```

`theme.json` defines the theme metadata returned by `GET /api/publish/themes`.
`styles.css` controls the published site appearance. `site.js` handles static
site behaviour such as navigation, search wiring, article state, and previous
version links.

Static themes should render these Markdown features well:

- headings and article title hierarchy;
- paragraphs, ordered lists, and unordered lists;
- inline code and fenced code blocks;
- Markdown tables;
- links;
- GitHub-style admonitions such as `[!TIP]`, `[!NOTE]`, and `[!WARNING]`;
- the generated **On this page** column;
- previous-version links when `showPreviousVersions` is enabled.

When adding or changing a theme, run the publishing tests and manually publish a
small site that includes code blocks, tables, admonitions, and enough headings
to populate the right-hand article navigation.

```bash
pytest tests/test_api_publish.py
```

## Runtime customisation

Supported configuration areas:

- service host and port;
- data directory;
- database URL;
- allowed storage locations;
- LLM provider and model;
- image OCR fallback model;
- service-wide API key;
- scoped agent tokens;
- parser adapters.

See [Configuration options](../02-getting-started/03-configuration.md) for environment variables.

## Ports

```text
8200  web service
8201  alternate local service
```

## Storage customisation

Default:

```text
data/
data/.mianotes/mia.db
```

Advanced:

```env
MIANOTES_DATA_DIR=/absolute/path/to/mianotes-data
MIANOTES_DATABASE_URL=sqlite:////absolute/path/to/.mianotes/mia.db
```

Admins can switch between allowed local folders from the Settings screen.

## Parser customisation

The parser stack is adapter-based. The default adapter uses Microsoft MarkItDown, with additional URL cleanup, source storage, OCR, and optional OpenAI image fallback.

Specialist local or hosted parsers belong behind the same parser adapter boundary so API behaviour remains stable.

## LLM customisation

Mia supports:

```text
openai
local
openai-compatible
```

Example local setup:

```env
MIANOTES_LLM_PROVIDER=local
MIANOTES_LLM_MODEL=llama3.2:3b
MIANOTES_LLM_BASE_URL=http://127.0.0.1:11434/v1
MIANOTES_LLM_API_KEY=ollama
```

## Web app theme conventions

Keep these decisions documented when changing the web app visual system:

- colour tokens;
- typography scale;
- spacing scale;
- dark mode behaviour;
- logo and app icon placement;
- Markdown rendering styles;
- note status badges;
- accessibility contrast rules;
- whether themes are per-user, per-workspace, or build-time only.

## Suggested theme documentation template

```markdown
# Theme name

## Purpose

Who this theme is for and where it should be used.

## Tokens

| Token | Value | Usage |
|---|---|---|
| `--color-background` | `...` | App background |
| `--color-text` | `...` | Primary text |

## Components

Notes about buttons, cards, sidebars, editors, and Markdown rendering.

## Accessibility checks

Contrast and keyboard-navigation notes.
```
