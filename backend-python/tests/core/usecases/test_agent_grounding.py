# backend-python/tests/core/usecases/test_agent_grounding.py
from unittest.mock import patch

from core.usecases.agent.grounding.active_page import get_active_page_snapshot
from core.usecases.agent.grounding.reply_guards import sanitize_agent_reply_text


def test_cross_page_fact_query_allows_other_page_reference() -> None:
    response, reason = sanitize_agent_reply_text(
        response_text="He is called Baron Hamu on 003.jpg.",
        messages=[{"role": "user", "content": "on which page is he called baron hamu?"}],
        active_filename="009.jpg",
        active_text_box_count=7,
    )
    assert reason is None
    assert response == "He is called Baron Hamu on 003.jpg."


def test_active_page_query_blocks_other_page_reference() -> None:
    response, reason = sanitize_agent_reply_text(
        response_text="On 003.jpg there are 12 text boxes.",
        messages=[{"role": "user", "content": "what is on this page?"}],
        active_filename="009.jpg",
        active_text_box_count=7,
    )
    assert reason == "stale_context_warning"
    assert response == "On 003.jpg there are 12 text boxes."


def test_navigation_query_blocks_wrong_page_reference() -> None:
    response, reason = sanitize_agent_reply_text(
        response_text="You are now on 000.jpg.",
        messages=[{"role": "user", "content": "go to next page"}],
        active_filename="001.jpg",
        active_text_box_count=6,
    )
    assert reason == "stale_context_warning"
    assert response == "You are now on 000.jpg."


def test_get_active_page_snapshot_loads_page_once() -> None:
    with patch(
        "core.usecases.agent.grounding.active_page.load_page",
        return_value={
            "boxes": [
                {"id": 1, "type": "text", "orderIndex": 1},
                {"id": 2, "type": "image", "orderIndex": 2},
                {"id": 0, "type": "text", "orderIndex": 3},
            ]
        },
    ) as load_page_mock:
        snapshot = get_active_page_snapshot(
            volume_id="vol-a",
            current_filename="001.jpg",
        )

    assert snapshot.filename == "001.jpg"
    assert snapshot.text_box_count == 1
    assert snapshot.page_revision is not None
    assert len(snapshot.page_revision) == 16
    load_page_mock.assert_called_once_with("vol-a", "001.jpg")
