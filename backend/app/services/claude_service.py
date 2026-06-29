import uuid
import anthropic
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.tools.registry import ToolRegistry
from app.models.conversation import Conversation, Message

settings = get_settings()


class ClaudeService:
    """
    Manages Claude conversations: maintains history, dispatches tool calls,
    persists messages to the database.
    """

    def __init__(self, db: AsyncSession, account_id: str = ""):
        self.db = db
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.account_id = account_id
        self.registry = ToolRegistry(db=db, account_id=account_id)

    async def chat(self, user_message: str, account_id: str, conversation_id: str | None = None) -> dict:
        conversation = await self._get_or_create_conversation(account_id, conversation_id)
        await self._persist_message(conversation.id, "user", user_message)

        history = await self._build_history(conversation.id)
        reply, tool_calls_log = await self._run(history)

        await self._persist_message(conversation.id, "assistant", reply, tool_calls_log)
        await self.db.commit()

        return {
            "conversation_id": conversation.id,
            "reply": reply,
            "tool_calls": tool_calls_log or None,
        }

    async def _run(self, history: list[dict]) -> tuple[str, list[dict]]:
        """
        Send messages to Claude. If Claude calls a tool, execute it and
        loop back until Claude returns a text response.
        """
        tool_calls_log: list[dict] = []

        while True:
            response = await self.client.messages.create(
                model=settings.anthropic_model,
                max_tokens=settings.anthropic_max_tokens,
                tools=self.registry.to_claude_specs(),
                messages=history,
            )

            if response.stop_reason == "end_turn":
                text = next(
                    (b.text for b in response.content if hasattr(b, "text")), ""
                )
                return text, tool_calls_log

            if response.stop_reason == "tool_use":
                # Append Claude's response (including tool_use blocks) to history
                history.append({"role": "assistant", "content": response.content})

                # Execute each tool call and collect results
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue

                    tool = self.registry.get(block.name)
                    if tool is None:
                        result = f"Error: tool '{block.name}' not found"
                    else:
                        result = await tool.execute(**block.input)

                    tool_calls_log.append({
                        "tool": block.name,
                        "input": block.input,
                        "result": result,
                    })
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

                history.append({"role": "user", "content": tool_results})
                continue

            # Fallback — unexpected stop reason
            return f"Unexpected stop reason: {response.stop_reason}", tool_calls_log

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    async def _get_or_create_conversation(self, account_id: str, conversation_id: str | None) -> Conversation:
        if conversation_id:
            result = await self.db.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.account_id == account_id,
                )
            )
            conv = result.scalar_one_or_none()
            if conv:
                return conv

        conv = Conversation(id=str(uuid.uuid4()), account_id=account_id)
        self.db.add(conv)
        await self.db.flush()
        return conv

    async def _build_history(self, conversation_id: str) -> list[dict]:
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        messages = result.scalars().all()
        return [{"role": m.role, "content": m.content} for m in messages]

    async def _persist_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        tool_calls: list[dict] | None = None,
    ) -> None:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
        )
        self.db.add(msg)
