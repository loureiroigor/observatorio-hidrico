from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict


@dataclass
class AdapterResult:
    source: str
    status: str
    updated_at: datetime
    payload: Dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class BaseAdapter(ABC):
    source_name: str

    @abstractmethod
    def fetch(self) -> AdapterResult:
        raise NotImplementedError

    def unavailable(self, error: str, payload: Dict[str, Any] | None = None) -> AdapterResult:
        return AdapterResult(
            source=self.source_name,
            status="unavailable",
            updated_at=datetime.now(),
            payload=payload or {},
            error=error,
        )
