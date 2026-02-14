# Agent North Star

## Abstract
Build an in-UI, volume-scoped agent that can translate manga end-to-end with minimal supervision.
The default path is multimodal (image + OCR + context), and every action is logged as jobs with
short step labels, status, and progress. Start sequential and safe, then expand to planning,
parallelization, and rich lore tracking.

## Phases (Summary)
- Phase 0: Hybrid UI + presets, sequential execution, jobs-as-log, multimodal translation.
- Phase 1: Task runner with explicit step queue and progress; structured memory writes (characters/glossary).
- Phase 2: Planner mode (plan preview + confirm), richer refinement loops, better box ordering heuristics.
- Phase 3: Parallel batch translation with reconciliation, lore visualization (list + graph view).
- Phase 4: Optional web lookup tool, advanced RAG over history/notes, cross-page consistency checks.

## Phase 0 (Baseline Agent)
- Hybrid UI: compact presets + optional chat panel.
- Presets:
  - Recon + Translate (default): detect -> OCR -> multimodal translate + character/lore extraction.
  - Refine Existing: use current translations + image + memory to improve consistency.
- Jobs pane is the action log (agent steps + tool calls), no chain-of-thought storage.
- Sequential execution only; stop/cancel always available.

## Phase 1 (Task Runner + Structured Memory)
- Task runner to queue steps and show progress per step.
- Structured memory writes:
  - Characters (name, aliases, gender, role, speech style, notes)
  - Glossary (term -> preferred translation)
  - Relationships (character <-> character or entity)
  - Volume summary (short, editable)

## Phase 2 (Planner Mode + Refinement)
- Planner mode: preview steps, confirm/adjust, then execute.
- Refinement loops for translation quality and consistency.
- Improved box ordering heuristics.

## Phase 3 (Batch + Lore Visualization)
- Parallel batch translation with reconciliation.
- Lore tab: list view + optional graph view of relationships.
- Show which memory items were used in recent runs.

## Phase 4 (Web + Advanced RAG)
- Optional web lookup tool (opt-in) to enrich lore.
- Advanced RAG over long-form history/notes for speaker/scene disambiguation.
- Cross-page consistency checks.

## Requirements and Principles
- Volume-scoped sessions only (no cross-volume memory by default).
- Agent can switch pages; UI must reflect active page.
- No chain-of-thought storage; store short step labels + results only.
- Sequential by default; parallelization later when safe and useful.
- Provide a clear stop control to cancel current step and clear queue.
- Agent loop is bounded by max steps and runtime (prevent runaway runs).

## Tool Interface (MVP)
- get_current_page, set_current_page
- list_pages(volume_id)
- detect_boxes(page, task, model_id)
- ocr_page(page, profile_id)
- translate_page(page, profile_id, use_context)
- reorder_boxes(page, strategy)
- set_box_text, set_box_translation
- read_page_image (or get_page_image_url)
- get_volume_context / set_volume_context
- read/write volume memory (characters, glossary, relationships)

## Image Handling
- Send page image via backend URL to the model.
- Resize before sending (max long edge 1280-1536 px, no upscaling, JPEG quality ~80).
- Start with full-page image only; add targeted crops later if needed.

## Model Strategy
- Agent brain uses OpenAI cloud (Responses API when possible).
- Local LLM remains a tool (optional) rather than the primary agent.

## Agent Loop (How It Runs)
- Build context (current page, volume memory, recent chat, tool results).
- Call the model with tool schemas.
- If tool call: execute tool, log job entry, append result, loop.
- If final response: stop and persist message.
- Limits: max steps per run, max runtime per run, and per-run tool cap.
