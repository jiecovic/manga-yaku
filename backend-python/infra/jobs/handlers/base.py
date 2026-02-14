# backend-python/infra/jobs/handlers/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from infra.jobs.store import Job, JobStore


class JobHandler(ABC):
    @abstractmethod
    async def run(self, job: Job, store: JobStore) -> dict[str, Any]:
        raise NotImplementedError
