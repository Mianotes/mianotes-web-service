# Feature requests

This document collects product and architecture ideas that would make Mianotes better, but are not part of the current release scope.

## Parallel job processing

Mianotes currently creates a database job for each upload or URL import, then schedules that job through the in-process job runner. Jobs are visible as queued, running, succeeded, or failed in the Console, but Mianotes does not yet have a dedicated worker pool that claims and processes multiple queued jobs at the same time.

Parallel processing would be useful for larger installs, especially teams running Mianotes on machines with plenty of CPU and memory.

### Proposed approach

Add a real `JobWorkerPool` that can run more than one job at a time.

The worker count should be configurable with something like:

```text
MIANOTES_JOB_WORKERS=2
```

The default should stay at `1` so small local installs remain predictable.

A later `auto` mode could choose a conservative worker count based on the host machine, for example using two workers on machines with 16 GB or more RAM, capped at a small number such as four.

### Design requirements

- API requests should continue to create jobs as `queued`.
- Workers should claim queued jobs atomically so two workers cannot process the same job.
- Each job should run with its own SQLAlchemy session.
- Each job should run with its own workspace context.
- Parser temporary files should stay isolated per job.
- Database transactions should stay short; ffmpeg, OCR, MarkItDown, and model calls should not hold long-running write transactions.
- Shutdown should be graceful. Workers should stop accepting new jobs and any interrupted jobs should be marked clearly on next startup.

### SQLite considerations

SQLite can support this if writes are kept short and well scoped. Parsing work is slow, but most of that time should happen outside database transactions. Workers should only write when they need to update job status, append logs, or persist note text.

### UI considerations

The Console should show the real number of active jobs, for example:

```text
2 active
```

This should reflect actual worker activity rather than just the number of jobs with a `running` status.

### Acceptance criteria

- Admins can configure the number of job workers.
- Two or more jobs can run concurrently when configured.
- Workers cannot claim the same queued job twice.
- Jobs stay scoped to the correct workspace.
- Failed jobs still update the related note and Console logs correctly.
- Existing single-worker behaviour remains the default.
- Tests cover concurrent claiming, workspace isolation, successful jobs, failed jobs, and interrupted jobs.
