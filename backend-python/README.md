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

- Workflow policy is owned by `core/workflows/agent_translate_page/*`.
  This includes stage order, transition rules, cancellation behavior, and
  completion/failure semantics.
- Workers in `infra/jobs/*` execute queued task units and persist status/results.
  Workers do not define business workflow policy.

## Jobs execution modes

Source of truth: `infra/jobs/job_modes.py`.

- `db-task`:
  `ocr_page`, `ocr_box`, `translate_box`
  persisted in `workflow_runs` + `task_runs`, consumed by DB workers.
- `memory-only`:
  `box_detection`, `prepare_dataset`, `train_model`
  handled via in-memory `JobStore`.
- `hybrid`:
  `agent_translate_page`
  queued through memory runtime while workflow state is persisted in DB.

## Data flow (high-level)

1. API route validates request and creates a workflow/job.
2. For DB-task workflows, task rows are created in Postgres.
3. Workers claim tasks, execute OCR/translation, and persist task outcomes.
4. Workflow status/progress is updated and exposed through jobs APIs/SSE.
5. Final results are written back to page state tables and surfaced in the UI.
