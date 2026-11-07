"""Tests for token redaction and handshake error handling."""
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import aiohttp
from multidict import CIMultiDict
import pytest
from yarl import URL

import plexwebsocket
from plexwebsocket import (
    ERROR_AUTH_FAILURE,
    ERROR_UNKNOWN,
    PLEX_TOKEN_PARAM,
    STATE_DISCONNECTED,
    STATE_STOPPED,
    PlexWebsocket,
    _redact,
)

TOKEN = "s3cr3t-token"
URI = f"https://plex.example/:/websockets/notifications?{PLEX_TOKEN_PARAM}={TOKEN}"


def test_redact_masks_token_only():
    out = _redact(Exception(f"url='{URI}&other=1'"))
    assert TOKEN not in out
    assert f"{PLEX_TOKEN_PARAM}=REDACTED&other=1" in out


def _handshake_error(status):
    url = URL(URI.replace("https", "wss"))
    info = aiohttp.RequestInfo(url, "GET", CIMultiDict(), url)
    return aiohttp.WSServerHandshakeError(
        info, (), status=status, message="Invalid response status"
    )


def _run(error, caplog, monkeypatch):
    monkeypatch.setattr(plexwebsocket.asyncio, "sleep", AsyncMock())
    server = MagicMock()
    server.url.return_value = URI
    session = MagicMock()
    session.ws_connect.side_effect = error
    callback = MagicMock()

    ws = PlexWebsocket(server, callback, session=session)
    with caplog.at_level(logging.DEBUG):
        asyncio.run(ws.running())
    return ws, callback


@pytest.mark.parametrize(
    "status, state, reason",
    [
        (401, STATE_STOPPED, ERROR_AUTH_FAILURE),
        (403, STATE_STOPPED, ERROR_UNKNOWN),
        (502, STATE_DISCONNECTED, None),
    ],
)
def test_handshake_error(status, state, reason, caplog, monkeypatch):
    ws, callback = _run(_handshake_error(status), caplog, monkeypatch)

    assert ws.state == state
    callback.assert_called_with(plexwebsocket.SIGNAL_CONNECTION_STATE, state, reason)
    assert str(status) in caplog.text
    assert TOKEN not in caplog.text


def test_connection_error_retry(caplog, monkeypatch):
    error = aiohttp.ClientConnectionError(f"Cannot connect to {URI}")
    ws, _ = _run(error, caplog, monkeypatch)

    assert ws.state == STATE_DISCONNECTED
    assert ws.failed_attempts == 1
    plexwebsocket.asyncio.sleep.assert_awaited_once_with(5)
    assert "retrying" in caplog.text
    assert TOKEN not in caplog.text
