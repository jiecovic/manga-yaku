# Jobs Infra

Purpose: runtime and persistence plumbing for background jobs.

## Modes

- `db-task`:
  `ocr_page`, `ocr_box`, `translate_box`
  Stored in `workflow_runs` + `task_runs`, processed by DB workers.

- `memory-only`:
  `box_detection`, `prepare_dataset`, `train_model`
  Stored in in-memory `JobStore`, processed by in-process handlers.

- `hybrid`:
  `agent_translate_page`
  Enqueued via memory queue, with workflow state persisted in DB.
  Submission is deduped per page (`volumeId + filename`) while active.

Source of truth: `infra/jobs/job_modes.py`.

## Idempotency behavior

For `agent_translate_page` create requests:

- `Idempotency-Key` is supported at the API layer.
- Same key + same payload reuses the existing created job id.
- Same key + different payload returns `409`.
- `forceRerun` disables idempotency replay for intentional reruns, while
  active-page dedupe still avoids parallel duplicates.

## Responsibility split

- Core workflow logic:
  `core/workflows/agent_translate_page/*`
  owns state transitions, stage ordering, and business decisions.
- Infra workers:
  `infra/jobs/db_ocr_worker.py` and `infra/jobs/db_translate_worker.py`
  poll queued task rows, execute work, and persist task/workflow progress.
