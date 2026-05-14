# Mianotes Web Service

Mianotes Web Service is the Python backend for Mianotes, an AI-powered local-first app that turns documents, images, links, audio, and text into organised Markdown notes.

The service stores note content on the filesystem, keeps lightweight indexes in SQLite, and exposes JSON REST APIs for the Mianotes web app and developer integrations.

## Current Status

This repository is at the product-definition stage. See [PRD.md](PRD.md) for the current requirements and technical direction.

## Planned Architecture

- Python web API service
- Filesystem-first note storage
- Markdown notes under `/data/<username>/<topic>/<filename>.md`
- JSON sidecar files for note comments
- SQLite index for users, topics, notes, source files, and comments
- Repository layer designed for future PostgreSQL support
- OpenAI ChatGPT API for v1 note generation
- LiteParse for supported document and image parsing

## License

Mianotes Web Service is licensed under GPL-3.0. See [LICENCE](LICENCE).
