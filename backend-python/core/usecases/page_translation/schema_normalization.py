# backend-python/core/usecases/page_translation/schema_normalization.py
"""Result normalization helpers for page-translation stages."""

from __future__ import annotations

from typing import Any

_SPEAKER_GENDER_CHOICES = {"male", "female", "unknown"}
_REFERENT_GENDER_CHOICES = {"male", "female", "unknown"}


def coerce_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def normalize_translate_stage_result(data: dict[str, Any]) -> dict[str, Any]:
    if "boxes" not in data or "no_text_boxes" not in data:
        raise ValueError("stage1 payload must include boxes and no_text_boxes")

    no_text_box_ids: set[int] = set()
    raw_no_text = data.get("no_text_boxes")
    if isinstance(raw_no_text, list):
        for item in raw_no_text:
            parsed = coerce_positive_int(item)
            if parsed is not None:
                no_text_box_ids.add(parsed)

    boxes: list[dict[str, Any]] = []
    raw_boxes = data.get("boxes")
    if isinstance(raw_boxes, list):
        for raw in raw_boxes:
            if not isinstance(raw, dict):
                continue
            raw_ids = raw.get("box_ids")
            if not isinstance(raw_ids, list):
                continue
            box_ids: list[int] = []
            seen_ids: set[int] = set()
            for item in raw_ids:
                parsed = coerce_positive_int(item)
                if parsed is None or parsed in seen_ids or parsed in no_text_box_ids:
                    continue
                seen_ids.add(parsed)
                box_ids.append(parsed)
            if not box_ids:
                continue

            speaker_gender = str(raw.get("speaker_gender") or "").strip().lower()
            if speaker_gender not in _SPEAKER_GENDER_CHOICES:
                speaker_gender = "unknown"
            referent_gender = str(raw.get("referent_gender") or "").strip().lower()
            if referent_gender not in _REFERENT_GENDER_CHOICES:
                referent_gender = "unknown"

            boxes.append(
                {
                    "box_ids": box_ids,
                    "ocr_profile_id": str(raw.get("ocr_profile_id") or "unknown").strip()
                    or "unknown",
                    "ocr_text": str(raw.get("ocr_text") or "").strip(),
                    "speaker_id": str(raw.get("speaker_id") or "unknown").strip() or "unknown",
                    "addressee_id": str(raw.get("addressee_id") or "").strip(),
                    "speaker_gender": speaker_gender,
                    "speaker_visual_cues": str(raw.get("speaker_visual_cues") or "").strip(),
                    "referent_id": str(raw.get("referent_id") or "unknown").strip() or "unknown",
                    "referent_gender": referent_gender,
                    "translation": str(raw.get("translation") or "").strip(),
                }
            )

    page_events: list[str] = []
    raw_events = data.get("page_events")
    if isinstance(raw_events, list):
        for item in raw_events:
            text = str(item or "").strip()
            if text:
                page_events.append(text)

    page_characters_detected: list[dict[str, str]] = []
    raw_detected = data.get("page_characters_detected")
    if isinstance(raw_detected, list):
        for item in raw_detected:
            if not isinstance(item, dict):
                continue
            speaker_id = str(item.get("speaker_id") or "unknown").strip() or "unknown"
            speaker_gender = str(item.get("speaker_gender") or "").strip().lower()
            if speaker_gender not in _SPEAKER_GENDER_CHOICES:
                speaker_gender = "unknown"
            speaker_visual_cues = str(item.get("speaker_visual_cues") or "").strip()
            page_characters_detected.append(
                {
                    "speaker_id": speaker_id,
                    "speaker_gender": speaker_gender,
                    "speaker_visual_cues": speaker_visual_cues,
                }
            )

    return {
        "boxes": boxes,
        "no_text_boxes": sorted(no_text_box_ids),
        "image_summary": str(data.get("image_summary") or "").strip(),
        "page_events": page_events,
        "page_characters_detected": page_characters_detected,
    }


def normalize_state_merge_result(data: dict[str, Any]) -> dict[str, Any]:
    if "characters" not in data or "open_threads" not in data or "glossary" not in data:
        raise ValueError("stage2 payload must include characters/open_threads/glossary")

    characters: list[dict[str, str]] = []
    raw_characters = data.get("characters")
    if isinstance(raw_characters, list):
        for item in raw_characters:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            gender = str(item.get("gender") or "unknown").strip().lower() or "unknown"
            info = str(item.get("info") or "").strip()
            characters.append({"name": name, "gender": gender, "info": info})

    open_threads: list[str] = []
    raw_threads = data.get("open_threads")
    if isinstance(raw_threads, list):
        for item in raw_threads:
            text = str(item or "").strip()
            if text:
                open_threads.append(text)

    glossary: list[dict[str, str]] = []
    raw_glossary = data.get("glossary")
    if isinstance(raw_glossary, list):
        for item in raw_glossary:
            if not isinstance(item, dict):
                continue
            term = str(item.get("term") or "").strip()
            translation = str(item.get("translation") or "").strip()
            note = str(item.get("note") or "").strip()
            if not term or not translation:
                continue
            glossary.append({"term": term, "translation": translation, "note": note})

    return {
        "characters": characters,
        "open_threads": open_threads,
        "glossary": glossary,
        "story_summary": str(data.get("story_summary") or "").strip(),
    }
