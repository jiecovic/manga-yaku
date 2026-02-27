from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from infra.db.db_store import get_page_index, upsert_page_context, upsert_volume_context

from ..helpers import apply_translation_payload


@dataclass(frozen=True)
class CommitStageResult:
    processed: int
    total: int
    updated: int
    order_applied: bool
    characters: list[Any]
    image_summary: str | None
    story_summary: str | None
    open_threads: list[Any]
    glossary: list[Any]


def run_commit_stage(
    *,
    volume_id: str,
    filename: str,
    text_boxes: list[dict[str, Any]],
    box_index_map: dict[int, int],
    translation_payload: dict[str, Any],
    prior_summary: str,
) -> CommitStageResult:
    commit = apply_translation_payload(
        volume_id=volume_id,
        filename=filename,
        text_boxes=text_boxes,
        box_index_map=box_index_map,
        translation_payload=translation_payload,
    )

    story_summary = translation_payload.get("story_summary")
    image_summary = translation_payload.get("image_summary")
    characters = translation_payload.get("characters", [])
    open_threads = translation_payload.get("open_threads", [])
    glossary = translation_payload.get("glossary", [])
    if not isinstance(characters, list):
        characters = []
    if not isinstance(open_threads, list):
        open_threads = []
    if not isinstance(glossary, list):
        glossary = []

    rolling_summary = (
        story_summary if isinstance(story_summary, str) and story_summary.strip() else prior_summary
    )
    page_summary = story_summary if isinstance(story_summary, str) else ""
    page_image_summary = image_summary if isinstance(image_summary, str) else ""
    page_index = get_page_index(volume_id, filename)
    upsert_volume_context(
        volume_id,
        rolling_summary=rolling_summary,
        active_characters=characters,
        open_threads=open_threads,
        glossary=glossary,
        last_page_index=page_index,
    )
    upsert_page_context(
        volume_id,
        filename,
        page_summary=page_summary,
        image_summary=page_image_summary,
        characters_snapshot=characters,
        open_threads_snapshot=open_threads,
        glossary_snapshot=glossary,
    )

    return CommitStageResult(
        processed=int(commit.get("processed") or 0),
        total=int(commit.get("total") or 0),
        updated=int(commit.get("updated") or 0),
        order_applied=bool(commit.get("orderApplied")),
        characters=characters,
        image_summary=image_summary if isinstance(image_summary, str) else None,
        story_summary=story_summary if isinstance(story_summary, str) else None,
        open_threads=open_threads,
        glossary=glossary,
    )

