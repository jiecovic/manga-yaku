# MangaYaku

MangaYaku is an experimental sandbox for manga translation workflows.

The repo is a place to explore different ways of doing things like:

- page and text-box detection
- OCR with local or model-backed pipelines
- translation with different model/runtime setups
- agent tooling and tool protocols such as MCP
- persisted jobs, workflows, and orchestration
- training and dataset-prep loops for improving detection quality

It is not a polished product. The point is to iterate on workflow design,
model/runtime choices, and supporting tooling in one local-first environment.
OpenAI-backed paths are the main supported LLM integration today, but part of
the reason the project uses MCP and a clearer tool/runtime split is to keep room
for experimenting with other providers later.

## What Works Today

Current supported paths:

- manual box editing in the browser
- box detection with persisted YOLO profiles
- OCR for a page or a single box
- single-box translation
- full `page_translation` workflow:
  - detect
  - OCR fanout
  - page-level translation
  - continuity merge
  - commit back to page state + context
- chat agent with MCP tools for page navigation, box inspection/editing, OCR,
  box detection, and page translation
- persisted jobs/workflows in Postgres
- dataset preparation and model training for box-detection workflows

Important current behavior:

- `page_translation` is the default page pipeline
- page reruns preserve existing boxes by default instead of wiping the page

## Stack

- frontend: React + Vite + TypeScript
- backend: FastAPI (Python)
- database: Postgres + pgvector
- models/runtime:
  - YOLO for box detection
  - manga-ocr or multimodal LLM OCR
  - OpenAI and local OpenAI-compatible translation/OCR paths
  - OpenAI Agents SDK + local MCP server for the chat agent

## Quick Start

Requirements:

- Python 3.10+
- Node.js 20.20.x
- npm 11.10.x
- Docker
- Git LFS if you want published model weights under `models/`
- `OPENAI_API_KEY` if you want to use the OpenAI-backed OCR, translation, or chat-agent paths

From repo root:

```text
git lfs install
git lfs pull

npm run setup
npm run dev
```

That starts:

- backend: http://localhost:8101
- frontend: http://localhost:5174

Useful alternatives:

```text
npm run dev:backend
npm run dev:frontend
npm run dev:backend:noreload
docker compose up --build -d
docker compose logs -f
docker compose down
```

`docker compose up --build -d` starts the full dev stack:

- frontend: http://localhost:5174
- backend: http://localhost:8101
- postgres: localhost:5433

If you want OpenAI-backed OCR, translation, or chat-agent paths in Docker
without editing `backend-python/.env`, export the key in your shell before
starting Compose:

```text
export OPENAI_API_KEY=sk-...
docker compose up --build -d
```

The host-based path (`npm run dev`) is still useful when you already have local
Python/Node tooling set up and only want Postgres in Docker.

## Configuration

Copy the example env files first:

- `frontend/.env.example` -> `frontend/.env`
- `backend-python/.env.example` -> `backend-python/.env`

Backend config you will usually care about first:

- `OPENAI_API_KEY`
- `DATABASE_URL`
- `AGENT_MODEL`
- `AGENT_MCP_SERVER_URL`
- `LOCAL_OPENAI_BASE_URL` / `LOCAL_OPENAI_MODEL` if you use a local compatible server

Optional dev overrides:

- `MANGAYAKU_BACKEND_PORT=8101`
- `MANGAYAKU_BACKEND_HOST=127.0.0.1`

## Data Layout

Runtime data lives in a few main places:

- `data/volumes/<volume-id>/...`
  - page images
- Postgres
  - volumes, pages, boxes, OCR text, translations, memory/context, jobs, workflows
- `data/logs/`
  - debug artifacts and LLM call payload captures
- `training-data/`
  - prepared datasets and training runs
- `models/`
  - published model weights and manifests

## Datasets And Training

The published text-box detector `yolo26s-text-v1` was trained on Manga109-s.
Dataset images are not redistributed in this repo.

You can still use this repo to:

- prepare datasets
- train your own detection models
- publish model manifests/weights locally

See [docs/DATASETS.md](/home/thomas/projects/manga-yaku/docs/DATASETS.md) for the dataset notes.

## Development

Main developer commands:

```text
npm run lint
npm run test:backend
```

Deeper contributor/setup guidance lives in:

- [CONTRIBUTING.md](/home/thomas/projects/manga-yaku/CONTRIBUTING.md)

## Docs

Start here depending on what you need:

- [ARCHITECTURE.md](/home/thomas/projects/manga-yaku/ARCHITECTURE.md)
  - current system architecture, boundaries, workflows, jobs, idempotency, MCP
- [backend-python/README.md](/home/thomas/projects/manga-yaku/backend-python/README.md)
  - backend-specific notes
- [CONTRIBUTING.md](/home/thomas/projects/manga-yaku/CONTRIBUTING.md)
  - setup, linting, testing, repo conventions

Backend API docs when running locally:

- Swagger UI: http://localhost:8101/docs

## License

MIT License
