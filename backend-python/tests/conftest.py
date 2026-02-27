from __future__ import annotations

import os

# Keep unit tests deterministic/offline: some OCR imports trigger
# Hugging Face lookups at import-time if these are unset.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

