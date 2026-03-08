# Backend Architecture

This document gives a technical overview of the Python backend.

## Layering

- `core/`:
  business logic, workflow policy, state transitions, domain ports.
- `infra/`:
  concrete adapters (DB, LLM clients, files/images, job runtime/workers).
- `api/`:
  HTTP transport (FastAPI routes, request/response schemas, service orchestration).

See also:
- `core/README.md`
- `infra/README.md`
- `infra/jobs/README.md`

## Workflow logic vs worker execution

The important split is:

- Workflow policy is owned by `core/workflows/page_translation/*`.
  This includes stage order, transition rules, cancellation behavior, and
  completion/failure semantics.
- Workers in `infra/jobs/*` execute queued task units and persist status/results.
  Workers do not define business workflow policy.

## Jobs execution modes

Source of truth: `infra/jobs/job_modes.py`.

- `db-task`:
  `ocr_page`, `ocr_box`, `translate_box`
  persisted in `workflow_runs` + `task_runs`, consumed by DB workers.
- `utility-workflow`:
  `box_detection`, `prepare_dataset`, `train_model`
  persisted in `workflow_runs` + `task_runs`, consumed by the DB utility worker.
- `workflow-orchestrator`:
  `page_translation`
  persisted in `workflow_runs` + `task_runs`, consumed by the DB page-translation worker.

## Page translation submission semantics

`POST /api/jobs/page_translation` uses request de-duplication rules:

- Active-page dedupe:
  if the same `volumeId + filename` already has a `queued/running` agent run,
  the API returns the existing job/workflow id instead of creating another run.
- Optional idempotency:
  clients may send `Idempotency-Key`; the backend stores key + request hash.
  same key + same payload replays existing id; same key + different payload
  returns `409`.
- `forceRerun`:
  bypasses idempotency replay for intentional fresh runs, but active-page dedupe
  still prevents parallel duplicate execution for the same page.

## Data flow (high-level)

1. API route validates request and creates a persisted workflow/job.
2. Workflow/task rows are created in Postgres.
3. Workers claim tasks, execute work, and persist task outcomes.
4. Workflow status/progress is updated and exposed through jobs APIs/SSE.
5. Final results are written back to page state tables and surfaced in the UI.
