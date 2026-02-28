# Core

Purpose: business logic and workflow rules.

Contains:
- domain models and ports
- use-case orchestration
- workflow/state-machine logic

## Workflow execution model

- Workflow policy and stage transitions live in
  `core/workflows/agent_translate_page`.
- The runner decides stage order, cancellation behavior, and completion rules.
- DB workers do execution for queued OCR/translate tasks, but do not own
  business workflow policy.

Avoid:
- DB queries and persistence
- HTTP/SDK integrations
- filesystem/process/runtime wiring
