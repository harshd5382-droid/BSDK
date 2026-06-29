"""Unit tests for the coordinator OpenAI proxy stream detection."""

from types import SimpleNamespace

from daios_node.app import NodeApp


def _req(accept: str | None = None):
    headers = {}
    if accept is not None:
        headers["accept"] = accept
    return SimpleNamespace(headers=headers)


def test_wants_stream_accept_header():
    assert NodeApp._wants_stream(_req("text/event-stream"), b"") is True


def test_wants_stream_body_true():
    assert NodeApp._wants_stream(_req(), b'{"stream": true}') is True
    assert NodeApp._wants_stream(_req(), b'{"stream":true}') is True


def test_wants_stream_body_false():
    assert NodeApp._wants_stream(_req(), b'{"stream": false}') is False
    assert NodeApp._wants_stream(_req(), b'{"messages": []}') is False


def test_wants_stream_empty_and_invalid():
    assert NodeApp._wants_stream(_req(), b"") is False
    assert NodeApp._wants_stream(_req(), b"not json") is False
