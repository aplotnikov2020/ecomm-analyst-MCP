"""Agent core — orchestrates Claude, MCP connections, and conversation state."""

import json
import logging
import sys
from contextlib import AsyncExitStack
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import anthropic

from src.agent.prompts import SYSTEM_PROMPT
from src.config import settings
from src.media.audio import transcribe_audio
from src.media.image import detect_mime_from_bytes, encode_image_for_claude
from src.whatsapp.client import WhatsAppClient
from src.whatsapp.webhook import IncomingMessage

logger = logging.getLogger(__name__)

MCP_SERVERS = {
    "ecomm": ["python", "-m", "mcp_servers.ecomm_server"],
    "trends": ["python", "-m", "mcp_servers.trends_server"],
    "market": ["python", "-m", "mcp_servers.market_server"],
}


class AgentCore:
    """Manages MCP connections, Claude conversations, and WhatsApp I/O."""

    def __init__(self) -> None:
        self._anthropic = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._wa = WhatsAppClient()
        self._exit_stack = AsyncExitStack()
        self._mcp_sessions: dict[str, Any] = {}
        self._tool_registry: dict[str, Any] = {}  # tool_name -> mcp session
        self._anthropic_tools: list[dict] = []
        self._db: Any = None  # Firestore client (optional)

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
            f"Agent ready — {len(self._anthropic_tools)} tools across "
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

        # Build the user content block(s) for Claude
        user_content: list[dict] = []

        if msg.msg_type == "audio":
            user_content = await self._handle_audio(msg)
        elif msg.msg_type == "image":
            user_content = await self._handle_image(msg)
        else:
            # Plain text
            user_content = [{"type": "text", "text": msg.text or ""}]

        if not user_content:
            await self._wa.send_text(
                msg.from_number,
                "⚠️ I couldn't process that message. Please try sending text, a product photo, or a voice note.",
            )
            return

        # Load conversation history
        history = await self._load_history(msg.from_number)

        # Run the agentic loop
        try:
            reply = await self._run_agent(user_content, history)
        except Exception as exc:
            logger.error(f"Agent error for {msg.from_number}: {exc}", exc_info=True)
            reply = "⚠️ I encountered an error while analysing your request. Please try again."

        # Persist conversation and reply
        await self._save_history(msg.from_number, history, user_content, reply)
        await self._wa.send_text(msg.from_number, reply)

    # ------------------------------------------------------------------
    # Media handling
    # ------------------------------------------------------------------

    async def _handle_audio(self, msg: IncomingMessage) -> list[dict]:
        """Download and transcribe audio; return text content block."""
        if not msg.media_id:
            return [{"type": "text", "text": "[audio message received but no media_id]"}]

        audio_bytes = await self._wa.get_and_download_media(msg.media_id)
        if not audio_bytes:
            return [{"type": "text", "text": "[could not download audio]"}]

        transcript = await transcribe_audio(audio_bytes, msg.mime_type or "audio/ogg")
        if transcript:
            return [{"type": "text", "text": f"[Voice message]: {transcript}"}]

        # Transcription failed — ask user to type
        return []

    async def _handle_image(self, msg: IncomingMessage) -> list[dict]:
        """Download image and build vision content block."""
        if not msg.media_id:
            return []

        image_bytes = await self._wa.get_and_download_media(msg.media_id)
        if not image_bytes:
            return []

        mime = msg.mime_type or detect_mime_from_bytes(image_bytes)
        image_block = encode_image_for_claude(image_bytes, mime)
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
        """Run the Claude agentic loop with MCP tool use.

        Uses prompt caching on the system prompt and adaptive thinking
        for complex multi-step analysis.
        """
        messages = history + [{"role": "user", "content": user_content}]

        for iteration in range(settings.max_tool_iterations):
            response = await self._anthropic.messages.create(
                model=settings.anthropic_model,
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        # Cache the system prompt across requests — it's large and stable
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=self._anthropic_tools if self._anthropic_tools else [],
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                return self._extract_text(response.content)

            if response.stop_reason == "tool_use":
                # Execute all tool calls (Claude may request multiple in parallel)
                tool_results = await self._execute_tools(response.content)
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason
            logger.warning(f"Unexpected stop_reason: {response.stop_reason}")
            return self._extract_text(response.content) or "Analysis complete."

        # Hit iteration limit — return whatever Claude said last
        return self._extract_text(response.content) or "Analysis complete (tool limit reached)."

    async def _execute_tools(self, content_blocks: list) -> list[dict]:
        """Execute all tool_use blocks and return tool_result messages."""
        results = []
        for block in content_blocks:
            if block.type != "tool_use":
                continue
            tool_name = block.name
            tool_input = block.input

            logger.info(f"Executing tool: {tool_name}({json.dumps(tool_input)[:200]})")

            result_text = await self._call_mcp_tool(tool_name, tool_input)
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_text,
            })
        return results

    async def _call_mcp_tool(self, tool_name: str, tool_input: dict) -> str:
        """Route a tool call to the appropriate MCP server session."""
        session = self._tool_registry.get(tool_name)
        if not session:
            logger.warning(f"Tool '{tool_name}' not found in registry")
            return json.dumps({"error": f"Tool '{tool_name}' not available"})

        try:
            result = await session.call_tool(tool_name, tool_input)
            # MCP returns a list of content items; concat text items
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
        """Query each MCP session for its tools and build the Anthropic tool list."""
        for name, session in self._mcp_sessions.items():
            try:
                tools_result = await session.list_tools()
                for tool in tools_result.tools:
                    self._tool_registry[tool.name] = session
                    self._anthropic_tools.append({
                        "name": tool.name,
                        "description": tool.description or f"Tool: {tool.name}",
                        "input_schema": tool.inputSchema or {
                            "type": "object",
                            "properties": {},
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
                    return messages[-max_turns * 2:]  # keep last N turn pairs
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
        # Build the new messages to append
        # Simplify media content blocks to text for storage
        stored_user_content: list[dict] | str
        text_parts = [b["text"] for b in user_content if b.get("type") == "text"]
        stored_user_content = " ".join(text_parts) if text_parts else "[media message]"

        new_messages = history + [
            {"role": "user", "content": stored_user_content},
            {"role": "assistant", "content": assistant_reply},
        ]
        # Trim to last N turns
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(content_blocks: list) -> str:
        """Join all text blocks from a response content list."""
        return "\n".join(
            block.text
            for block in content_blocks
            if hasattr(block, "type") and block.type == "text"
        ).strip()


def firestore_server_timestamp():
    """Return Firestore SERVER_TIMESTAMP sentinel if available, else now."""
    try:
        from google.cloud import firestore  # type: ignore[import]
        return firestore.SERVER_TIMESTAMP
    except Exception:
        return datetime.now(tz=timezone.utc)
