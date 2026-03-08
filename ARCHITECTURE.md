# Architecture

This document describes how MangaYaku works today.

It is intentionally code-oriented: it reflects the current implementation in
`backend-python/`, the mounted MCP server, the persisted workflow runtime, and
the current database model.

## System Overview

At a high level the system is:

- frontend: React/Vite UI
- backend: FastAPI app in `backend-python/app.py`
- database: Postgres
- filesystem: page images, model weights, prepared datasets, training runs, and
  debug/log artifacts on disk under `data/`, `models/`, and `training-data/`

The backend starts a single process that contains:

- the main FastAPI API surface
- the mounted MCP server at `/api/mcp`
- the in-process jobs runtime
- DB-backed workers for OCR, translation, utility jobs, and page translation

The backend process is therefore both:

- the HTTP/API server
- the MCP server
- the worker supervisor

It is not split into separate deployable services today.

## Package Boundaries

The important backend boundaries are:

- `backend-python/api/`
  - HTTP routers, request/response schemas, and thin service adapters
- `backend-python/core/`
  - business logic
  - `usecases/` contains reusable capabilities and runtime helpers
  - `workflows/` contains long-running orchestration built on those capabilities
- `backend-python/infra/`
  - database access
  - worker/runtime plumbing
  - provider SDK integration
  - filesystem/logging helpers
- `backend-python/mcp_server/`
  - MCP server construction, MCP request context, and MCP tool registration

The most important conceptual distinction is:

- `usecases` answer: "How does one capability work?"
- `workflows` answer: "How do multiple capabilities run together as one job?"

That is why `page_translation` exists in both:

- `core/usecases/page_translation/`
  - prompt construction
  - structured LLM calls
  - parsing/normalization
  - runtime diagnostics
- `core/workflows/page_translation/`
  - detect -> OCR fanout -> translate -> commit orchestration
  - persisted workflow state transitions
  - progress, cancellation, and terminal outcomes

## Runtime Bootstrap

The main application entrypoint is `backend-python/app.py`.

On startup it does the following:

1. configures logging
2. binds domain ports
3. optionally initializes the database schema
4. initializes OCR runtime
5. starts the jobs runtime
6. starts the MCP session manager
7. mounts all API routers under `/api`
8. mounts the MCP ASGI app under `/api/mcp`

Important consequence:

- MCP is not a separate service by default
- the chat agent connects back to the same backend process over Streamable HTTP

## What Is Stored In Postgres

The current schema is defined in `backend-python/infra/db/db.py`.

The main table groups are:

### Content and Page State

- `volumes`
  - logical manga volumes
- `pages`
  - page identity per volume, including `filename` and `page_index`
- `boxes`
  - box geometry and metadata
  - `type` is one of `text|panel|face|body`
  - `source` is one of `manual|detect`
- `text_box_contents`
  - OCR text, translation, note, language, confidence for each text box
- `box_detection_runs`
  - audit rows for box-detection executions, including model/version/path/hash

This is the persisted source of truth for page state in the editor.

### Narrative Memory / Context

- `volume_context`
  - rolling story summary, active characters, open threads, glossary
- `page_context`
  - page summary, image summary, manual notes, per-page character/thread/glossary snapshot

These are what the UI and agent refer to as persisted "memory" or context.

### Agent Chat

- `agent_sessions`
  - one row per chat session
  - includes persisted `model_id`
- `agent_messages`
  - persisted chat history with `role`, `content`, and `meta`

### Settings

- `app_settings`
  - generic key/value registry
  - used for global knobs like OCR parallelism
- `ocr_profile_settings`
  - DB-backed overrides for OCR profiles
- `translation_profile_settings`
  - DB-backed overrides for translation profiles
- `page_translation_settings`
  - singleton page-translation runtime settings

Important detail:

- code/env still defines base defaults and available profiles/models
- DB stores overrides on top of those defaults
- effective runtime settings are resolved at runtime

### Jobs and Workflows

- `workflow_runs`
  - top-level durable workflow/job rows
- `task_runs`
  - child tasks inside a workflow
- `task_attempt_events`
  - per-attempt audit rows for OCR/translation/page-translation stages
- `idempotency_keys`
  - request idempotency claims and finalized resource ids

### LLM Observability

- `llm_call_logs`
  - metadata for each logged OpenAI call:
    - provider/api/component
    - model
    - workflow/task/job ids
    - token counts
    - finish reason
    - request/response excerpts
    - path to full payload artifact on disk

The full redacted payloads are also written to disk under `data/logs/llm_calls/`.

## Jobs: What They Are And What They Are Not

The jobs UI is a control-plane view, not a Kafka-style event log.

Today the jobs pane is built from:

- persisted `workflow_runs` projected into UI-friendly `JobPublic` rows
- any in-memory jobs still present in `JobStore`

The merge happens in `backend-python/api/services/jobs_workflow_helpers.py`.

What jobs are:

- a unified user-facing snapshot of work in progress and recent work
- backed mostly by persisted workflow rows
- streamed to the UI over SSE from `/api/jobs/stream`

What jobs are not:

- an append-only event table
- a replayable message bus
- a `LISTEN/NOTIFY` event stream

`JobStore` still exists in `backend-python/infra/jobs/store.py`, but today it is
primarily:

- an in-process registry for any memory jobs
- a signal/broadcast layer for SSE updates
- a place to keep some live runtime metadata like log paths

The durable source of truth for user-visible long-running work is Postgres.

## Job Modes

Canonical job mode boundaries live in `backend-python/infra/jobs/job_modes.py`.

Current persisted job families:

- `db-task`
  - `ocr_page`
  - `ocr_box`
  - `translate_box`
  - stored in `workflow_runs` + `task_runs`
  - executed by DB workers
- `utility-workflow`
  - `box_detection`
  - `prepare_dataset`
  - `train_model`
  - one workflow row plus one task row
  - executed by the DB utility worker
- `workflow-orchestrator`
  - `page_translation`
  - one durable workflow run whose business logic lives in `core/workflows/page_translation`
  - executed by the DB page-translation worker

## Worker / Runtime Model

The jobs runtime starts in `backend-python/infra/jobs/runtime.py`.

It supervises:

- in-memory `job_worker(STORE)`
- DB page-translation worker supervisor
- DB OCR worker supervisor
- DB translate worker supervisor
- DB utility worker supervisor

On startup it also marks running `page_translation` workflows interrupted so
restart behavior is explicit instead of leaving stale "running" rows behind.

### Task Claiming and Recovery

The shared task-claiming API lives in `backend-python/infra/jobs/workflow_repo.py`.

Claiming rules:

- tasks are selected with `SELECT ... FOR UPDATE SKIP LOCKED`
- a claimed task moves to `running`
- the parent workflow moves to `running` if needed
- `lease_until` is set for task ownership

Recovery rules:

- lease expiry can requeue stale running tasks
- startup recovery can move interrupted tasks back to `queued`
- canceled workflows cause pending tasks to be canceled instead of requeued

This is how the workers avoid double-claiming while still recovering from
crashes or restarts.

## Idempotency

Idempotency is implemented explicitly in Postgres, not only in memory.

The persistence layer is `backend-python/infra/db/idempotency_store.py`.

The `idempotency_keys` table stores:

- `job_type`
- `idempotency_key`
- `request_hash`
- `resource_id`

The claim API returns one of four states:

- `claimed`
  - caller may proceed and must later finalize
- `replay`
  - same key + same payload already completed
  - return the previously created resource id
- `conflict`
  - same key reused for a different payload
- `in_progress`
  - same key and payload are already being processed

### Where We Use It Today

#### Page Translation

`backend-python/infra/jobs/page_translation_creation.py` does two distinct things:

1. active-run dedupe
   - before creating anything, it looks for an active `page_translation`
     workflow for the same `volumeId + filename`
   - if one exists, it reuses that workflow id
2. optional explicit idempotency
   - if the caller provides `Idempotency-Key`, it claims the key against the
     normalized request hash
   - after workflow creation it finalizes the claim with the created workflow id
   - if creation fails, it releases the unfinished claim

Important nuance:

- `forceRerun=true` bypasses idempotency replay
- it does not bypass active-run dedupe

#### Agent-Managed Auto Keys

Some agent tools manage idempotency automatically through the shared persisted
operation layer in `backend-python/infra/jobs/operations.py`.

Current policy examples:

- `translate_active_page`
  - `optional_key+active_run_dedupe`
- `detect_text_boxes`
  - `agent_managed_auto_key`
- `ocr_text_box`
  - `agent_managed_auto_key`
- `translate_box`
  - no idempotency
- utility workflows
  - no idempotency

The important architectural point is:

- idempotency is a persistence concern and is enforced with durable DB rows
- the agent and HTTP layers are thin adapters around that persisted policy

## Page Translation Workflow

This is the most important long-running workflow in the system.

### Packages

Workflow orchestration lives in:

- `core/workflows/page_translation/orchestration/`
- `core/workflows/page_translation/persistence/`
- `core/workflows/page_translation/state/`
- `core/workflows/page_translation/stages/`

The state machine is in:

- `core/workflows/page_translation/state/state_machine.py`
- `core/workflows/page_translation/state/types.py`

### State Machine

States:

- `queued`
- `detecting_boxes`
- `ocr_running`
- `translating`
- `committing`
- `completed`
- `failed`
- `canceled`

Events:

- `start_requested`
- `detect_succeeded` / `detect_failed`
- `ocr_succeeded` / `ocr_failed`
- `translate_succeeded` / `translate_failed`
- `commit_succeeded` / `commit_failed`
- `cancel_requested`

The runner uses this state machine to update durable workflow state rather than
encoding transitions ad hoc.

### Stage Order

The orchestration entrypoint is
`core/workflows/page_translation/orchestration/runner.py`.

The workflow does:

1. normalize the request payload into `PageTranslationRequest`
2. ensure a persisted `workflow_runs` row exists
3. detect boxes
4. run OCR fanout
5. run the page-translation LLM stages
6. commit translated content and refreshed context
7. persist terminal outcome

### Detect Stage

`core/workflows/page_translation/stages/detect.py` calls the box-detection
usecase and then reloads the page boxes.

Important current behavior:

- `preserveExistingBoxes` defaults to `true`
- preserve mode calls box detection with `replace_existing=False`
- detection therefore adds only non-overlapping new boxes and does not wipe the page
- explicit rebuild behavior still exists when the flag is set to false

### OCR Fanout

`core/workflows/page_translation/stages/ocr_fanout.py` fans out OCR across the
current page boxes.

It does all of the following:

- creates one persisted `task_runs` row per `(box, profile)` combination
- executes OCR calls concurrently with bounded semaphores
- stores attempt audit rows in `task_attempt_events`
- updates OCR task progress back into the workflow run context
- selects the best OCR text per box using `select_box_ocr_texts(...)`
- persists the chosen OCR text back into `text_box_contents`

Concurrency is bounded by settings resolved from
`resolve_ocr_parallelism_settings()`:

- local OCR limit
- remote OCR limit
- max worker cap
- lease seconds
- task timeout seconds

Within page translation specifically, OCR fanout runs inside the workflow
runner with `asyncio.gather(...)` and separate semaphores for:

- local OCR providers
- remote LLM OCR providers

### Translate Stage

`core/workflows/page_translation/stages/translate.py` wraps the lower-level
page-translation runtime.

It creates two persisted task rows:

- `translate_page`
- `merge_state`

Then it calls `core/usecases/page_translation/runtime/stage.py`, which runs two
LLM-backed stages:

1. translate the page boxes into structured output
2. merge that result with prior continuity context to refresh:
   - story summary
   - image summary
   - characters
   - open threads
   - glossary

The usecase runtime also owns:

- structured-output parsing
- malformed JSON repair
- stage event emission
- debug snapshot capture
- non-fatal merge fallback behavior
- coverage warnings when structured output is syntactically valid but incomplete

### Commit Stage

`core/workflows/page_translation/stages/commit.py` applies the translated
payload back into durable page state.

It writes:

- updated box text/translation fields
- `volume_context`
- `page_context`

So page translation is both:

- a box update workflow
- a continuity/memory update workflow

## OCR, Translation, and Box Detection Outside Page Translation

These are also available as standalone persisted operations.

### OCR

Standalone OCR jobs are:

- `ocr_box`
- `ocr_page`

These are executed by `backend-python/infra/jobs/db_ocr_worker.py`.

The OCR DB worker:

- claims queued OCR tasks from `task_runs`
- uses provider-aware semaphores for local vs remote OCR
- persists retry/attempt telemetry into `task_attempt_events`
- writes selected OCR text back into `text_box_contents`
- finalizes workflow progress in `workflow_runs`

### Translation

Standalone single-box translation jobs are executed by
`backend-python/infra/jobs/db_translate_worker.py`.

This worker:

- claims `translate_box` tasks
- runs the translation usecase for one box
- persists task-attempt events
- updates the parent workflow row as queued/running/completed/failed/canceled

### Box Detection

Box detection is a utility workflow executed by
`backend-python/infra/jobs/db_utility_worker.py`.

The core usecase entrypoint is
`core/usecases/box_detection/runtime/engine.py`.

That usecase:

- resolves the effective detection profile
- loads the page image
- runs YOLO inference
- creates a `box_detection_runs` audit row
- either:
  - replaces existing boxes for a type, or
  - appends only non-overlapping new detections

The preserve-vs-rebuild behavior is explicit and now defaults to preserve mode
for agent/page-translation/UI autodetect flows.

## Agent and MCP

### Chat Agent Runtime

The chat runtime lives under `core/usecases/agent/`.

Important pieces:

- `runtime/engine_sdk_runtime.py`
  - OpenAI Agents SDK orchestration
- `runtime/mcp_runtime.py`
  - per-run MCP client creation and cleanup
- `grounding/`
  - active page state + grounding message construction
- `tools/`
  - provider-neutral tool adapters used by MCP

The chat session model choice is stored in `agent_sessions.model_id`.

### MCP Server

The MCP server is defined in `backend-python/mcp_server/`.

Current architecture:

- `server.py` builds `FastMCP`
- `tools.py` registers the MCP tools
- `context.py` resolves run-scoped context from request headers
- `app.py` mounts the MCP app at `/api/mcp`

The backend therefore hosts its own MCP server locally.

### MCP Context Model

Each chat run creates MCP clients with headers:

- `x-mangayaku-volume-id`
- `x-mangayaku-active-filename`
- `x-mangayaku-agent-run-id`

`mcp_server/context.py` also keeps a run-scoped in-memory map from
`agent_run_id -> active_filename`, so tools can keep using the current page
across calls in the same run.

The MCP clients are run-scoped and cleaned up after each run. They are not
global pooled clients today.

### What MCP Tools Look Like

Tools are individual named actions registered with `@mcp.tool(...)`.

Each tool exposes:

- a stable name
- a human-readable description
- typed parameters
- structured return data

Representative tools:

- page navigation
  - `set_active_page`
  - `shift_active_page`
  - `list_volume_pages`
- context / memory
  - `get_volume_context`
  - `get_page_memory`
  - `update_volume_context`
  - `update_page_memory`
- box inspection / editing
  - `list_text_boxes`
  - `get_text_box_detail`
  - `update_text_box_fields`
  - `view_text_box`
- job-backed operations
  - `ocr_text_box`
  - `detect_text_boxes`
  - `translate_active_page`

Tool behavior is described primarily in the MCP tool descriptions rather than
in the system prompt alone.

## Prompts and Model Settings

Prompt bundles live under `prompts/` and are loaded through
`backend-python/infra/prompts.py`.

Current prompt organization is capability-based, for example:

- `prompts/agent/chat/...`
- `prompts/mcp/...`
- `prompts/ocr/...`
- `prompts/translation/...`
- `prompts/page_translation/...`

Important architectural distinction:

- prompt files define text
- model selection comes from settings/session/profile resolution in code

Current settings model:

- base defaults come from code/env
- DB stores overrides
- core resolves typed runtime settings before calls
- model capability logic decides whether settings like `temperature` or
  `reasoning_effort` actually apply

## Observability

The system has two main durable observability layers.

### Task-Level Attempt Audit

`task_attempt_events` records:

- tool name
- model id
- prompt version
- params snapshot
- token usage
- finish reason
- latency
- error detail

This is the per-attempt audit trail for OCR/translation/page-translation tasks.

### LLM Call Logs

`llm_call_logs` records every logged OpenAI call with:

- provider/api/component
- status
- model
- workflow/task/job ids
- token counts
- finish reason
- excerpts
- payload path

The full redacted payload is written to:

- `data/logs/llm_calls/<uuid>.json`

Page-translation-specific debug artifacts are also written under:

- `data/logs/page_translation/...`

## What Is Deliberately Not True Today

To avoid confusion, these are common assumptions that do not match the current
implementation:

- jobs are not an append-only event log
- the MCP server is not a separate deployed backend by default
- page translation is not a single direct LLM call; it is a persisted workflow
- JSON repair is not a substitute for truncated-output recovery
  - truncation is treated as a generation-budget problem first

## Current Architectural Shape In One Sentence

Today MangaYaku is a single FastAPI-based backend that owns page state,
chat-agent runtime, a mounted MCP tool server, and a Postgres-backed durable
workflow system for OCR, translation, box detection, training utilities, and
the multi-stage page-translation pipeline.
