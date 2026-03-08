# Core

Purpose: business rules, reusable use cases, and workflow orchestration.

## What lives here

- `domain/`
  - stable entities and ports that should not depend on transport or storage
- `usecases/`
  - reusable business operations and runtime helpers
  - examples:
    - chat-agent runtime
    - OCR runtime
    - single-box translation runtime
    - page-translation LLM stage logic
- `workflows/`
  - long-running orchestration that composes multiple use cases
  - examples:
    - persisted page-translation workflow state machine
    - stage order, retry boundaries, cancel behavior, completion rules

## Use Cases vs Workflows

The most important distinction in this package is:

- `usecases` answer: "How does one capability work?"
- `workflows` answer: "How do multiple capabilities run together as one job?"

For `page_translation`, that means:

- `core/usecases/page_translation/`
  - prompt construction
  - model/runtime config
  - structured LLM calls
  - schema parsing and normalization
  - diagnostics for the translation/merge stages
- `core/workflows/page_translation/`
  - detect -> OCR fanout -> translate -> commit orchestration
  - persisted workflow state transitions
  - progress, cancellation, and terminal outcomes

This split is intentional. The page-translation feature is both:

- a reusable LLM/runtime capability
- a long-running workflow built on top of that capability

## Typical execution path

High-level request flow today:

1. API or worker layer validates and normalizes request data.
2. `core/usecases/...` builds the business/runtime payloads.
3. `core/workflows/...` coordinates multi-stage jobs when the feature is
   persisted or long-running.
4. `infra/...` performs persistence, provider SDK calls, filesystem access,
   and worker runtime concerns.

Example:

1. A page-translation workflow is claimed by a DB worker.
2. `core/workflows/page_translation/orchestration/runner.py` advances the
   workflow state machine.
3. Stage helpers call into `core/usecases/page_translation/runtime/...` for the
   actual structured LLM work.
4. Persistence/event helpers under `infra/...` store results and logs.

## Design constraints

Keep `core` focused on policy and business logic. Avoid leaking in:

- direct HTTP request/response handling
- DB session management or SQL ownership
- filesystem/process bootstrapping
- provider-specific wiring that belongs in `infra/`

Small adapters at the boundary are fine, but `core` should stay explainable as:
"what the app does" rather than "how this process happens to be wired today".
