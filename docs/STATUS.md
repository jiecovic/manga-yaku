# Status

## Stable
- Local-first UI for manual box annotation
- Volume/page library backed by Postgres
- Page context and memory storage
- OCR via manga-ocr (local)
- Translation via OpenAI (requires API key)
- Jobs panel (hybrid: persisted workflow jobs + in-memory utility jobs)

## Experimental
- Agent translate page workflow
- Training UI (dataset prep + model training)
- Box detection (requires trained model weights)
- Agent translate debug logs

## Planned
- Volume-wide agent orchestration
- Planner mode and parallel execution
- Lore visualization and consistency checks
- RAG/embedding memory with pgvector (summaries, translation memory, orchestration aids)
- Optional fine-tuning experiments

## Notes
- Workflow jobs are persisted in Postgres (`workflow_runs`, `task_runs`, `task_attempt_events`).
- In-memory utility jobs still reset on backend restart.
- Box detection requires trained model weights in `training-data/runs`.
