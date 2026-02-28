# Infra

Purpose: concrete adapters and I/O integrations.

Contains:
- database persistence
- LLM/API clients
- filesystem/image operations
- job runtime/workers
- logging and integration wiring

Job mode boundary details: `infra/jobs/README.md`.

Avoid:
- business rules
- workflow decision policy
