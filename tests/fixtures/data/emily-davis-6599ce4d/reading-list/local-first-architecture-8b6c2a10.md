# Local-First Architecture

## Summary

Local-first architecture gives users direct ownership of their data by storing primary content in files that can be inspected, backed up, and moved. For Mianotes, Markdown files and JSON metadata make the system understandable even without the app running.

## Key Points

- The filesystem should be the source of truth for note content.
- SQLite should index files for fast list views and relationships.
- Stable paths reduce maintenance work and avoid expensive migrations.
- Background jobs may be needed for long parsing and AI generation tasks.

## Implementation Notes

- Do not scan the filesystem for normal note list API calls.
- Store permanent note paths in the `notes` table.
- Store source file paths in the `source_files` table.
- Keep comments in sidecar JSON files.

## Follow-Up

Design the repository layer so PostgreSQL can be introduced without rewriting API handlers.

