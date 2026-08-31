from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentError(Exception):
    message: str
    category: str = "internal"
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": type(self).__name__,
            "category": self.category,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


class ValidationError(AgentError):
    def __init__(self, message: str, *, field: str | None = None) -> None:
        details = {"field": field} if field else {}
        super().__init__(message=message, category="validation", details=details)


class OutputError(AgentError):
    def __init__(self, message: str, *, path: str) -> None:
        super().__init__(message=message, category="output", details={"path": path})


class S2APIError(AgentError):
    def __init__(
        self,
        message: str,
        *,
        category: str = "api",
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        details: dict[str, Any] = {}
        if status_code is not None:
            details["status_code"] = status_code
        if retry_after is not None:
            details["retry_after_seconds"] = retry_after
        super().__init__(message=message, category=category, details=details)
