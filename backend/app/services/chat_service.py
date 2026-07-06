import inspect
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.services.llm_client import LLMClient
from app.tools.registry import ToolRegistry
from app.models.conversation import Conversation, Message
from app.models.stack import Stack

_TITLE_PROMPT = """\
Summarize the topic of this conversation in a short title — 3 to 6 words, plain \
text, no quotes, no trailing punctuation, no markdown.

{conversation}
"""


class ChatService:
    """
    Manages assistant conversations: maintains history, dispatches tool calls,
    persists messages to the database.
    """

    def __init__(self, db: AsyncSession, account_id: str = ""):
        self.db = db
        self.llm = LLMClient()
        self.account_id = account_id
        self.registry = ToolRegistry(db=db, account_id=account_id)

    async def chat(
        self,
        user_message: str,
        account_id: str,
        conversation_id: str | None = None,
        stack_id: str | None = None,
    ) -> dict:
        conversation = await self._get_or_create_conversation(account_id, conversation_id, stack_id)
        await self._persist_message(conversation.id, "user", user_message)

        history = await self._build_history(conversation.id)
        chat_stack = await self._get_stack(account_id, conversation.stack_id)
        system_prompt = self._build_system_prompt(chat_stack)
        reply, tool_calls_log = await self._run(
            history, system_prompt, chat_stack.branch if chat_stack else None
        )

        await self._persist_message(conversation.id, "assistant", reply, tool_calls_log)
        await self.db.commit()

        return {
            "conversation_id": conversation.id,
            "reply": reply,
            "tool_calls": tool_calls_log or None,
        }

    async def _run(
        self, history: list[dict], system_prompt: str | None, chat_branch: str | None = None
    ) -> tuple[str, list[dict]]:
        """
        Send messages to the model. If it calls a tool, execute it and
        loop back until it returns a final text response.
        """
        tool_calls_log: list[dict] = []

        while True:
            result = await self.llm.chat(
                history,
                tools=self.registry.to_tool_specs(),
                system=system_prompt,
            )

            if result.finished:
                return result.text, tool_calls_log

            history.append(self.llm.assistant_message(result))

            tool_results: list[tuple[str, str]] = []
            for call in result.tool_calls:
                tool = self.registry.get(call.name)
                if tool is None:
                    output = f"Error: tool '{call.name}' not found"
                else:
                    kwargs = dict(call.input)
                    if "_chat_branch" in inspect.signature(tool.execute).parameters:
                        kwargs["_chat_branch"] = chat_branch
                    try:
                        output = await tool.execute(**kwargs)
                    except Exception as exc:
                        output = f"Error: tool '{call.name}' failed — {exc}"

                tool_calls_log.append({
                    "tool": call.name,
                    "input": call.input,
                    "result": output,
                })
                tool_results.append((call.id, output))

            history.append(self.llm.tool_results_message(tool_results))

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    async def _get_or_create_conversation(
        self, account_id: str, conversation_id: str | None, stack_id: str | None
    ) -> Conversation:
        if conversation_id:
            result = await self.db.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.account_id == account_id,
                )
            )
            conv = result.scalar_one_or_none()
            if conv:
                if stack_id is not None and stack_id != conv.stack_id:
                    conv.stack_id = stack_id
                return conv

        conv = Conversation(id=str(uuid.uuid4()), account_id=account_id, stack_id=stack_id)
        self.db.add(conv)
        await self.db.flush()
        return conv

    async def _get_stack(self, account_id: str, stack_id: str | None) -> Stack | None:
        if not stack_id:
            return None
        result = await self.db.execute(
            select(Stack).where(Stack.id == stack_id, Stack.account_id == account_id)
        )
        return result.scalar_one_or_none()

    def _build_system_prompt(self, stack: Stack | None) -> str | None:
        if not stack:
            return None

        lines = [
            "You are Canary, an AI assistant for data infrastructure and pipelines.",
            "",
            f'The user is currently focused on the "{stack.name}" stack (environment). Assume questions '
            'about "this environment", "this stack", or unqualified warehouse/infra questions refer to '
            "it unless they say otherwise:",
            f"- Deployment branch: {stack.branch}",
        ]
        if stack.sf_account_name:
            identity = (
                f"{stack.sf_organization_name}-{stack.sf_account_name}"
                if stack.sf_organization_name
                else stack.sf_account_name
            )
            lines.append(f"- Snowflake account: {identity}")
        if stack.sf_database:
            lines.append(f"- Snowflake database: {stack.sf_database}")
        if stack.sf_schema:
            lines.append(f"- Snowflake schema: {stack.sf_schema}")
        if stack.sf_warehouse:
            lines.append(f"- Snowflake warehouse: {stack.sf_warehouse}")
        if stack.sf_role:
            lines.append(f"- Snowflake role: {stack.sf_role}")
        lines.append(f"- Cloud: {stack.cloud_provider.upper()} ({stack.cloud_region or 'region not set'})")

        return "\n".join(lines)

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

    async def generate_title(self, conversation_id: str, account_id: str) -> Conversation | None:
        """Generate and save a short title summarizing the conversation so far.
        Returns None if the conversation doesn't exist; leaves it untouched
        (but still returns it) if there's nothing to summarize yet."""
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.id == conversation_id, Conversation.account_id == account_id)
            .options(selectinload(Conversation.messages))
        )
        conv = result.scalar_one_or_none()
        if not conv:
            return None

        history = await self._build_history(conversation_id)
        if not history:
            return conv

        transcript = "\n".join(f"{m['role']}: {m['content']}" for m in history)[:4000]
        title = await self.llm.complete(_TITLE_PROMPT.format(conversation=transcript), max_tokens=20)
        title = title.strip().strip('"').strip("'").rstrip(".")
        if title:
            conv.title = title[:255]
        return conv
