# Status

## Stable
- Local-first UI for manual box annotation
- Volume/page library backed by Postgres
- Page context and memory storage
- OCR via manga-ocr (local)
- Translation via OpenAI (requires API key)
- Jobs panel (in-memory)

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
- Jobs are in-memory and reset on backend restart.
- Box detection requires trained model weights in `training-data/runs`.
