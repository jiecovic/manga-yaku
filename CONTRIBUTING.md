# Contributing

Thanks for your interest in MangaYaku. This is primarily a personal project and
my review bandwidth is limited. You are welcome to open issues or PRs, but I may
be slow to respond or may not be able to merge everything. For larger changes,
please open an issue first to confirm direction.

## Development Setup

Requirements:
- Python 3.10+
- Node.js 20.20.x
- npm 11.10.x
- Docker (for Postgres)
- Git LFS (for published model weights under `models/`)
- `OPENAI_API_KEY` if you want to use the OpenAI-backed OCR, translation, or chat-agent paths

Tooling consistency:
- Use `.nvmrc` (`nvm use`) before installing dependencies.
- Prefer `npm ci` for clean/reproducible installs (especially in CI).

Model weights setup:

```text
git lfs install
git lfs pull
```

Common commands:

```text
npm run setup
npm run dev
npm run dev:backend
npm run dev:backend:noreload
npm run dev:frontend
npm run start:backend
```

Backend only:

```text
cd backend-python
python -m uvicorn app:app --port 8101 --reload
python -m uvicorn app:app --port 8101
```

## Codebase Overview

This repo is split into a Vite/React frontend and a FastAPI backend with a shared
Postgres database.

High-level structure:

```
frontend/        # React UI (Vite + TS)
backend-python/  # FastAPI app + core logic
data/            # runtime data (volumes, logs)
training-data/   # local datasets + runs (gitignored)
models/          # published model weights + manifests
docs/            # datasets, plans, and deeper project notes
```

Backend layout (core vs infra):

- `backend-python/api/` — FastAPI routers + schemas (HTTP surface area).
- `backend-python/core/` — business logic and workflow orchestration (usecases, profiles, detection/ocr engines, page-translation workflow).
- `backend-python/infra/` — DB, LLM clients, jobs, IO adapters.
- `backend-python/app.py` — app wiring and router registration.

Frontend layout:

- `frontend/src/components/` — UI screens and panels.
- `frontend/src/context/` — global state (settings, jobs, health, library).
- `frontend/src/hooks/` — workflow helpers (job actions, library state).
- `frontend/src/api/` — typed client wrappers around backend endpoints.
- `frontend/src/ui/` — design tokens + primitives.

## Database Layout (Postgres)

The database schema lives in `backend-python/infra/db/db.py` and is created via
`Base.metadata.create_all()` during init.

Core tables:

- `volumes` — manga volumes (name, created_at).
- `pages` — pages within volumes (filename, page_index).
- `boxes` — detected/annotated boxes (type, geometry, source, run_id).
- `text_box_contents` — OCR text + translations per box.
- `box_detection_runs` — metadata for each detection run (model + params).
- `volume_context` — rolling summaries, character/glossary context per volume.
- `page_context` — per-page summaries and snapshots.
- `agent_sessions` / `agent_messages` — optional chat-style agent history.
- `app_settings` — persisted settings (e.g., detection thresholds, defaults).
- `ocr_profile_settings` — per-OCR profile overrides for agent use.
- `translation_profile_settings` — per-translation profile overrides for single-box translation.
- `page_translation_settings` — default model/params for the page-translation workflow.
- `workflow_runs` — persisted workflow jobs (ocr/translate/agent pipelines).
- `task_runs` — child tasks for workflow runs (stage/model/box level execution).
- `task_attempt_events` — per-attempt telemetry (latency/tokens/errors).
- `llm_call_logs` — request/response metadata and payload references for debugging.

Indexes and constraints are defined directly in `db.py`.

Relationships (high-level):

- `volumes` -> `pages` (1:N)
- `pages` -> `boxes` (1:N)
- `boxes` -> `text_box_contents` (1:1)
- `box_detection_runs` -> `boxes` (1:N via `boxes.run_id`)
- `volumes` -> `volume_context` (1:1)
- `pages` -> `page_context` (1:1)
- `volumes` -> `agent_sessions` -> `agent_messages`
- `workflow_runs` -> `task_runs` -> `task_attempt_events`

Important constraints:

- `pages` unique (`volume_id`, `filename`)
- `boxes` unique (`page_id`, `box_id`) and constrained `type`/`source`
- `page_translation_settings` is a singleton row (`id = 1`)

## Key Workflows

Box detection:
- UI picks a detection profile from the page view or falls back to the default page-translation detection setting.
- Backend loads a YOLO profile and writes boxes to Postgres.

OCR:
- Uses local manga-ocr by default, optional OpenAI vision OCR.
- OCR results are stored per box in Postgres.

Page translation:
- Detects boxes → runs OCR fanout (multi-profile child tasks) → page translate stage
  (image + OCR candidates) → merge stage (continuity updates) → commit to Postgres.
- Default LLM model and merge/runtime knobs are configured in Settings → Page Translation Workflow.

Jobs model:
- Workflow-backed jobs (`ocr_box`, `ocr_page`, `translate_box`, `page_translation`) are persisted
  in Postgres (`workflow_runs`/`task_runs`) and can be reloaded after backend restart.
- Utility workflows (`box_detection`, `prepare_dataset`, `train_model`) are also persisted in
  Postgres and executed by the DB utility worker.
- `page_translation` create requests support `Idempotency-Key` and same-page
  active dedupe (`volumeId + filename`) to avoid duplicate runs from retries/double-clicks.
- `forceRerun` can request a fresh run, but does not allow parallel duplicate runs
  for the same page while one is already queued/running.

Training:
- Raw datasets live under `training-data/sources/` (ignored).
- Prepared YOLO datasets under `training-data/prepared/` (ignored).
- Training runs saved to `training-data/runs/`.
- Published model weights and manifests live in `models/`.

## Linting

```text
npm run lint
npm run lint:backend
npm run lint:frontend
npm run format:backend:check
```

## Pre-commit

This repo includes a `.pre-commit-config.yaml` that runs:
- `ruff` (backend)
- `pyright` (backend types)
- `tsc --noEmit` (frontend types)
- `eslint` (frontend)

Setup:

```text
npm run setup
python -m pip install pre-commit
pre-commit install
```

Run on demand:

```text
pre-commit run --all-files
```

## Testing (backend)

```text
cd backend-python
source .venv/bin/activate
pytest -q tests
```

Notes:
- The test suite defaults to offline Hugging Face/Transformers mode via
  `tests/conftest.py` (`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`).
- For quick local checks, you can run focused files such as:
  `pytest -q tests/core/page_translation/test_page_translation_state_machine.py tests/core/usecases/test_retry_policies.py`.
- Test module coverage map and targeted command groups are documented in:
  `backend-python/tests/README.md`.

## Backend Package Conventions

- Keep `__init__.py` files docstring-only for internal packages.
- Use `__all__` and re-exports only for intentional public APIs
  (for example: `core/usecases/*`, `infra/llm`, `infra/logging`).
- Avoid side-effectful logic in `__init__.py` (I/O, env parsing, config resolution).

## Local OpenAI-Compatible Server

- `LOCAL_OPENAI_BASE_URL` and `LOCAL_OPENAI_MODEL` are optional.
- The local translation profile is enabled only when the base URL is reachable.

## Frontend UI Tokens

The shared UI layer lives under `frontend/src/ui`.

- `tokens.ts` holds reusable Tailwind class strings.
- `primitives.tsx` provides small components that wrap those tokens.

Conventions:
- Prefer primitives for new UI, then fall back to tokens.
- If a token string is reused 3+ times, consider a primitive or a new token.
- Keep token names descriptive and grouped by domain.

## Training Data

Local training datasets live under `training-data/` and are not committed.

Structure:

```
training-data/
  sources/     # raw datasets (ignored)
  prepared/    # generated YOLO-ready datasets (ignored)
```

Manga109s layout:

```
training-data/sources/manga109s/
  images/
  annotations/
  annotations_COO/
  annotations_Manga109Dialog/
```
