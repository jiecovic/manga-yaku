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

From repo root:

```text
git lfs install
git lfs pull

docker compose up -d
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
```

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
