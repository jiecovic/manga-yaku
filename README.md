# MangaYaku

MangaYaku is a personal sandbox for manga translation workflows: box detection, OCR,
and LLM translation with a local-first UI.

## Status

See `docs/STATUS.md` for stable vs experimental features and planned work.

## Features

- Manual speech-bubble annotation in the browser
- OCR via manga-ocr (local) or a multimodal LLM via the OpenAI API
- Automatic translation of individual bubbles
- JA->EN translation using OpenAI or a local OpenAI-compatible server
- Context handling for volume and page prompts
- Persistent page state stored in Postgres

## Experimental

- Box detection via YOLO/Ultralytics (train models in the UI)
- Agent translate page pipeline

See `docs/STATUS.md` for more detail.

## Stack

- Frontend: React + Vite + TypeScript
- Backend: FastAPI (Python)
- Database: Postgres + pgvector (Docker, reserved for future RAG)

## Quick Start

From repo root:

```powershell
docker compose up -d
npm run dev
```

This will set up backend and frontend dependencies if needed, then start:
- FastAPI at http://localhost:8101
- Vite at http://localhost:5174

## Configuration

Copy the example env files and adjust as needed:
- `frontend/.env.example` → `frontend/.env` (set `VITE_API_BASE`)
- `backend-python/.env.example` → `backend-python/.env` (set `OPENAI_API_KEY`, `DATABASE_URL`, etc.)

Optional overrides:
- `MANGAYAKU_BACKEND_PORT=8101`
- `MANGAYAKU_BACKEND_HOST=127.0.0.1`

## Troubleshooting

- Backend unreachable or DB unavailable: run `docker compose up -d` and restart the backend. `/api/health` returns `503` when the DB is down.
- OpenAI providers disabled: set `OPENAI_API_KEY` in `backend-python/.env` and restart the backend.
- Box detection shows no models: train a model first so weights exist under `training-data/runs`.

## Data

Page images live under:

```
data/volumes/<volume-id>/*.jpg|png|webp
```

Page state (boxes, OCR text, translations) is stored in Postgres.

## Datasets

### Manga109-s

The published box-detection model `yolo26s-text-v1` was trained using Manga109-s.
Dataset images are not redistributed in this repo. Dataset homepage:
[Manga109](http://www.manga109.org/en/).

You can train with Manga109-s using this framework, but you must download the dataset
yourself from the official site. You can also use it for local testing, but no sample
pages are included here due to licensing.

References:

1. Aizawa, K., Fujimoto, A., Otsubo, A., Ogawa, T., Matsui, Y., Tsubota, K., Ikuta, H. (2020).
   Building a Manga Dataset "Manga109" with Annotations for Multimedia Applications.
   IEEE MultiMedia, 27(2), 8–18. doi: 10.1109/MMUL.2020.2987895.
2. Matsui, Y., Ito, K., Aramaki, Y., Fujimoto, A., Ogawa, T., Yamasaki, T., Aizawa, K. (2017).
   Sketch-based Manga Retrieval using Manga109 Dataset.
   Multimedia Tools and Applications, 76(20), 21811–21838. doi: 10.1007/s11042-016-4020-z.

## Development

See `CONTRIBUTING.md` for development setup, linting/testing, and internal conventions.

## License

MIT License

