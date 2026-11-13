import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.services.llm_client import LLMClient
from app.tools.registry import ToolRegistry
from app.models.conversation import Conversation, Message
from app.models.stack import Stack
from app.models.project import Project
from app.models.data_classification import DataClassification

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
        classifications = await self._get_data_classifications(account_id)
        default_retention_policy = await self._get_default_retention_policy(account_id)
        system_prompt = self._build_system_prompt(chat_stack, classifications, default_retention_policy)
        reply, tool_calls_log = await self._run(history, system_prompt)

        await self._persist_message(conversation.id, "assistant", reply, tool_calls_log)
        await self.db.commit()

        return {
            "conversation_id": conversation.id,
            "reply": reply,
            "tool_calls": tool_calls_log or None,
        }

    async def _run(self, history: list[dict], system_prompt: str | None) -> tuple[str, list[dict]]:
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
                    try:
                        output = await tool.execute(**call.input)
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

    async def _get_data_classifications(self, account_id: str) -> list[DataClassification]:
        result = await self.db.execute(
            select(DataClassification)
            .where(DataClassification.account_id == account_id)
            .order_by(DataClassification.sort_order)
        )
        return list(result.scalars().all())

    async def _get_default_retention_policy(self, account_id: str) -> str | None:
        result = await self.db.execute(select(Project).where(Project.account_id == account_id))
        project = result.scalar_one_or_none()
        return project.default_retention_policy if project else None

    def _build_system_prompt(
        self,
        stack: Stack | None,
        classifications: list[DataClassification],
        default_retention_policy: str | None,
    ) -> str | None:
        lines = ["You are Canary, an AI assistant for data infrastructure and pipelines."]

        if classifications:
            lines.append("")
            lines.append(
                "This account's configured data classifications (used by create_landing_zone and "
                "draft_landing_zone_tables) — each table/landing zone should get whichever one actually "
                "fits, judged against these descriptions:"
            )
            for c in classifications:
                default_marker = " (account default)" if c.is_default else ""
                desc = f" — {c.description}" if c.description else ""
                lines.append(f"- {c.name}{default_marker}{desc}")
            lines.append(
                "If the user doesn't specify a classification for a table, use the account default. But "
                "if that table's inferred columns look more sensitive than the default's own description "
                "covers (e.g. an email/SSN/payment column under a default whose description doesn't "
                "mention PII), don't silently apply the default — flag it and ask which classification "
                "actually fits before proceeding."
            )

        if default_retention_policy:
            lines.append("")
            lines.append(
                f"This account's default retention_policy for create_landing_zone is "
                f"'{default_retention_policy}' — use it whenever the user doesn't specify one; only ask "
                "if there's a specific reason this landing zone might need something different."
            )

        if stack:
            lines.append("")
            lines.append(
                f'The user is currently focused on the "{stack.name}" stack (environment). Assume '
                'questions about "this environment", "this stack", or unqualified warehouse/infra '
                "questions refer to it unless they say otherwise:"
            )
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

        if len(lines) == 1:
            return None
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
