"""FastAPI entry point — WhatsApp Product Analysis Agent."""

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from src.config import settings
from src.agent.core import AgentCore
from src.whatsapp.webhook import WebhookHandler

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# Global agent instance — shared across requests within one Cloud Run instance
_agent: AgentCore | None = None
_webhook_handler = WebhookHandler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    logger.info("Starting up WhatsApp Product Analysis Agent...")
    _agent = AgentCore()
    await _agent.start()
    logger.info("Agent started — ready to receive messages")
    yield
    logger.info("Shutting down agent...")
    if _agent:
        await _agent.stop()
    logger.info("Shutdown complete")


app = FastAPI(
    title="WhatsApp Product Analysis Agent",
    description=(
        "AI-powered e-commerce product analysis agent via WhatsApp. "
        "Accepts product photos, audio, and text. Powered by Claude Opus 4.7 + MCP."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "whatsapp-product-analysis-agent",
        "model": settings.openrouter_model,
        "mcp_servers": ["ecomm", "trends", "market"],
    }


# ---------------------------------------------------------------------------
# WhatsApp webhook — verification (GET) and message receipt (POST)
# ---------------------------------------------------------------------------

@app.get("/webhook")
async def verify_webhook(
    mode: str = Query(alias="hub.mode"),
    token: str = Query(alias="hub.verify_token"),
    challenge: str = Query(alias="hub.challenge"),
) -> PlainTextResponse:
    """WhatsApp webhook verification handshake."""
    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        logger.info("Webhook verified successfully")
        return PlainTextResponse(challenge)
    logger.warning(f"Webhook verification failed — token mismatch")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@app.post("/webhook")
async def receive_webhook(request: Request) -> dict:
    """Receive and process incoming WhatsApp messages.

    Processes asynchronously so WhatsApp gets a fast 200 response.
    """
    body = await request.json()
    # Fire-and-forget — WhatsApp requires a 200 within 20s
    asyncio.create_task(_webhook_handler.process(body, _agent))
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Dev / testing endpoint (no-WhatsApp direct chat)
# ---------------------------------------------------------------------------

@app.post("/dev/chat")
async def dev_chat(request: Request) -> dict:
    """Test the agent directly without WhatsApp (dev only).

    Body: {"from": "+15551234567", "text": "Analyse running shoes demand"}
    """
    if not _agent:
        raise HTTPException(status_code=503, detail="Agent not ready")

    body = await request.json()
    from_number = body.get("from", "dev-user")
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="'text' field required")

    from src.whatsapp.webhook import IncomingMessage
    msg = IncomingMessage(
        message_id="dev-msg",
        from_number=from_number,
        msg_type="text",
        text=text,
    )

    # Capture reply instead of sending via WhatsApp
    replies: list[str] = []
    original_send = _agent._wa.send_text

    async def capture_send(to: str, text: str) -> bool:
        replies.append(text)
        return True

    _agent._wa.send_text = capture_send  # type: ignore[method-assign]
    await _agent.handle_message(msg)
    _agent._wa.send_text = original_send  # type: ignore[method-assign]

    return {"reply": "\n".join(replies), "from": from_number}


if __name__ == "__main__":
    uvicorn.run("src.main:app", host="0.0.0.0", port=8080, log_level="info")
