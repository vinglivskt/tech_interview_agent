from __future__ import annotations

import logging

import httpx
from src.main import _log_ingest_failure


class TestLogIngestFailure:
    def _log(self, exc: Exception, caplog) -> logging.LogRecord:
        with caplog.at_level(logging.DEBUG, logger="src.main"):
            _log_ingest_failure(exc, phase="Первая индексация docx не удалась", ollama_url="http://o:11434")
        assert caplog.records
        return caplog.records[-1]

    def test_connect_error_is_concise_hint_without_traceback(self, caplog) -> None:
        record = self._log(httpx.ConnectError("All connection attempts failed"), caplog)
        assert record.levelno == logging.WARNING
        assert record.exc_info is None
        assert "Индексация docx пропущена" in record.getMessage()
        assert "http://o:11434" in record.getMessage()

    def test_connect_timeout_is_also_treated_as_unavailable(self, caplog) -> None:
        record = self._log(httpx.ConnectTimeout("timeout"), caplog)
        assert record.levelno == logging.WARNING
        assert record.exc_info is None

    def test_unexpected_error_keeps_traceback(self, caplog) -> None:
        record = self._log(ValueError("битая схема вектора"), caplog)
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None
        assert "битая схема вектора" in record.getMessage()