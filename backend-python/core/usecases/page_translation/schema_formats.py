# backend-python/core/usecases/page_translation/schema_formats.py
"""JSON schema format definitions for page-translation stages."""

from __future__ import annotations

from typing import Any


def build_translate_stage_text_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "translate_page_stage1",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "boxes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "box_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                            "ocr_profile_id": {"type": "string"},
                            "ocr_text": {"type": "string"},
                            "speaker_id": {"type": "string"},
                            "addressee_id": {"type": "string"},
                            "speaker_gender": {
                                "type": "string",
                                "enum": ["male", "female", "unknown"],
                            },
                            "speaker_visual_cues": {"type": "string"},
                            "referent_id": {"type": "string"},
                            "referent_gender": {
                                "type": "string",
                                "enum": ["male", "female", "unknown"],
                            },
                            "translation": {"type": "string"},
                        },
                        "required": [
                            "box_ids",
                            "ocr_profile_id",
                            "ocr_text",
                            "speaker_id",
                            "addressee_id",
                            "speaker_gender",
                            "speaker_visual_cues",
                            "referent_id",
                            "referent_gender",
                            "translation",
                        ],
                    },
                },
                "no_text_boxes": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
                "image_summary": {"type": "string"},
                "page_events": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "page_characters_detected": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "speaker_id": {"type": "string"},
                            "speaker_gender": {
                                "type": "string",
                                "enum": ["male", "female", "unknown"],
                            },
                            "speaker_visual_cues": {"type": "string"},
                        },
                        "required": ["speaker_id", "speaker_gender", "speaker_visual_cues"],
                    },
                },
            },
            "required": [
                "boxes",
                "no_text_boxes",
                "image_summary",
                "page_events",
                "page_characters_detected",
            ],
        },
        "strict": True,
    }


def build_state_merge_text_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "translate_page_stage2",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "characters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "gender": {"type": "string"},
                            "info": {"type": "string"},
                        },
                        "required": ["name", "gender", "info"],
                    },
                },
                "story_summary": {"type": "string"},
                "open_threads": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "glossary": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "term": {"type": "string"},
                            "translation": {"type": "string"},
                            "note": {"type": "string"},
                        },
                        "required": ["term", "translation", "note"],
                    },
                },
            },
            "required": [
                "characters",
                "story_summary",
                "open_threads",
                "glossary",
            ],
        },
        "strict": True,
    }
