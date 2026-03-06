# backend-python/tests/core/usecases/test_agent_stream_event_formatting.py
from core.usecases.agent.stream_event_formatting import (
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
