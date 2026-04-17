"""WhatsApp webhook payload parsing and message routing."""

import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.agent.core import AgentCore

logger = logging.getLogger(__name__)


class IncomingMessage:
    """Normalised representation of an incoming WhatsApp message."""

    def __init__(
        self,
        message_id: str,
        from_number: str,
        msg_type: str,
        text: Optional[str] = None,
        media_id: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> None:
        self.message_id = message_id
        self.from_number = from_number
        self.msg_type = msg_type  # "text", "image", "audio", "document"
        self.text = text
        self.media_id = media_id
        self.mime_type = mime_type

    def __repr__(self) -> str:
        return f"<IncomingMessage {self.msg_type} from={self.from_number}>"


class WebhookHandler:
    """Parse and route incoming WhatsApp webhook events."""

    def parse_message(self, body: dict) -> Optional[IncomingMessage]:
        """Extract a normalised IncomingMessage from the raw webhook payload.

        Returns None for non-message events (delivery receipts, status updates, etc.).
        """
        try:
            entry = body.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            messages = value.get("messages", [])

            if not messages:
                return None  # status update, not a message

            msg = messages[0]
            msg_type = msg.get("type", "unknown")
            from_number = msg.get("from", "")
            message_id = msg.get("id", "")

            if msg_type == "text":
                return IncomingMessage(
                    message_id=message_id,
                    from_number=from_number,
                    msg_type="text",
                    text=msg.get("text", {}).get("body", ""),
                )

            if msg_type in ("image", "video"):
                media = msg.get(msg_type, {})
                return IncomingMessage(
                    message_id=message_id,
                    from_number=from_number,
                    msg_type="image",
                    media_id=media.get("id"),
                    mime_type=media.get("mime_type", "image/jpeg"),
                )

            if msg_type == "audio":
                audio = msg.get("audio", {})
                return IncomingMessage(
                    message_id=message_id,
                    from_number=from_number,
                    msg_type="audio",
                    media_id=audio.get("id"),
                    mime_type=audio.get("mime_type", "audio/ogg"),
                )

            if msg_type == "document":
                doc = msg.get("document", {})
                return IncomingMessage(
                    message_id=message_id,
                    from_number=from_number,
                    msg_type="image",  # treat documents as images if visual
                    media_id=doc.get("id"),
                    mime_type=doc.get("mime_type", "image/jpeg"),
                )

            logger.info(f"Unhandled message type '{msg_type}' — ignoring")
            return None

        except Exception as exc:
            logger.error(f"Failed to parse webhook payload: {exc}", exc_info=True)
            return None

    async def process(self, body: dict, agent: Any) -> None:
        """Parse the webhook body and route to the agent for handling."""
        if not agent:
            logger.warning("Agent not initialised — dropping message")
            return

        msg = self.parse_message(body)
        if msg:
            logger.info(f"Processing {msg}")
            await agent.handle_message(msg)
