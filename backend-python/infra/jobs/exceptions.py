# backend-python/infra/jobs/exceptions.py
"""Shared exceptions for job-runtime cancellation semantics."""

from __future__ import annotations


class JobCanceled(RuntimeError):
    """Raised when cooperative job cancelation should stop current work."""

