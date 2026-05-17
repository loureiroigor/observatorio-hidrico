from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AdapterResult:
    source: str
    status: str
    updated_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class BaseAdapter(ABC):
    source_name: str

    @abstractmethod
    def fetch(self) -> AdapterResult:
        raise NotImplementedError

    def success(self, payload: dict[str, Any]) -> AdapterResult:
        return AdapterResult(
            source=self.source_name,
            status="ok",
            updated_at=datetime.now(),
            payload=payload,
            error=None,
        )

    def unavailable(self, error: str, payload: dict[str, Any] | None = None) -> AdapterResult:
        return AdapterResult(
            source=self.source_name,
            status="unavailable",
            updated_at=datetime.now(),
            payload=payload or {},
            error=error,
        )
