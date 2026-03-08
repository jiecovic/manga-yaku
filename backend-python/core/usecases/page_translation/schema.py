# backend-python/core/usecases/page_translation/schema.py
"""Structured payload schema helpers for the page-translation workflow."""

from __future__ import annotations

from . import schema_formats as _schema_formats
from . import schema_json as _schema_json
from . import schema_normalization as _schema_normalization
from . import stage_outputs as _stage_outputs

JsonParser = _schema_json.JsonParser
extract_json = _schema_json.extract_json
json_result_validator = _schema_json.json_result_validator
repair_json = _schema_json.repair_json
should_retry = _schema_json.should_retry
build_translate_stage_text_format = _schema_formats.build_translate_stage_text_format
build_state_merge_text_format = _schema_formats.build_state_merge_text_format
coerce_positive_int = _schema_normalization.coerce_positive_int
normalize_translate_stage_result = _schema_normalization.normalize_translate_stage_result
normalize_state_merge_result = _schema_normalization.normalize_state_merge_result
apply_no_text_consensus_guard = _stage_outputs.apply_no_text_consensus_guard
summarize_translate_stage_coverage = _stage_outputs.summarize_translate_stage_coverage
