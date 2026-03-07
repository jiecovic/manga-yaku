# backend-python/tests/conftest.py
"""Shared test bootstrap for backend unit tests.

What this file configures:
- Offline environment flags to prevent model/download side effects at import time.
- Domain port bindings required by tests that touch core page write helpers.

How it is used:
- Imported automatically by pytest before collecting/running tests.
- Keeps the suite deterministic and independent of external services.
"""

from __future__ import annotations

import os

from infra.domain_bindings import bind_domain_ports

# Keep unit tests deterministic/offline: some OCR imports trigger
# Hugging Face lookups at import-time if these are unset.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# Bind domain ports for tests that hit core domain write helpers.
bind_domain_ports()
