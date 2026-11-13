from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """
    Base class for all model-callable tools.
    Subclass this and implement `name`, `description`, `input_schema`, and `execute`.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier used by the model."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Plain-English description the model uses to decide when to call this tool."""

    @property
    @abstractmethod
    def input_schema(self) -> dict:
        """JSON Schema describing the tool's input parameters."""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool and return a string result."""

    def to_tool_spec(self) -> dict:
        """Serialize to the tool-spec format the configured LLM provider expects."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
