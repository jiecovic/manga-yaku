# backend-python/infra/db/idempotency_store.py
"""Persistence helpers for request idempotency keys."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .db import IdempotencyKey, get_session

ClaimStatus = Literal["claimed", "replay", "conflict", "in_progress"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_existing(
    *,
    job_type: str,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, str | None]:
    with get_session() as session:
        row = session.execute(
            select(IdempotencyKey)
            .where(IdempotencyKey.job_type == job_type)
            .where(IdempotencyKey.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if row is None:
            return {"status": "claimed", "resource_id": None}
        if str(row.request_hash) != request_hash:
            return {"status": "conflict", "resource_id": row.resource_id}
        if row.resource_id:
            return {"status": "replay", "resource_id": str(row.resource_id)}
        return {"status": "in_progress", "resource_id": None}


def claim_idempotency_key(
    *,
    job_type: str,
    idempotency_key: str,
    request_hash: str,
) -> dict[str, str | None]:
    """
    Reserve an idempotency key for a request.

    Returns one of:
    - claimed: caller can execute and then finalize.
    - replay: key already completed for same payload, return resource_id.
    - conflict: key reused with different payload hash.
    - in_progress: same payload key is currently being processed.
    """
    now = _utc_now()
    try:
        with get_session() as session:
            row = session.execute(
                select(IdempotencyKey)
                .where(IdempotencyKey.job_type == job_type)
                .where(IdempotencyKey.idempotency_key == idempotency_key)
                .with_for_update()
            ).scalar_one_or_none()
            if row is None:
                session.add(
                    IdempotencyKey(
                        job_type=job_type,
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        resource_id=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
                session.flush()
                return {"status": "claimed", "resource_id": None}

            row.updated_at = now
            if str(row.request_hash) != request_hash:
                return {"status": "conflict", "resource_id": row.resource_id}
            if row.resource_id:
                return {"status": "replay", "resource_id": str(row.resource_id)}
            return {"status": "in_progress", "resource_id": None}
    except IntegrityError:
        # A concurrent insert won the race; re-read stable row state.
        return _read_existing(
            job_type=job_type,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )


def finalize_idempotency_key(
    *,
    job_type: str,
    idempotency_key: str,
    request_hash: str,
    resource_id: str,
) -> str:
    """Attach the created resource id to a claimed idempotency key."""
    now = _utc_now()
    with get_session() as session:
        row = session.execute(
            select(IdempotencyKey)
            .where(IdempotencyKey.job_type == job_type)
            .where(IdempotencyKey.idempotency_key == idempotency_key)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            row = IdempotencyKey(
                job_type=job_type,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                resource_id=resource_id,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            return resource_id

        if str(row.request_hash) != request_hash:
            raise ValueError("idempotency key reused with different request payload")

        if row.resource_id:
            return str(row.resource_id)

        row.resource_id = resource_id
        row.updated_at = now
        return resource_id


def release_idempotency_claim(
    *,
    job_type: str,
    idempotency_key: str,
    request_hash: str,
) -> None:
    """Delete an unfinished claim so a failed enqueue can be retried."""
    with get_session() as session:
        row = session.execute(
            select(IdempotencyKey)
            .where(IdempotencyKey.job_type == job_type)
            .where(IdempotencyKey.idempotency_key == idempotency_key)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            return
        if str(row.request_hash) != request_hash:
            return
        if row.resource_id:
            return
        session.delete(row)
