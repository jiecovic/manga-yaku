# backend-python/tests/infra/logging/test_correlation.py
"""Unit tests for shared logging correlation helpers."""

from __future__ import annotations

import unittest

from infra.logging.correlation import append_correlation, normalize_correlation, with_correlation


class CorrelationHelpersTests(unittest.TestCase):
    def test_normalize_correlation_maps_aliases(self) -> None:
        normalized = normalize_correlation(
            {
                "component": "agent.reply.stream",
                "jobId": "job-1",
                "workflowRunId": "wf-1",
                "sessionId": "sess-1",
                "volumeId": "Akuhamu",
                "currentFilename": "001.jpg",
                "requestId": "req_123",
                "box_id": 7,
            }
        )

        self.assertEqual(
            normalized,
            {
                "component": "agent.reply.stream",
                "job_id": "job-1",
                "workflow_run_id": "wf-1",
                "session_id": "sess-1",
                "volume_id": "Akuhamu",
                "filename": "001.jpg",
                "request_id": "req_123",
                "box_id": 7,
            },
        )

    def test_append_correlation_formats_suffix(self) -> None:
        message = append_correlation(
            "agent stream start",
            {
                "component": "agent.reply.stream",
                "session_id": "sess-1",
                "filename": "001.jpg",
            },
            max_messages=20,
        )

        self.assertEqual(
            message,
            (
                "agent stream start | component=agent.reply.stream "
                "session_id=sess-1 filename=001.jpg max_messages=20"
            ),
        )

    def test_append_correlation_preserves_generic_correlation_fields(self) -> None:
        message = append_correlation(
            "Unhandled exception",
            {
                "component": "api.errors",
                "method": "GET",
                "path": "/api/logs/llm-calls",
            },
        )

        self.assertEqual(
            message,
            (
                "Unhandled exception | component=api.errors "
                "method=GET path=/api/logs/llm-calls"
            ),
        )

    def test_with_correlation_enriches_payload(self) -> None:
        payload = with_correlation(
            {"value": 1},
            {"component": "agent.translate_page", "debug_id": "job-9"},
            volumeId="Akuhamu",
        )

        self.assertEqual(payload["value"], 1)
        self.assertEqual(
            payload["correlation"],
            {
                "component": "agent.translate_page",
                "job_id": "job-9",
                "volume_id": "Akuhamu",
            },
        )
