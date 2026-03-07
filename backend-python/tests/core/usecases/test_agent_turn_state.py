# backend-python/tests/core/usecases/test_agent_turn_state.py
from core.usecases.agent.turn_state import sanitize_agent_reply_text


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
