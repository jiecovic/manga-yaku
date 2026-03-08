# backend-python/tests/core/usecases/test_agent_stream_event_formatting.py
from core.usecases.agent.runtime.stream_event_formatting import (
    coerce_tool_output_dict,
    extract_page_switch_filename,
    summarize_tool_output,
)


def test_coerce_tool_output_dict_parses_text_content_list() -> None:
    output = [
        {
            "type": "text",
            "text": '{"status":"ok","filename":"003.jpg","text_box_count":12}',
        }
    ]
    parsed = coerce_tool_output_dict(output)
    assert parsed == {
        "status": "ok",
        "filename": "003.jpg",
        "text_box_count": 12,
    }


def test_coerce_tool_output_dict_parses_single_text_item_dict() -> None:
    output = {
        "type": "text",
        "text": '{"status":"ok","filename":"004.jpg","text_box_count":7}',
    }
    parsed = coerce_tool_output_dict(output)
    assert parsed == {
        "status": "ok",
        "filename": "004.jpg",
        "text_box_count": 7,
    }


def test_extract_page_switch_filename_from_dict_output() -> None:
    filename = extract_page_switch_filename(
        "set_active_page",
        {"status": "ok", "filename": "009.jpg"},
    )
    assert filename == "009.jpg"


def test_extract_page_switch_filename_from_shift_tool() -> None:
    filename = extract_page_switch_filename(
        "shift_active_page",
        {"status": "ok", "filename": "010.jpg", "moved_by": 1},
    )
    assert filename == "010.jpg"


def test_summarize_tool_output_set_active_page() -> None:
    summary = summarize_tool_output(
        "set_active_page",
        {"status": "ok", "filename": "007.jpg", "text_box_count": 5},
    )
    assert summary == "active page switched to 007.jpg (5 text boxes)"


def test_summarize_tool_output_shift_active_page() -> None:
    summary = summarize_tool_output(
        "shift_active_page",
        {"status": "ok", "filename": "008.jpg", "moved_by": 1},
    )
    assert summary == "active page moved forward to 008.jpg"


def test_summarize_tool_output_set_text_box_note() -> None:
    summary = summarize_tool_output(
        "set_text_box_note",
        {"status": "ok", "filename": "001.jpg", "box_id": 3},
    )
    assert summary == "updated note for box #3 on 001.jpg"


def test_summarize_tool_output_get_page_memory() -> None:
    summary = summarize_tool_output(
        "get_page_memory",
        {
            "filename": "001.jpg",
            "characters": [{"name": "Saitama", "gender": "male", "info": "hero"}],
            "open_threads": ["thread"],
            "glossary": [{"term": "hero", "translation": "hero", "note": ""}],
        },
    )
    assert summary == "page memory loaded: 1 characters, 1 open threads, 1 glossary terms"


def test_summarize_tool_output_list_text_boxes_with_counts() -> None:
    summary = summarize_tool_output(
        "list_text_boxes",
        {
            "filename": "004.jpg",
            "total": 18,
            "ocr_filled_count": 18,
            "translated_count": 0,
        },
    )
    assert summary == "18 text boxes on 004.jpg (18 OCR, 0 translated)"


def test_summarize_tool_output_detect_text_boxes_replay() -> None:
    summary = summarize_tool_output(
        "detect_text_boxes",
        {
            "status": "ok",
            "filename": "001.jpg",
            "idempotency_state": "replay",
        },
    )
    assert summary == "reused detection result for 001.jpg"


def test_summarize_tool_output_detect_text_boxes_no_new_boxes() -> None:
    summary = summarize_tool_output(
        "detect_text_boxes",
        {
            "status": "ok",
            "filename": "001.jpg",
            "replace_existing": False,
            "new_box_count": 0,
            "total_text_box_count": 12,
        },
    )
    assert summary == "no new text boxes detected on 001.jpg; preserved existing boxes"


def test_summarize_tool_output_ocr_text_box_skipped_existing() -> None:
    summary = summarize_tool_output(
        "ocr_text_box",
        {
            "status": "skipped_existing",
            "filename": "001.jpg",
            "box_id": 5,
        },
    )
    assert summary == "skipped OCR for box #5 on 001.jpg; text already exists"


def test_summarize_tool_output_translate_active_page_completed() -> None:
    summary = summarize_tool_output(
        "translate_active_page",
        {
            "status": "completed",
            "filename": "004.jpg",
            "updated": 18,
            "total": 18,
        },
    )
    assert summary == "page workflow completed for 004.jpg (18/18 boxes updated)"


def test_summarize_tool_output_translate_active_page_already_translated() -> None:
    summary = summarize_tool_output(
        "translate_active_page",
        {
            "status": "already_translated",
            "filename": "006.jpg",
            "translated_count": 8,
            "text_box_count": 8,
        },
    )
    assert summary == "page 006.jpg was already translated (8/8 boxes)"


def test_summarize_tool_output_translate_active_page_started_now() -> None:
    summary = summarize_tool_output(
        "translate_active_page",
        {
            "status": "queued",
            "filename": "006.jpg",
            "started_now": True,
        },
    )
    assert summary == "started page workflow for 006.jpg"
