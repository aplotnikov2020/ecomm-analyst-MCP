"""Agent core — orchestrates the LLM via OpenRouter, MCP connections, and conversation state."""

import json
import logging
from contextlib import AsyncExitStack
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import openai

from src.agent.prompts import SYSTEM_PROMPT
from src.config import settings
from src.media.audio import transcribe_audio
from src.media.image import detect_mime_from_bytes, encode_image_for_openai
from src.whatsapp.client import WhatsAppClient
from src.whatsapp.webhook import IncomingMessage

logger = logging.getLogger(__name__)

MCP_SERVERS = {
    "ecomm": ["python", "-m", "mcp_servers.ecomm_server"],
    "trends": ["python", "-m", "mcp_servers.trends_server"],
    "market": ["python", "-m", "mcp_servers.market_server"],
}


class AgentCore:
    """Manages MCP connections, LLM conversations via OpenRouter, and WhatsApp I/O."""

    def __init__(self) -> None:
        self._openai = openai.AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
        self._wa = WhatsAppClient()
        self._exit_stack = AsyncExitStack()
        self._mcp_sessions: dict[str, Any] = {}
        self._tool_registry: dict[str, Any] = {}
        self._openai_tools: list[dict] = []
        self._db: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start MCP servers and establish client connections."""
        await self._exit_stack.__aenter__()
        await self._connect_mcp_servers()
        await self._build_tool_registry()
        self._init_firestore()
        logger.info(
            f"Agent ready — {len(self._openai_tools)} tools across "
            f"{len(self._mcp_sessions)} MCP servers"
        )

    async def stop(self) -> None:
        """Gracefully close MCP connections."""
        await self._exit_stack.aclose()
        await self._wa.close()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def handle_message(self, msg: IncomingMessage) -> None:
        """Process an incoming WhatsApp message end-to-end."""
        await self._wa.mark_read(msg.message_id)

        user_content: list[dict] = []

        if msg.msg_type == "audio":
            user_content = await self._handle_audio(msg)
        elif msg.msg_type == "image":
            user_content = await self._handle_image(msg)
        else:
            user_content = [{"type": "text", "text": msg.text or ""}]

        if not user_content:
            await self._wa.send_text(
                msg.from_number,
                "⚠️ I couldn't process that message. Please try sending text, a product photo, or a voice note.",
            )
            return

        history = await self._load_history(msg.from_number)

        try:
            reply = await self._run_agent(user_content, history)
        except Exception as exc:
            logger.error(f"Agent error for {msg.from_number}: {exc}", exc_info=True)
            reply = "⚠️ I encountered an error while analysing your request. Please try again."

        await self._save_history(msg.from_number, history, user_content, reply)
        await self._wa.send_text(msg.from_number, reply)

    # ------------------------------------------------------------------
    # Media handling
    # ------------------------------------------------------------------

    async def _handle_audio(self, msg: IncomingMessage) -> list[dict]:
        if not msg.media_id:
            return [{"type": "text", "text": "[audio message received but no media_id]"}]

        audio_bytes = await self._wa.get_and_download_media(msg.media_id)
        if not audio_bytes:
            return [{"type": "text", "text": "[could not download audio]"}]

        transcript = await transcribe_audio(audio_bytes, msg.mime_type or "audio/ogg")
        if transcript:
            return [{"type": "text", "text": f"[Voice message]: {transcript}"}]

        return []

    async def _handle_image(self, msg: IncomingMessage) -> list[dict]:
        if not msg.media_id:
            return []

        image_bytes = await self._wa.get_and_download_media(msg.media_id)
        if not image_bytes:
            return []

        mime = msg.mime_type or detect_mime_from_bytes(image_bytes)
        image_block = encode_image_for_openai(image_bytes, mime)
        if not image_block:
            return []

        return [
            image_block,
            {
                "type": "text",
                "text": (
                    "I've sent you a product photo. Please identify the product category and type, "
                    "then ask me what kind of analysis I would like (demand, supply, trends, seasonality, "
                    "or a full market overview)."
                ),
            },
        ]

    # ------------------------------------------------------------------
    # Agentic loop
    # ------------------------------------------------------------------

    async def _run_agent(self, user_content: list[dict], history: list[dict]) -> str:
        """Run the agentic loop with OpenRouter + MCP tool use."""
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_content},
        ]

        last_content: Optional[str] = None

        for _ in range(settings.max_tool_iterations):
            response = await self._openai.chat.completions.create(
                model=settings.openrouter_model,
                max_tokens=4096,
                messages=messages,
                tools=self._openai_tools if self._openai_tools else None,
            )

            choice = response.choices[0]
            msg = choice.message
            last_content = msg.content or ""

            if choice.finish_reason == "stop":
                return last_content

            if choice.finish_reason == "tool_calls":
                tool_calls = msg.tool_calls or []

                # Append assistant turn with the tool_calls the model issued
                messages.append({
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                })

                # Execute each tool call and append result messages
                for tc in tool_calls:
                    tool_name = tc.function.name
                    try:
                        tool_input = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        tool_input = {}
                    logger.info(f"Executing tool: {tool_name}({tc.function.arguments[:200]})")
                    result_text = await self._call_mcp_tool(tool_name, tool_input)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_text,
                    })
                continue

            logger.warning(f"Unexpected finish_reason: {choice.finish_reason}")
            return last_content or "Analysis complete."

        return last_content or "Analysis complete (tool limit reached)."

    async def _call_mcp_tool(self, tool_name: str, tool_input: dict) -> str:
        """Route a tool call to the appropriate MCP server session."""
        session = self._tool_registry.get(tool_name)
        if not session:
            logger.warning(f"Tool '{tool_name}' not found in registry")
            return json.dumps({"error": f"Tool '{tool_name}' not available"})

        try:
            result = await session.call_tool(tool_name, tool_input)
            if result.content:
                return " ".join(
                    item.text for item in result.content if hasattr(item, "text")
                )
            return json.dumps({"result": "empty"})
        except Exception as exc:
            logger.error(f"MCP tool '{tool_name}' failed: {exc}")
            return json.dumps({"error": str(exc)})

    # ------------------------------------------------------------------
    # MCP connection management
    # ------------------------------------------------------------------

    async def _connect_mcp_servers(self) -> None:
        """Start each MCP server subprocess and open a client session."""
        try:
            from mcp import ClientSession, StdioServerParameters  # type: ignore[import]
            from mcp.client.stdio import stdio_client  # type: ignore[import]
        except ImportError:
            logger.warning("mcp library not installed — running without MCP tools")
            return

        for name, cmd in MCP_SERVERS.items():
            try:
                params = StdioServerParameters(
                    command=cmd[0],
                    args=cmd[1:],
                    env={**__import__("os").environ},
                )
                read, write = await self._exit_stack.enter_async_context(stdio_client(params))
                session = await self._exit_stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self._mcp_sessions[name] = session
                logger.info(f"Connected to MCP server: {name}")
            except Exception as exc:
                logger.error(f"Failed to connect to MCP server '{name}': {exc}")

    async def _build_tool_registry(self) -> None:
        """Query each MCP session for its tools and build the OpenAI function-call tool list."""
        for name, session in self._mcp_sessions.items():
            try:
                tools_result = await session.list_tools()
                for tool in tools_result.tools:
                    self._tool_registry[tool.name] = session
                    self._openai_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or f"Tool: {tool.name}",
                            "parameters": tool.inputSchema or {
                                "type": "object",
                                "properties": {},
                            },
                        },
                    })
                logger.info(f"Registered {len(tools_result.tools)} tools from '{name}'")
            except Exception as exc:
                logger.error(f"Failed to list tools from '{name}': {exc}")

    # ------------------------------------------------------------------
    # Conversation persistence (Firestore)
    # ------------------------------------------------------------------

    def _init_firestore(self) -> None:
        try:
            from google.cloud import firestore  # type: ignore[import]
            self._db = firestore.AsyncClient(project=settings.gcp_project_id)
            logger.info("Firestore client initialised")
        except Exception as exc:
            logger.warning(f"Firestore unavailable — using in-memory history: {exc}")
            self._db = None
            self._in_memory_history: dict[str, list] = {}

    async def _load_history(self, user_id: str) -> list[dict]:
        """Load conversation history for a user (last N turns)."""
        max_turns = settings.max_conversation_turns

        if self._db:
            try:
                doc_ref = self._db.collection(settings.firestore_collection).document(user_id)
                doc = await doc_ref.get()
                if doc.exists:
                    data = doc.to_dict()
                    messages = data.get("messages", [])
                    return messages[-max_turns * 2:]
            except Exception as exc:
                logger.error(f"Firestore load failed: {exc}")
        else:
            history = self._in_memory_history.get(user_id, [])
            return history[-max_turns * 2:]

        return []

    async def _save_history(
        self,
        user_id: str,
        history: list[dict],
        user_content: list[dict],
        assistant_reply: str,
    ) -> None:
        """Persist the updated conversation history."""
        text_parts = [b["text"] for b in user_content if b.get("type") == "text"]
        stored_user_content = " ".join(text_parts) if text_parts else "[media message]"

        new_messages = history + [
            {"role": "user", "content": stored_user_content},
            {"role": "assistant", "content": assistant_reply},
        ]
        max_turns = settings.max_conversation_turns
        new_messages = new_messages[-(max_turns * 2):]

        ttl = datetime.now(tz=timezone.utc) + timedelta(hours=settings.conversation_ttl_hours)

        if self._db:
            try:
                doc_ref = self._db.collection(settings.firestore_collection).document(user_id)
                await doc_ref.set({
                    "messages": new_messages,
                    "last_updated": firestore_server_timestamp(),
                    "ttl": ttl,
                })
            except Exception as exc:
                logger.error(f"Firestore save failed: {exc}")
        else:
            self._in_memory_history[user_id] = new_messages


def firestore_server_timestamp():
    """Return Firestore SERVER_TIMESTAMP sentinel if available, else now."""
    try:
        from google.cloud import firestore  # type: ignore[import]
        return firestore.SERVER_TIMESTAMP
    except Exception:
        return datetime.now(tz=timezone.utc)
