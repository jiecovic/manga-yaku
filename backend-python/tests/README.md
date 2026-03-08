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
pytest -q \
  tests/core/page_translation/test_page_translation_state_machine.py \
  tests/core/page_translation/test_page_translation_workflow_stages.py
```

OCR and translation execution:

```bash
pytest -q \
  tests/core/usecases/ocr/test_ocr_execution.py \
  tests/core/usecases/ocr/test_ocr_providers.py \
  tests/core/usecases/translation/test_translation_execution.py \
  tests/core/usecases/test_retry_policies.py
```

Jobs runtime and persistence adapters:

```bash
pytest -q \
  tests/infra/jobs/test_jobs_runtime.py \
  tests/infra/jobs/test_jobs_worker_repo_adapters.py \
  tests/api/test_jobs_service.py
```

## Test module map

- `api/test_api_smoke.py`
  - smoke-level router contract checks without full ASGI lifespan boot.
- `core/page_translation/test_page_translation_state_machine.py`
  - workflow status transitions and cancellation semantics.
- `core/page_translation/test_page_translation_workflow_stages.py`
  - detect/ocr/translate/commit stage behavior and wiring.
- `core/page_translation/test_page_translation_workflow_helpers.py`
  - helper utilities used by page-translation workflow orchestration.
- `core/page_translation/test_page_translation_helpers.py`
  - stage result normalization and OCR no-text consensus guard logic.
- `core/usecases/test_retry_policies.py`
  - retry-policy behavior for failure/transient conditions.
- `core/usecases/ocr/test_ocr_execution.py`
  - shared OCR task execution helper behavior.
- `core/usecases/translation/test_translation_execution.py`
  - shared translation task execution helper behavior.
- `core/usecases/ocr/test_ocr_providers.py`
  - provider availability regression checks (hide unavailable manga-ocr).
- `infra/jobs/test_jobs_runtime.py`
  - startup/shutdown behavior of in-process job runtime.
- `api/test_jobs_service.py`
  - non-HTTP jobs service orchestration logic.
- `infra/jobs/test_jobs_worker_repo_adapters.py`
  - DB worker adapter mapping around workflow repo helpers.
- `infra/jobs/test_jobs_infra.py`
  - lower-level jobs infra behavior.
- `api/test_translate_box_workflow.py`
  - persisted translate-box workflow creation/wiring.
- `core/domain/test_domain_page_ports.py`
  - core-domain page write port binding/delegation.
- `api/test_volumes_memory_service.py`
  - volumes memory and derived-state service behavior.
- `conftest.py`
  - shared fixtures and offline test defaults.

## Conventions

- Keep tests deterministic and offline (no real LLM/network calls).
- Prefer narrow unit tests around stage/service boundaries.
- For behavior changes, update tests in the same PR/commit slice.
