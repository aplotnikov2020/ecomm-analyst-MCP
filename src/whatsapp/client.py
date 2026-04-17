"""WhatsApp Business Cloud API client."""

import logging
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

WA_BASE = settings.whatsapp_api_base
PHONE_ID = settings.whatsapp_phone_number_id


class WhatsAppClient:
    """Async client for the WhatsApp Business Cloud API."""

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {settings.whatsapp_token}"},
            timeout=httpx.Timeout(30.0),
        )

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def send_text(self, to: str, text: str) -> bool:
        """Send a plain text message. Splits messages > 4096 chars automatically."""
        # WhatsApp has a 4096-char limit per message
        chunks = [text[i: i + 4096] for i in range(0, len(text), 4096)]
        success = True
        for chunk in chunks:
            ok = await self._send_message(to, {"type": "text", "text": {"body": chunk, "preview_url": False}})
            success = success and ok
        return success

    async def send_typing(self, to: str) -> bool:
        """Send a typing indicator (read receipt + typing status)."""
        try:
            await self._http.post(
                f"{WA_BASE}/{PHONE_ID}/messages",
                json={"messaging_product": "whatsapp", "status": "read", "message_id": "dummy"},
            )
        except Exception:
            pass  # Typing indicators are best-effort
        return True

    async def mark_read(self, message_id: str) -> bool:
        """Mark a received message as read."""
        try:
            resp = await self._http.post(
                f"{WA_BASE}/{PHONE_ID}/messages",
                json={
                    "messaging_product": "whatsapp",
                    "status": "read",
                    "message_id": message_id,
                },
            )
            return resp.status_code == 200
        except Exception as exc:
            logger.debug(f"Mark-read failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Media
    # ------------------------------------------------------------------

    async def get_media_url(self, media_id: str) -> Optional[str]:
        """Resolve a media_id to a downloadable URL."""
        try:
            resp = await self._http.get(f"{WA_BASE}/{media_id}")
            resp.raise_for_status()
            return resp.json().get("url")
        except Exception as exc:
            logger.error(f"Failed to get media URL for {media_id}: {exc}")
            return None

    async def download_media(self, url: str) -> Optional[bytes]:
        """Download media bytes from a WhatsApp media URL."""
        try:
            resp = await self._http.get(url)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            logger.error(f"Failed to download media: {exc}")
            return None

    async def get_and_download_media(self, media_id: str) -> Optional[bytes]:
        """Convenience: get URL then download in one call."""
        url = await self.get_media_url(media_id)
        if not url:
            return None
        return await self.download_media(url)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _send_message(self, to: str, message_body: dict) -> bool:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            **message_body,
        }
        try:
            resp = await self._http.post(f"{WA_BASE}/{PHONE_ID}/messages", json=payload)
            if resp.status_code not in (200, 201):
                logger.error(f"WhatsApp send failed [{resp.status_code}]: {resp.text[:300]}")
                return False
            return True
        except Exception as exc:
            logger.error(f"WhatsApp send exception: {exc}")
            return False
