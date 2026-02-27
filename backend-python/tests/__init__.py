# backend-python/tests/__init__.py
"""Backend test package.

What this package covers:
- Unit-level behavior for API helpers, workflow orchestration, and infra adapters.
- Small integration seams via mocks/fakes around DB, workers, and provider init.

How tests are written:
- Deterministic inputs with no network calls.
- External boundaries are patched to keep runs fast and reproducible.
"""
