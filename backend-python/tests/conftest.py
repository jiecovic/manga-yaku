# backend-python/tests/conftest.py
from __future__ import annotations

import os

from infra.domain_bindings import bind_domain_ports

# Keep unit tests deterministic/offline: some OCR imports trigger
# Hugging Face lookups at import-time if these are unset.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

# Bind domain ports for tests that hit core domain write helpers.
bind_domain_ports()
