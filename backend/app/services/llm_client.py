"""Provider-agnostic LLM client.

Every call site in this codebase goes through `LLMClient` rather than importing
a model provider's SDK directly. `LLMClient` picks a concrete provider (default:
Anthropic's Claude, via the `llm_provider` setting or the `provider` constructor
arg) but no caller depends on which one — they only see `complete()`/`chat()`
and the generic `ChatResult`/`ToolCall` types below. Adding a new provider means
implementing `_LLMProvider` and registering it in `_PROVIDERS`; nothing outside
this file needs to change.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings

settings = get_settings()


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class ChatResult:
    text: str
    tool_calls: list[ToolCall]
    finished: bool  # True => final answer; False => tool_calls must be executed and fed back
    _raw_content: Any = field(default=None, repr=False)  # provider-native content, for history replay only


class _LLMProvider(ABC):
    """Interface every concrete model provider backend implements."""

    @abstractmethod
    async def complete(self, prompt: str, *, max_tokens: int | None) -> str:
        """Single-turn text completion: send a prompt, get text back."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None,
        system: str | None,
        max_tokens: int | None,
    ) -> ChatResult:
        """Multi-turn chat, optionally with tool calling."""

    @abstractmethod
    def assistant_message(self, result: ChatResult) -> dict:
        """Build the history entry for the assistant's turn."""

    @abstractmethod
    def tool_results_message(self, results: list[tuple[str, str]]) -> dict:
        """Build the history entry for tool results — (tool_call_id, result_text) pairs."""


class _AnthropicProvider(_LLMProvider):
    def __init__(self, api_key: str | None, model: str | None, max_tokens: int | None):
        import anthropic

        self._sdk = anthropic
        self._client = anthropic.AsyncAnthropic(api_key=api_key or settings.anthropic_api_key)
        self._model = model or settings.anthropic_model
        self._default_max_tokens = max_tokens or settings.anthropic_max_tokens

    async def complete(self, prompt: str, *, max_tokens: int | None) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens or self._default_max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return next((b.text for b in response.content if hasattr(b, "text")), "").strip()

    async def chat(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None,
        system: str | None,
        max_tokens: int | None,
    ) -> ChatResult:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens or self._default_max_tokens,
            system=system or self._sdk.NOT_GIVEN,
            tools=tools or self._sdk.NOT_GIVEN,
            messages=messages,
        )

        text = next((b.text for b in response.content if hasattr(b, "text")), "")
        tool_calls = [
            ToolCall(id=b.id, name=b.name, input=b.input)
            for b in response.content
            if b.type == "tool_use"
        ]
        return ChatResult(
            text=text,
            tool_calls=tool_calls,
            finished=response.stop_reason != "tool_use",
            _raw_content=response.content,
        )

    def assistant_message(self, result: ChatResult) -> dict:
        return {"role": "assistant", "content": result._raw_content}

    def tool_results_message(self, results: list[tuple[str, str]]) -> dict:
        return {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": call_id, "content": text}
                for call_id, text in results
            ],
        }


_PROVIDERS: dict[str, type[_LLMProvider]] = {
    "anthropic": _AnthropicProvider,
}


class LLMClient:
    """Thin wrapper over the configured LLM provider.

    `complete()` is for one-shot prompt-in/text-out calls. `chat()` supports
    multi-turn conversations with optional tool calling; `assistant_message()`
    and `tool_results_message()` build the history entries needed to continue
    a `chat()` conversation after executing tool calls, without callers ever
    touching provider-native message shapes.

    Pass `provider=` to use a specific backend for one call site; otherwise it
    falls back to the `LLM_PROVIDER` setting (default: "anthropic").
    """

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ):
        provider_name = provider or settings.llm_provider
        provider_cls = _PROVIDERS.get(provider_name)
        if provider_cls is None:
            raise ValueError(
                f"Unknown LLM provider '{provider_name}'. Available: {', '.join(_PROVIDERS)}"
            )
        self._provider = provider_cls(api_key=api_key, model=model, max_tokens=max_tokens)

    async def complete(self, prompt: str, *, max_tokens: int | None = None) -> str:
        return await self._provider.complete(prompt, max_tokens=max_tokens)

    async def chat(
        self,
        messages: list[dict],
        *,
        tools: list[dict] | None = None,
        system: str | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        return await self._provider.chat(messages, tools=tools, system=system, max_tokens=max_tokens)

    def assistant_message(self, result: ChatResult) -> dict:
        return self._provider.assistant_message(result)

    def tool_results_message(self, results: list[tuple[str, str]]) -> dict:
        return self._provider.tool_results_message(results)
