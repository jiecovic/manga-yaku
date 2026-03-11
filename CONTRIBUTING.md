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
- Docker (for Postgres or the full Docker dev stack)
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
docker compose up --build -d
docker compose logs -f
docker compose down
```

Host-based dev:

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

This repo is split into a Vite/React frontend and a FastAPI backend with a
shared Postgres database.

High-level structure:

```
frontend/        # React UI (Vite + TS)
backend-python/  # FastAPI app + core logic
data/            # runtime data (volumes, logs)
training-data/   # local datasets + runs (gitignored)
models/          # published model weights + manifests
docs/            # datasets, plans, and deeper project notes
```

Backend layout:

- `backend-python/api/` — FastAPI routers + schemas (HTTP surface area).
- `backend-python/core/` — business logic and workflow orchestration.
  - `usecases/` contains reusable capabilities such as OCR, translation, box detection, settings, and chat-agent runtime helpers.
  - `workflows/` contains longer-running orchestration such as the multi-stage `page_translation` pipeline.
- `backend-python/infra/` — DB, LLM clients, jobs, IO adapters.
- `backend-python/app.py` — app wiring and router registration.

Frontend layout:

- `frontend/src/components/` — UI screens and panels.
- `frontend/src/context/` — global state (settings, jobs, health, library).
- `frontend/src/hooks/` — workflow helpers.
- `frontend/src/api/` — typed client wrappers around backend endpoints.
- `frontend/src/ui/` — design tokens + primitives.

For the current runtime and data model, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Linting

```text
npm run lint
npm run lint:fix
npm run lint:backend
npm run lint:frontend
npm run lint:types
npm run typecheck:frontend
npm run format:backend:check
npm run format:frontend:check
```

## Pre-commit

This repo includes a `.pre-commit-config.yaml` that runs:

- `ruff` (backend)
- `pyright` (backend types)
- `npm run typecheck:frontend` (frontend TypeScript build/typecheck)
- `biome check` (frontend lint + format + import sorting)

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
- If you use Docker and want OpenAI-backed OCR, translation, or chat-agent
  paths without editing `backend-python/.env`, export `OPENAI_API_KEY` in your
  shell before starting `docker compose`.

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
The usual layout is:

```text
training-data/
  sources/
  prepared/
  runs/
```

See [docs/DATASETS.md](docs/DATASETS.md) for the current Manga109-s notes and
references used by the box-detection training flow.
