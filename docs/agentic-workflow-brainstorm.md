# Agentic Workflow Brainstorm

Date: 2026-02-26
Branch: `spike/rework-playground`
Status: brainstorming only (no implementation yet)

## Goal

Rework `agent_translate_page` into a cleaner workflow-oriented architecture that supports:

- clear state transitions
- parallel OCR execution
- bounded retries/timeouts
- better observability in frontend jobs UI
- optional future resumability after backend restarts

## Core Principles

- Use divide-and-conquer with explicit fan-out/fan-in stages.
- Keep orchestration deterministic via a state machine.
- Treat LLM outputs as speculative until validated.
- Persist side effects only in a commit stage.
- Separate execution tracking (`jobs`) from capability (`tools`) and policy (`agents`).

## Terminology Boundaries

- `Workflow run`: parent execution for one page-level request (example: `agent_translate_page`).
- `Task run`: unit of work within a workflow (example: OCR one box with one profile).
- `Attempt`: one try of a task, including retries.
- `Tool`: deterministic capability implementation (`manga_ocr`, OpenAI OCR call, DB write adapter, detector).
- `Agent`: policy component with autonomy/planning (only where needed, not everywhere).

Current interpretation:

- `manga_ocr` is a tool.
- LLM OCR profiles are best treated as tools with strict contracts, unless we explicitly add autonomous behavior.
- Translation step can stay a tool-backed stage unless we intentionally introduce planning loops.

## Agent vs Tool Boundary (LLM OCR)

Short answer for this project: LLM OCR should be modeled as a **tool** by default.

Decision rule:

- It is a **tool** if:
  - input/output contract is fixed
  - no autonomous planning
  - no dynamic multi-step strategy selection
  - deterministic orchestration decides when/how it runs
- It is an **agent** if:
  - it can choose among tools/prompts/strategies autonomously
  - it can re-plan after intermediate observations
  - it has goal-seeking behavior beyond one bounded call

Recommended current boundary:

- `manga_ocr`, `openai_fast_ocr`, `openai_quality_ocr`, `openai_ultra_ocr` => tools
- orchestration/state transitions/retries/timeouts => workflow engine
- optional future "ocr coordinator" can be an agent only if we truly need adaptive planning

Why this is typical in production agentic systems:

- keeps reliability high (bounded behavior)
- makes retries/idempotency simpler
- makes provenance/auditability clearer
- prevents "agent sprawl" where everything is labeled an agent without autonomy

### Agent-As-Tool Pattern (real systems)

Yes. In real agentic architectures, a component can be:

- an **agent internally** (it may plan/use sub-tools)
- exposed externally as a **tool interface** to a higher-level orchestrator

So "LLM agent as a tool" is valid at system boundaries.
The key is to keep the interface contract strict and bounded for the caller.

## Proposed Page Workflow (Fan-out/Fan-in)

1. `detect_boxes`
2. `ocr_fan_out` for each `(box_id, profile_id)` pair in parallel
3. `ocr_fan_in` and adjudicate final OCR per box
4. `translate_page` (single prompt from adjudicated OCR + memory context)
5. `validate_output`
6. `commit_persist` (DB writes)
7. `update_memory`
8. `completed | failed | canceled`

## State Machine Sketch

- `queued` -> `detecting_boxes`
- `detecting_boxes` -> `ocr_running`
- `ocr_running` -> `ocr_collecting` (until all done or cutoff reached)
- `ocr_collecting` -> `ocr_adjudicated`
- `ocr_adjudicated` -> `translating`
- `translating` -> `validating`
- `validating` -> `committing` or `failed`
- `committing` -> `memory_updating`
- `memory_updating` -> `completed`
- any state -> `canceled` if cancellation requested and safe to stop

Invariant idea:

- only `committing` may mutate final persisted box/page/volume outputs

## Parallelization Plan

- Parallel unit: task keyed by `(workflow_id, box_id, profile_id)`.
- Use bounded worker pools and per-provider concurrency limits.
- Keep separate limits for local OCR and remote OCR to avoid starving one class.
- Track progress at parent and child levels.
- Add idempotency key for each task input revision.

## Timeout and Cutoff Policy

- Task timeout: per OCR/LLM call.
- Stage deadline: OCR fan-in cutoff.
- Workflow deadline: hard stop for full page process.
- Lease timeout for workers: reclaim stuck tasks.
- If OCR cutoff is reached, proceed with best available completed results and mark missing tasks as `timed_out`.

## Retry Policy

For LLM OCR tasks:

- retry transient transport/5xx/429 errors with backoff + jitter
- retry truncation once with higher token budget
- retry empty or unparseable structured output once with stricter formatting prompt
- stop after fixed attempt cap and record failure reason

For translation task:

- same bounded retry philosophy
- keep strict structured output contract
- fail closed when schema cannot be satisfied after limits

## Data Model Proposal (Postgres-first)

Prefer Postgres-backed durable orchestration now (Kafka later only if needed).

### `workflow_runs`

- `id`
- `workflow_type` (example: `agent_translate_page`)
- `volume_id`
- `filename`
- `page_revision`
- `state`
- `status` (`queued|running|completed|failed|canceled`)
- `deadline_at`
- `cancel_requested`
- `created_at`
- `updated_at`

### `task_runs`

- `id`
- `workflow_id`
- `stage` (`detect|ocr|adjudicate|translate|validate|commit|memory`)
- `box_id` (nullable)
- `profile_id` (nullable)
- `status`
- `attempt`
- `lease_until`
- `next_retry_at`
- `error_code`
- `result_json`
- `started_at`
- `finished_at`

### `task_attempt_events` (append-only)

- `task_id`
- `attempt`
- `tool_name`
- `model_id`
- `prompt_version`
- `params_snapshot`
- `token_usage`
- `finish_reason`
- `latency_ms`
- `error_detail`
- `created_at`

## Worker Execution Model

- Claim runnable tasks with `FOR UPDATE SKIP LOCKED`.
- Use lease + heartbeat to recover from worker crash.
- Only transition states through guarded handlers.
- Keep state transition and side-effect writes in transactional boundaries where possible.

### Event Triggering Without Kafka (recommended now)

Yes, conceptually similar to queue consumers, but implemented with Postgres.

Flow:

1. Orchestrator inserts `task_runs` rows for runnable work.
2. Workers claim tasks from DB (`queued` -> `running`) with row locks.
3. Worker executes task, writes result/error, marks terminal status.
4. Orchestrator (or stage reducer) checks fan-in readiness and advances workflow state.
5. Worker picks next task.

Trigger/wakeup options:

- baseline: short polling loop (simple, robust)
- improved: `LISTEN/NOTIFY` on new runnable tasks to reduce polling latency

This gives Kafka-like fan-out/fan-in behavior while staying operationally simple.

### OCR Parallelism Controls

Add per-provider concurrency settings, e.g.:

- `ocr.parallelism.local` (manga_ocr)
- `ocr.parallelism.remote` (LLM OCR)
- optional per-profile override (`openai_fast_ocr`, `openai_quality_ocr`, ...)

Scheduler should enforce both:

- global workflow budget (avoid overload)
- per-provider budget (avoid one provider starving others)

### Detection Overlap Handling (current code confirmation)

Current detection already has overlap suppression in two layers:

1. YOLO inference NMS via confidence/IoU thresholds
2. post-process containment dedupe (`filter_contained_boxes`)

So "remove overlapping boxes" currently exists, specifically as NMS + containment filtering.

## Jobs UI Model (Hierarchical)

Display should reflect workflow topology:

- parent job row: page workflow overall progress/state
- stage rows: detect, OCR fan-out, adjudicate, translate, commit
- expandable child tasks for OCR `(box_id, profile_id)`
- summary metrics per stage:
  - done / running / failed / timed out
  - retries
  - token/time cost

Default UX:

- compact stage-based summary first
- deep task detail on expand for debugging

## Kafka vs Postgres Decision

Current recommendation:

- start with Postgres-backed queue/workflow tables
- keep architecture event-ready, but do not introduce Kafka yet

Why:

- lower operational complexity
- enough for current scale
- durable resume after restart can still be achieved
- easier to iterate quickly during refactor

Future path:

- add outbox events from Postgres transitions
- introduce Kafka only when multi-service scaling or throughput needs justify it

## Migration Strategy (Incremental)

1. Define workflow/state model and transition guards.
2. Introduce DB tables for durable workflow/task tracking.
3. Migrate `agent_translate_page` first as vertical slice.
4. Keep old jobs panel wired, then enhance to hierarchical view.
5. Add resume/recovery behavior and cancellation semantics.
6. Move other pipelines (`ocr_page`, `translate_page`, training) over time.

## Open Questions

- Should unmentioned translation boxes imply deletion, or only explicit delete intents?
- Do we require confidence scoring from every OCR tool output?
- What is acceptable partial-result policy at OCR cutoff for production behavior?
- Which metrics are mandatory in job UI vs debug-only?
- Do we want a dedicated adjudication step/tool now or later?

## Where To Start (Recommended Sequence)

Do not refactor everything at once. Start with architecture contracts, then one vertical slice.

### Phase 0: Alignment (design-only)

Deliverables:

- state transition table for `agent_translate_page`
- task input/output schemas (detect, ocr_task, adjudicate, translate, commit)
- explicit policies for retry, timeout, cutoff, cancellation
- decision on destructive behavior (box deletion policy)

Exit criteria:

- team can explain one full run from `queued` to `completed` with failure/cancel paths

### Phase 1: Workflow Skeleton (no behavior change yet)

Deliverables:

- introduce `workflow_run` + `task_run` models (in-memory first is fine)
- wrap current logic behind stage handlers
- add structured run/task event logging

Exit criteria:

- existing feature still works, but progress is now stage-oriented

### Phase 2: OCR Fan-out/Fan-in (first real refactor)

Deliverables:

- parallel `(box_id, profile_id)` OCR tasks with bounded concurrency
- fan-in aggregation and per-box adjudication step
- stage cutoff behavior implemented

Exit criteria:

- same or better output quality
- measurable reduction in OCR stage latency

### Phase 3: Durability and Resume

Deliverables:

- move workflow/task state to Postgres
- add task leasing/heartbeat and reclaim
- add resume-after-restart semantics

Exit criteria:

- restart during run does not lose workflow progress

### Phase 4: Frontend Jobs UX

Deliverables:

- parent workflow row + stage rows + expandable child task details
- clear failure/timed_out/retry visibility

Exit criteria:

- user can diagnose where/why a run failed without backend logs

### First Practical Step (next action)

Write the state transition table and stage contracts for `agent_translate_page` before any code changes.
This avoids architecture drift and gives a stable target for implementation.

## Sandbox Rewrite Strategy (big refactor mode)

Given this is a sandbox branch, a controlled "break and rebuild" approach is acceptable.

### Proposed mode

- Build the new workflow implementation mostly from scratch.
- Keep old implementation isolated as read-only reference.
- Reintroduce functionality stage by stage into the new workflow.

### Legacy isolation pattern

- Move old logic into a clearly named folder (example: `backend-python/legacy/agent_translate_page/`).
- Do not evolve legacy code except critical reference fixes.
- Treat legacy as documentation-by-code and fallback reference.

### Guardrails to avoid chaos

1. Tag baseline before rewrite (`baseline-legacy-before-workflow-rewrite`).
2. Keep one parity checklist for required capabilities.
3. Keep a small golden dataset (few pages) with expected outputs for comparison.
4. Keep architecture contracts authoritative (state + stage schemas).
5. Rebuild in coarse milestones, not file-by-file random edits.

### Milestones for rebuild-from-scratch

1. workflow runner skeleton + state transitions
2. detection stage wired
3. OCR fan-out/fan-in wired with parallel workers
4. translation + validation wired
5. commit + memory update wired
6. frontend jobs hierarchy wired

### Tradeoff

This is faster for architectural cleanup, but branch can stay broken for periods.
Acceptable in sandbox, as long as baseline reference and milestone discipline are maintained.

## Immediate Start Plan (rewrite)

Recommended first implementation slice:

1. Scaffold new workflow state machine + runner (no OCR/LLM yet).
2. Implement only `detect_boxes` stage end-to-end inside new workflow.
3. Persist stage result snapshot (`page_revision`, detected boxes).
4. Expose parent workflow progress in jobs UI (minimal fields).

Stop here first and verify:

- queued -> detecting -> detect_done transition works
- cancel behavior works in this narrow slice
- workflow/task records are written correctly

Then continue:

5. Add OCR fan-out task schema and worker claiming loop (initially no real OCR call; stub tool).
6. Replace stub with real OCR tools and bounded concurrency controls.

## Legacy-First Cutover Decision

Question: move old OCR/translate/box logic to legacy first, then rebuild?

Recommendation: **yes**, but do it as copy/freeze first, then cut over.

Suggested order:

1. Tag baseline and copy current workflow modules into `legacy/agent_translate_page/`.
2. Mark legacy as read-only reference.
3. Scaffold the new workflow package with detect-only stage.
4. Switch entrypoints to new workflow only when detect stage is wired.
5. Reintroduce OCR/translate behavior into new workflow incrementally.

Why copy/freeze before hard move:

- avoids breaking imports immediately
- preserves exact reference behavior
- supports aggressive rebuild while still having a stable fallback map

## Agent Translate Page: Transition Table (draft)

| Current State | Event | Guard | Action | Next State |
|---|---|---|---|---|
| `queued` | `start_requested` | workflow row exists and not canceled | initialize run metadata, emit start event | `detecting_boxes` |
| `detecting_boxes` | `detect_success` | detector output parsed | store detected box set snapshot (`page_revision`) | `ocr_fanout_planned` |
| `detecting_boxes` | `detect_failed` | retry budget available | schedule retry with backoff | `detecting_boxes` |
| `detecting_boxes` | `detect_failed` | retry budget exhausted | record terminal error | `failed` |
| `ocr_fanout_planned` | `fanout_ready` | at least one text box | create `ocr_task` rows for each `(box_id, profile_id)` | `ocr_running` |
| `ocr_fanout_planned` | `fanout_ready` | no text boxes | skip OCR, produce empty OCR map | `translating` |
| `ocr_running` | `ocr_task_finished` | stage deadline not reached | update stage counters and task result | `ocr_running` |
| `ocr_running` | `ocr_all_done` | all ocr tasks terminal | close OCR stage | `ocr_adjudicating` |
| `ocr_running` | `ocr_deadline_reached` | pending tasks remain | mark pending as `timed_out` | `ocr_adjudicating` |
| `ocr_adjudicating` | `adjudicate_success` | per-box output contract valid | persist adjudicated OCR in stage result | `translating` |
| `ocr_adjudicating` | `adjudicate_failed` | recoverable | fallback to deterministic best-available OCR selection | `translating` |
| `translating` | `translate_success` | output contract valid | store translation candidate payload | `validating` |
| `translating` | `translate_failed` | retry budget available | schedule retry with bounded token bump policy | `translating` |
| `translating` | `translate_failed` | retry exhausted | record terminal error | `failed` |
| `validating` | `validation_passed` | schema and invariants pass | freeze commit payload | `committing` |
| `validating` | `validation_failed` | fix-up retry available | run one repair attempt and re-validate | `validating` |
| `validating` | `validation_failed` | fix-up retry exhausted | record validation failure | `failed` |
| `committing` | `commit_success` | DB transaction committed | write final outputs for page | `memory_updating` |
| `committing` | `commit_failed` | retry budget available | retry commit transaction (idempotent) | `committing` |
| `committing` | `commit_failed` | retry exhausted | record terminal error | `failed` |
| `memory_updating` | `memory_update_success` | context write completed | emit completion metrics | `completed` |
| `memory_updating` | `memory_update_failed` | non-critical failure policy | keep page outputs, mark warning | `completed` |
| `*` | `cancel_requested` | currently cancel-safe state | mark canceled and stop scheduling new tasks | `canceled` |
| `*` | `deadline_reached` | workflow deadline passed | abort remaining tasks and mark timed out | `failed` |

### Cancel-Safe States (draft)

- `queued`
- `detecting_boxes` (between attempts)
- `ocr_running` (before claiming new tasks)
- `translating` (between attempts)

Non-cancel-safe state:

- `committing` (must finish or rollback transaction safely)

## Stage Contracts (draft)

### `detect_boxes` output

- `page_revision: string`
- `boxes: array<{box_id:int,x:float,y:float,width:float,height:float,type:string}>`
- `detector_meta: {profile_id:string, model_id:string, latency_ms:int}`

### `ocr_task` output (per `(box_id, profile_id)`)

- `box_id: int`
- `profile_id: string`
- `status: ok|no_text|invalid|error|timed_out`
- `text: string`
- `confidence: number|null`
- `finish_reason: string|null`
- `attempt: int`
- `usage: {input_tokens:int|null, output_tokens:int|null, total_tokens:int|null}`
- `error_code: string|null`

### `ocr_adjudicate` output (per box)

- `box_id: int`
- `selected_profile_id: string|null`
- `ocr_text: string`
- `decision_reason: string`
- `candidate_summary: array<{profile_id:string,status:string,text_len:int}>`

### `translate_page` output

- `boxes: array<{box_ids:int[], ocr_profile_id:string, ocr_text:string, translation:string}>`
- `characters: array<object>`
- `image_summary: string`
- `story_summary: string`
- `no_text_boxes: int[]`
- `open_threads: string[]`
- `glossary: array<object>`

### `commit_persist` input/output

Input:

- validated translation payload
- adjudicated OCR map
- `page_revision`

Output:

- `committed_box_ids: int[]`
- `deleted_box_ids: int[]`
- `order_applied: boolean`
- `context_updated: boolean`

## Progress Log

### 2026-02-26: first implementation slice started

- legacy freeze created under `backend-python/legacy/agent_translate_page/`
- new workflow scaffolding created under `backend-python/core/workflows/agent_translate_page/`
- active `agent_translate_page` handler switched to new detect-only workflow runner
- current behavior intentionally stops after detect stage; OCR/translation stages are pending rewrite
- old `core.usecases.agent.page_translate.run_agent_translate_page` path explicitly detached (fail-fast guard)
