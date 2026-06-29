from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """
    Base class for all Claude-callable tools.
    Subclass this and implement `name`, `description`, `input_schema`, and `execute`.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier used by Claude."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Plain-English description Claude uses to decide when to call this tool."""

    @property
    @abstractmethod
    def input_schema(self) -> dict:
        """JSON Schema describing the tool's input parameters."""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool and return a string result."""

    def to_claude_spec(self) -> dict:
        """Serialize to the format the Anthropic API expects."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
