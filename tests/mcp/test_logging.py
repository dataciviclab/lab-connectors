"""Tests per lab_connectors.mcp.logging."""
from __future__ import annotations

import logging

import pytest

from lab_connectors.mcp.logging import get_mcp_logger


class TestMcpLogger:
    def test_info_logs_message(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        logger = get_mcp_logger("test-server")
        logger.info("test_tool", "Messaggio di test", url="https://example.com")
        assert "test_tool" in caplog.text
        assert "Messaggio di test" in caplog.text

    def test_warning_logs_message(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        logger = get_mcp_logger("test-server")
        logger.warning("test_tool", "Attenzione", codice=404)
        assert "Attenzione" in caplog.text

    def test_error_logs_message(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.ERROR)
        logger = get_mcp_logger("test-server")
        logger.error("test_tool", "Errore grave", error_code="timeout")
        assert "Errore grave" in caplog.text

    def test_timed_logs_duration(self, caplog: pytest.LogCaptureFixture) -> None:
        import time
        caplog.set_level(logging.INFO)
        logger = get_mcp_logger("test-server")
        start = time.monotonic()
        time.sleep(0.001)
        logger.timed("test_tool", "Operazione completata", start)
        assert "Operazione completata" in caplog.text
        assert "duration_ms" in caplog.text

    def test_get_mcp_logger_caches(self) -> None:
        a = get_mcp_logger("cache-test")
        b = get_mcp_logger("cache-test")
        assert a is b

    def test_get_mcp_logger_different_names(self) -> None:
        a = get_mcp_logger("server-a")
        b = get_mcp_logger("server-b")
        assert a is not b
