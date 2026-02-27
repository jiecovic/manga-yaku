# Backend Tests Guide

Purpose: quick map of what each backend test module protects.

## Run all backend tests

```bash
cd backend-python
source .venv/bin/activate
pytest -q tests
```

## Fast targeted runs

State machine and workflow stages:

```bash
pytest -q tests/test_agent_state_machine.py tests/test_agent_workflow_stages.py
```

OCR and translation execution:

```bash
pytest -q tests/test_ocr_execution.py tests/test_translation_execution.py tests/test_ocr_providers.py
```

Jobs runtime and persistence adapters:

```bash
pytest -q tests/test_jobs_runtime.py tests/test_jobs_service.py tests/test_jobs_worker_repo_adapters.py
```

## Test module map

- `test_api_smoke.py`
  - smoke-level router contract checks without full ASGI lifespan boot.
- `test_agent_state_machine.py`
  - workflow status transitions and cancellation semantics.
- `test_agent_workflow_stages.py`
  - detect/ocr/translate/commit stage behavior and wiring.
- `test_agent_workflow_helpers.py`
  - helper utilities used by agent workflow orchestration.
- `test_agent_page_translate_helpers.py`
  - stage result normalization and OCR no-text consensus guard logic.
- `test_retry_policies.py`
  - retry-policy behavior for failure/transient conditions.
- `test_ocr_execution.py`
  - shared OCR task execution helper behavior.
- `test_translation_execution.py`
  - shared translation task execution helper behavior.
- `test_ocr_providers.py`
  - provider availability regression checks (hide unavailable manga-ocr).
- `test_jobs_runtime.py`
  - startup/shutdown behavior of in-process job runtime.
- `test_jobs_service.py`
  - non-HTTP jobs service orchestration logic.
- `test_jobs_worker_repo_adapters.py`
  - DB worker adapter mapping around workflow repo helpers.
- `test_jobs_infra.py`
  - lower-level jobs infra behavior.
- `test_translate_box_workflow.py`
  - persisted translate-box workflow creation/wiring.
- `test_domain_page_ports.py`
  - core-domain page write port binding/delegation.
- `test_volumes_memory_service.py`
  - volumes memory and derived-state service behavior.
- `conftest.py`
  - shared fixtures and offline test defaults.

## Conventions

- Keep tests deterministic and offline (no real LLM/network calls).
- Prefer narrow unit tests around stage/service boundaries.
- For behavior changes, update tests in the same PR/commit slice.
