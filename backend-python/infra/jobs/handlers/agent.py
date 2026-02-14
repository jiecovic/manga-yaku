# backend-python/infra/jobs/handlers/agent.py
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, TypedDict

from core.usecases.agent.page_translate import run_agent_translate_page
from core.usecases.agent.settings import resolve_agent_translate_settings
from core.usecases.box_detection.engine import detect_text_boxes_for_page
from core.usecases.ocr.engine import run_ocr_box
from core.usecases.ocr.profile_settings import agent_enabled_ocr_profiles
from core.usecases.ocr.profiles import get_ocr_profile
from core.usecases.settings.service import get_setting_value
from infra.db.db_store import (
    delete_boxes_by_ids,
    get_page_index,
    get_volume_context,
    load_page,
    set_box_ocr_text_by_id,
    set_box_order_for_type,
    set_box_translation_by_id,
    upsert_page_context,
    upsert_volume_context,
)
from infra.jobs.store import Job, JobStatus, JobStore

from .base import JobHandler
from .utils import list_text_boxes


def _is_blank_ocr_text(value: str) -> bool:
    cleaned = value.strip()
    if not cleaned:
        return True
    if cleaned in ('""', "''"):
        return True
    return False


def _is_repetitive_ocr(text: str) -> bool:
    cleaned = text.strip()
    if len(cleaned) < 60:
        return False
    counts: dict[str, int] = {}
    for ch in cleaned:
        counts[ch] = counts.get(ch, 0) + 1
    most_common = max(counts.values()) if counts else 0
    return most_common / max(len(cleaned), 1) >= 0.7


def _sanitize_ocr_text(value: Any, *, llm: bool) -> tuple[str, str]:
    if not isinstance(value, str):
        return "", "invalid"
    cleaned = value.strip()
    if cleaned.upper() == "NO_TEXT":
        return "", "no_text"
    if _is_blank_ocr_text(cleaned):
        return "", "invalid" if llm else "no_text"
    if _is_repetitive_ocr(cleaned):
        return "", "invalid"
    return cleaned, "ok"


def _build_ocr_profile_meta(profile_ids: list[str]) -> list[dict[str, Any]]:
    meta: list[dict[str, Any]] = []
    for profile_id in profile_ids:
        try:
            profile = get_ocr_profile(profile_id)
        except Exception:
            continue
        cfg = profile.get("config", {}) or {}
        model = cfg.get("model") or cfg.get("model_path") or profile.get("provider")
        meta.append(
            {
                "id": profile_id,
                "model": str(model) if model is not None else "",
                "hint": profile.get("llm_hint", ""),
            }
        )
    return meta


class AgentTranslatePageResult(TypedDict, total=False):
    processed: int
    total: int
    updated: int
    orderApplied: bool
    characters: list[dict[str, Any]]
    imageSummary: str | None
    storySummary: str | None


@dataclass(frozen=True)
class AgentTranslatePageInput:
    volume_id: str
    filename: str
    detection_profile_id: str | None
    ocr_profiles: list[str]
    source_language: str
    target_language: str
    model_id: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> AgentTranslatePageInput:
        return cls(
            volume_id=str(payload["volumeId"]),
            filename=str(payload["filename"]),
            detection_profile_id=payload.get("detectionProfileId"),
            ocr_profiles=list(payload.get("ocrProfiles") or []),
            source_language=str(payload.get("sourceLanguage") or "Japanese"),
            target_language=str(payload.get("targetLanguage") or "English"),
            model_id=payload.get("modelId"),
        )


class AgentTranslatePageJobHandler(JobHandler):
    async def run(self, job: Job, store: JobStore) -> AgentTranslatePageResult:
        payload = dict(job.payload)
        data = AgentTranslatePageInput.from_payload(payload)

        detection_profile_id = data.detection_profile_id
        if not detection_profile_id:
            stored_profile_id = get_setting_value(
                "agent.translate.detection_profile_id"
            )
            if isinstance(stored_profile_id, str) and stored_profile_id.strip():
                detection_profile_id = stored_profile_id.strip()

        ocr_profiles = data.ocr_profiles or agent_enabled_ocr_profiles()
        if not ocr_profiles:
            ocr_profiles = ["manga_ocr_default"]
        llm_profiles = set()
        for profile_id in ocr_profiles:
            try:
                profile = get_ocr_profile(profile_id)
            except Exception:
                continue
            if profile.get("provider") == "openai_vision_chat":
                llm_profiles.add(profile_id)

        agent_settings = resolve_agent_translate_settings()
        model_id = data.model_id or agent_settings.get("model_id")

        max_output_tokens = agent_settings.get("max_output_tokens")
        reasoning_effort = agent_settings.get("reasoning_effort")
        temperature = agent_settings.get("temperature")

        store.update_job(job, progress=5, message="Detecting text boxes")
        await asyncio.to_thread(
            detect_text_boxes_for_page,
            data.volume_id,
            data.filename,
            detection_profile_id,
            replace_existing=True,
        )
        if job.status == JobStatus.canceled:
            store.update_job(job, message="Canceled")
            store.update_job(job, progress=100)
            return {"processed": 0, "total": 0, "updated": 0}
        store.update_job(job, progress=15, message="Detected text boxes")

        page = load_page(data.volume_id, data.filename)
        text_boxes = list_text_boxes(page)

        total_boxes = len(text_boxes)

        candidates: dict[int, dict[str, str]] = {}
        no_text_candidates: dict[int, set[str]] = {}
        error_candidates: dict[int, set[str]] = {}
        invalid_candidates: dict[int, set[str]] = {}
        llm_error_counts: dict[str, int] = {}
        llm_invalid_counts: dict[str, int] = {}
        total_ocr = total_boxes * len(ocr_profiles)
        processed = 0

        if total_boxes > 0:
            for profile_id in ocr_profiles:
                for box in text_boxes:
                    if job.status == JobStatus.canceled:
                        store.update_job(job, message="Canceled")
                        break
                    box_id = int(box.get("id") or 0)
                    status = "ok"
                    try:
                        text = await asyncio.to_thread(
                            run_ocr_box,
                            profile_id,
                            data.volume_id,
                            data.filename,
                            box_id or None,
                            float(box.get("x") or 0.0),
                            float(box.get("y") or 0.0),
                            float(box.get("width") or 0.0),
                            float(box.get("height") or 0.0),
                            persist=False,
                        )
                    except Exception:
                        text = ""
                        status = "error"
                    if status != "error":
                        text, status = _sanitize_ocr_text(
                            text,
                            llm=profile_id in llm_profiles,
                        )
                    if status == "no_text":
                        no_text_candidates.setdefault(box_id, set()).add(profile_id)
                    elif status == "invalid":
                        invalid_candidates.setdefault(box_id, set()).add(profile_id)
                        if profile_id in llm_profiles:
                            llm_invalid_counts[profile_id] = (
                                llm_invalid_counts.get(profile_id, 0) + 1
                            )
                    elif status == "error":
                        error_candidates.setdefault(box_id, set()).add(profile_id)
                        if profile_id in llm_profiles:
                            llm_error_counts[profile_id] = (
                                llm_error_counts.get(profile_id, 0) + 1
                            )
                    candidates.setdefault(box_id, {})[profile_id] = text
                    processed += 1
                    percent = 5 + int((processed / max(total_ocr, 1)) * 55)
                    store.update_job(
                        job,
                        progress=percent,
                        message=f"OCR {processed}/{total_ocr}",
                    )
                if job.status == JobStatus.canceled:
                    break

            if job.status == JobStatus.canceled:
                store.update_job(job, message="Canceled")
                store.update_job(job, progress=100)
                return {"processed": 0, "total": total_boxes, "updated": 0}

            warnings: list[str] = []
            if llm_invalid_counts:
                parts = ", ".join(
                    f"{pid}={count}" for pid, count in llm_invalid_counts.items()
                )
                warnings.append(f"OCR invalid: {parts}")
            if llm_error_counts:
                parts = ", ".join(
                    f"{pid}={count}" for pid, count in llm_error_counts.items()
                )
                warnings.append(f"OCR errors: {parts}")
            if warnings:
                store.update_job(job, warnings=warnings)

            preferred_profile = ocr_profiles[0] if ocr_profiles else ""
            for box in text_boxes:
                box_id = int(box.get("id") or 0)
                per_box = candidates.get(box_id, {})
                chosen = per_box.get(preferred_profile, "") if preferred_profile else ""
                if not chosen:
                    for value in per_box.values():
                        if value:
                            chosen = value
                            break
                set_box_ocr_text_by_id(
                    data.volume_id,
                    data.filename,
                    box_id=box_id,
                    ocr_text=chosen,
                )
            store.update_job(job, progress=60, message="OCR complete")
        else:
            store.update_job(job, progress=60, message="No text boxes detected")

        payload_boxes: list[dict[str, Any]] = []
        box_index_map: dict[int, int] = {}
        next_box_index = 1
        for box in text_boxes:
            box_id = int(box.get("id") or 0)
            ocr_list = [
                {"profile_id": pid, "text": text}
                for pid, text in candidates.get(box_id, {}).items()
                if isinstance(text, str) and text.strip()
            ]
            raw_index = int(box.get("orderIndex") or 0)
            box_index = raw_index if raw_index > 0 else 0
            if box_index <= 0 or box_index in box_index_map:
                box_index = next_box_index
                while box_index in box_index_map:
                    box_index += 1
            box_index_map[box_index] = box_id
            next_box_index = max(next_box_index, box_index + 1)
            no_text_profiles = sorted(
                pid for pid in no_text_candidates.get(box_id, set())
            )
            error_profiles = sorted(
                pid
                for pid in error_candidates.get(box_id, set())
                if pid not in llm_profiles
            )
            invalid_profiles = sorted(
                pid
                for pid in invalid_candidates.get(box_id, set())
                if pid not in llm_profiles
            )
            payload_box = {
                "box_index": box_index,
                "ocr_candidates": ocr_list,
            }
            if no_text_profiles:
                payload_box["ocr_no_text_profiles"] = no_text_profiles
            if error_profiles:
                payload_box["ocr_error_profiles"] = error_profiles
            if invalid_profiles:
                payload_box["ocr_invalid_profiles"] = invalid_profiles
            payload_boxes.append(
                payload_box
            )

        volume_context = get_volume_context(data.volume_id) or {}
        prior_summary = str(volume_context.get("rolling_summary") or "")
        prior_characters = volume_context.get("active_characters")
        if not isinstance(prior_characters, list):
            prior_characters = []
        prior_open_threads = volume_context.get("open_threads")
        if not isinstance(prior_open_threads, list):
            prior_open_threads = []
        prior_glossary = volume_context.get("glossary")
        if not isinstance(prior_glossary, list):
            prior_glossary = []

        store.update_job(job, progress=65, message="Translating page")
        ocr_profile_meta = _build_ocr_profile_meta(ocr_profiles)
        translation_payload = await asyncio.to_thread(
            run_agent_translate_page,
            volume_id=data.volume_id,
            filename=data.filename,
            boxes=payload_boxes,
            ocr_profiles=ocr_profile_meta,
            prior_context_summary=prior_summary,
            prior_characters=prior_characters,
            prior_open_threads=prior_open_threads,
            prior_glossary=prior_glossary,
            source_language=data.source_language,
            target_language=data.target_language,
            model_id=model_id,
            debug_id=job.id,
            max_output_tokens=(
                int(max_output_tokens)
                if isinstance(max_output_tokens, int | float)
                else None
            ),
            reasoning_effort=(
                str(reasoning_effort)
                if isinstance(reasoning_effort, str)
                else None
            ),
            temperature=(
                float(temperature)
                if isinstance(temperature, int | float)
                else None
            ),
        )
        if job.status == JobStatus.canceled:
            store.update_job(job, message="Canceled")
            store.update_job(job, progress=100)
            return {"processed": 0, "total": total_boxes, "updated": 0}

        translations = translation_payload.get("boxes", [])
        no_text_raw = translation_payload.get("no_text_boxes")
        no_text_box_indices: set[int] = set()
        if isinstance(no_text_raw, list):
            for item in no_text_raw:
                try:
                    no_text_box_indices.add(int(item))
                except (TypeError, ValueError):
                    continue
        updated = 0
        merged_ids: list[int] = []
        ordered_primary_ids: list[int] = []

        for entry in translations:
            box_ids_raw = entry.get("box_ids")
            if not isinstance(box_ids_raw, list):
                single_id = entry.get("box_id")
                if single_id is None:
                    continue
                box_ids_raw = [single_id]
            box_indices: list[int] = []
            for item in box_ids_raw:
                try:
                    box_indices.append(int(item))
                except (TypeError, ValueError):
                    continue
            if not box_indices:
                continue
            if any(box_index in no_text_box_indices for box_index in box_indices):
                continue
            mapped_ids = [box_index_map.get(box_index) for box_index in box_indices]
            box_ids = [box_id for box_id in mapped_ids if isinstance(box_id, int)]
            if not box_ids:
                continue

            primary_id = box_ids[0]
            ordered_primary_ids.append(primary_id)
            if len(box_ids) > 1:
                merged_ids.extend(box_ids[1:])

            ocr_text = entry.get("ocr_text")
            if isinstance(ocr_text, str):
                set_box_ocr_text_by_id(
                    data.volume_id,
                    data.filename,
                    box_id=primary_id,
                    ocr_text=ocr_text,
                )

            translation = entry.get("translation")
            if isinstance(translation, str):
                set_box_translation_by_id(
                    data.volume_id,
                    data.filename,
                    box_id=primary_id,
                    translation=translation,
                )
                updated += 1

        applied_order = False
        current_ids = {int(box.get("id") or 0) for box in text_boxes}
        mentioned_ids = set(ordered_primary_ids) | set(merged_ids)
        orphaned = list(current_ids - mentioned_ids)
        if orphaned:
            delete_boxes_by_ids(data.volume_id, data.filename, orphaned)
        if merged_ids:
            delete_boxes_by_ids(data.volume_id, data.filename, merged_ids)

        if ordered_primary_ids:
            applied_order = set_box_order_for_type(
                data.volume_id,
                data.filename,
                box_type="text",
                ordered_ids=ordered_primary_ids,
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
            story_summary
            if isinstance(story_summary, str) and story_summary.strip()
            else prior_summary
        )
        page_summary = story_summary if isinstance(story_summary, str) else ""
        page_image_summary = image_summary if isinstance(image_summary, str) else ""
        page_index = get_page_index(data.volume_id, data.filename)
        upsert_volume_context(
            data.volume_id,
            rolling_summary=rolling_summary,
            active_characters=characters,
            open_threads=open_threads,
            glossary=glossary,
            last_page_index=page_index,
        )
        upsert_page_context(
            data.volume_id,
            data.filename,
            page_summary=page_summary,
            image_summary=page_image_summary,
            characters_snapshot=characters,
            open_threads_snapshot=open_threads,
            glossary_snapshot=glossary,
        )

        store.update_job(job, progress=100, message="Agent translation complete")
        return {
            "processed": total_boxes,
            "total": total_boxes,
            "updated": updated,
            "orderApplied": applied_order,
            "characters": characters,
            "imageSummary": image_summary if isinstance(image_summary, str) else None,
            "storySummary": story_summary if isinstance(story_summary, str) else None,
            "openThreads": open_threads,
            "glossary": glossary,
        }
