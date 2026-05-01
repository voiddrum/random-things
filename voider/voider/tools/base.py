from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    content: str
    data: dict[str, Any] | None = None


class Tool(ABC):
    name: str
    description: str
    parameters: dict[str, Any]

    def permission_target(self, arguments: dict[str, Any]) -> str:
        """What scopes a stored permission decision. Default: blanket (`*`)."""
        return "*"

    def permission_summary(self, arguments: dict[str, Any]) -> str:
        return f"{self.name}({arguments})"

    @abstractmethod
    async def run(self, arguments: dict[str, Any]) -> ToolResult: ...

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
