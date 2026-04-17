"""Tests for webhook parsing and routing."""

import pytest
from src.whatsapp.webhook import WebhookHandler, IncomingMessage


@pytest.fixture
def handler():
    return WebhookHandler()


def _make_payload(msg_type: str, content: dict) -> dict:
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "id": "msg_123",
                        "from": "+15551234567",
                        "type": msg_type,
                        **content,
                    }]
                }
            }]
        }]
    }


def test_parse_text_message(handler):
    payload = _make_payload("text", {"text": {"body": "Analyse yoga mats"}})
    msg = handler.parse_message(payload)
    assert isinstance(msg, IncomingMessage)
    assert msg.msg_type == "text"
    assert msg.text == "Analyse yoga mats"
    assert msg.from_number == "+15551234567"


def test_parse_image_message(handler):
    payload = _make_payload("image", {"image": {"id": "media_456", "mime_type": "image/jpeg"}})
    msg = handler.parse_message(payload)
    assert msg is not None
    assert msg.msg_type == "image"
    assert msg.media_id == "media_456"


def test_parse_audio_message(handler):
    payload = _make_payload("audio", {"audio": {"id": "audio_789", "mime_type": "audio/ogg"}})
    msg = handler.parse_message(payload)
    assert msg is not None
    assert msg.msg_type == "audio"
    assert msg.mime_type == "audio/ogg"


def test_parse_status_update_returns_none(handler):
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": "abc", "status": "delivered"}]}}]}]}
    msg = handler.parse_message(payload)
    assert msg is None


def test_parse_empty_payload_returns_none(handler):
    msg = handler.parse_message({})
    assert msg is None


def test_parse_unknown_type_returns_none(handler):
    payload = _make_payload("sticker", {"sticker": {"id": "sticker_123"}})
    msg = handler.parse_message(payload)
    assert msg is None
