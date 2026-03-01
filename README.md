# MangaYaku

MangaYaku is a manga translation workflow app with a local-first UI for box detection,
OCR, and LLM-assisted translation.

## Status

See `docs/STATUS.md` for stable vs experimental features and planned work.
Current default page pipeline is `agent_translate_page`; standalone
`translate_page` jobs are disabled.

## Features

- Manual speech-bubble annotation in the browser
- OCR via manga-ocr (local) or a multimodal LLM via the OpenAI API
- Single-box translation jobs via OpenAI or a local OpenAI-compatible server
- Context handling for volume and page prompts
- Persistent page state stored in Postgres

## Stack

- Frontend: React + Vite + TypeScript
- Backend: FastAPI (Python)
- Database: Postgres + pgvector (Docker)

## Quick Start

From repo root:

If you use published model weights under `models/`, fetch LFS objects first:

```text
git lfs install
git lfs pull
```

Start app services:

```text
docker compose up -d

# one-time setup
npm run setup

# run backend + frontend
npm run dev
```

`npm run dev` uses the scripts in `scripts/` and starts:
- FastAPI at http://localhost:8101
- Vite at http://localhost:5174

Run separately:

```text
npm run dev:backend
npm run dev:frontend
```

## Configuration

Copy the example env files and adjust as needed:
- copy `frontend/.env.example` to `frontend/.env` (set `VITE_API_BASE`, e.g. `http://127.0.0.1:8101` direct backend or `http://localhost:5174` dev proxy)
- copy `backend-python/.env.example` to `backend-python/.env` (set `OPENAI_API_KEY`, `DATABASE_URL`, etc.)

Optional overrides:
- `MANGAYAKU_BACKEND_PORT=8101`
- `MANGAYAKU_BACKEND_HOST=127.0.0.1`

## Data

Page images live under:

```
data/volumes/<volume-id>/*.jpg|png|webp
```

Page state (boxes, OCR text, translations) is stored in Postgres.

## Datasets

### Manga109-s

The published box-detection model `yolo26s-text-v1` was trained using Manga109-s.
Dataset images are not redistributed in this repo.

You can train with Manga109-s using this framework, but you must download the dataset
yourself from the official site. You can also use it for local testing, but no sample
pages are included here due to licensing. See `docs/DATASETS.md` for links and references.

## Development

See `CONTRIBUTING.md` for development setup, linting/testing, and internal conventions.

## See Also

- `docs/STATUS.md`
- `backend-python/README.md`
- `CONTRIBUTING.md`
- Swagger UI: http://localhost:8101/docs

## License

MIT License
