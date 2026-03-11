# MangaYaku

MangaYaku is an experimental sandbox for manga translation using AI.

It is where I experiment with text-box detection, OCR, LLM-based translation,
and workflow orchestration.

It also includes a simple chat agent built on the OpenAI Agents SDK and a
custom MCP server. The agent can inspect the active page image, discuss
translation choices, and call tools for things like page navigation, box
detection with a pretrained YOLO model, OCR with different profiles, and the
page-translation workflow.

It is not a polished product. The goal is to iterate on workflows, models, and
tooling in one local-first environment.

## What Works Today

Current supported paths:

- manual box editing in the browser
- building up a local volume from page images, including creating one from the
  frontend via clipboard paste
- box detection with persisted YOLO profiles; the frontend also exposes dataset
  preparation and training flows so you can train your own detectors locally
  (for example against Manga109-s, see [Datasets And Training](#datasets-and-training))
- OCR for a page or a single box, using `manga-ocr` or LLM-backed OCR profiles
- single-box translation
- full `page_translation` workflow: detect, OCR fanout, page translation,
  continuity merge, commit back to page state + context
- chat agent with MCP tools for page navigation, box inspection/editing, OCR,
  box detection, and page translation
- persisted page state, jobs, workflows, chat sessions, and settings in
  Postgres

Important current behavior:

- `page_translation` is the default page pipeline
- page reruns preserve existing boxes by default instead of wiping the page

## Stack

- frontend: React + Vite + TypeScript + Tailwind CSS
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

Runtime data lives in:

- `data/volumes/<volume-id>/...` for page images
- Postgres for volumes, pages, boxes, OCR text, translations, memory/context, jobs, and workflows
- `data/logs/` for debug artifacts and LLM call payload captures
- `training-data/` for prepared datasets and training runs
- `models/` for published model weights and manifests

## Datasets And Training

The published text-box detector `yolo26s-text-v1` was trained on Manga109-s.
Dataset images are not redistributed here, but you can still prepare datasets,
train your own detection models, and publish model manifests/weights locally.
See [docs/DATASETS.md](docs/DATASETS.md) for dataset notes and references,
including:

- Aizawa et al. (2020), *Building a Manga Dataset "Manga109" with Annotations
  for Multimedia Applications*
- Matsui et al. (2017), *Sketch-based Manga Retrieval using Manga109 Dataset*

## Development

Main developer commands:

```text
npm run lint
npm run lint:fix
npm run test:backend
```

`npm run lint` is the main repo quality gate. It runs:

- backend Ruff lint
- backend Ruff format check
- backend Pyright
- frontend TypeScript typecheck
- frontend Biome lint/format/import checks

Deeper contributor/setup guidance lives in [CONTRIBUTING.md](CONTRIBUTING.md).

## Docs

Start here depending on what you need:

- [ARCHITECTURE.md](ARCHITECTURE.md)
  - current system architecture, boundaries, workflows, jobs, idempotency, MCP
- [backend-python/README.md](backend-python/README.md)
  - backend-specific notes
- [CONTRIBUTING.md](CONTRIBUTING.md)
  - setup, linting, testing, repo conventions

Backend API docs when running locally:

- Swagger UI: http://localhost:8101/docs

## License

MIT License
