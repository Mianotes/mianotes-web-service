# Performance Review Skill

## Purpose

Review this codebase as a senior backend engineer with a performance and production-readiness focus:

Audit the working tree read-only. Do not modify files.

Look specifically for:

- Full-table or full-workspace scans on request paths
- N+1 queries and per-result follow-up queries
- Eager loading that multiplies rows across multiple child collections
- Python-side aggregation that should be done in SQL
- Missing pagination, limits, timeouts, or streaming
- Large in-memory I/O, including uploads, downloads, URL fetches, ZIP generation, and file parsing
- Missing or weak composite indexes for common filters and sorts
- Filesystem/database mismatches that create slow authorization checks
- Security issues that overlap with performance, especially SSRF, unbounded remote fetches, and public file access checks
- Maintainability issues that make performance fixes risky or hard to test

For each issue, include:

- Severity: Critical / High / Medium / Low
- File and line number or section
- Current behavior
- Why it matters in production
- Specific fix, preferably with a short code sketch when useful
- Expected impact

Then produce:

1. A "Best 20/80 Order" section with the safest implementation order.
2. Implementation tickets for the main fixes. Each ticket should include:
   - Goal
   - Scope
   - Acceptance Criteria
   - Expected Impact

Be harsh but practical. Prefer fixes that preserve the existing API behavior and response schemas. Call out where a suggested index or query change should be validated with `EXPLAIN QUERY PLAN` before committing to it.