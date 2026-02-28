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

Source of truth: `infra/jobs/job_modes.py`.
