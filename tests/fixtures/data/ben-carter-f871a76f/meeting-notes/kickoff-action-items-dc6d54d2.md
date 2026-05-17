# Kickoff Action Items

## Summary

The kickoff clarified that Mianotes should start with a filesystem-first backend and a simple REST API. The first release should prove the complete flow from user creation to Markdown note storage before adding advanced ingestion.

## Decisions

- Use FastAPI for the backend API.
- Use SQLite for v1 indexing.
- Store generated notes as Markdown files.
- Store comments as JSON sidecars.
- Keep PostgreSQL support as an architectural path, not a v1 requirement.

## Action Items

- Implement user and token APIs.
- Add topic CRUD.
- Build `POST /api/notes/from-text` as the first note creation path.
- Deploy each working slice to the Arduino box.

## Risks

- Document parsing can become slow for large files.
- API token handling needs to be clear for both the web app and developers.

