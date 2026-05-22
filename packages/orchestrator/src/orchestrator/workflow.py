from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class WorkflowState:
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ticker: str = ""
    status: WorkflowStatus = WorkflowStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    error: str | None = None
    result: Any | None = None
    steps_completed: list[str] = field(default_factory=list)

    def mark_step(self, step: str) -> None:
        self.steps_completed.append(step)
        logger.debug("Workflow step completed", extra={"step": step, "workflow_id": self.workflow_id})

    def complete(self, result: Any) -> None:
        self.status = WorkflowStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.result = result

    def fail(self, error: str) -> None:
        self.status = WorkflowStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error = error

    @property
    def duration_seconds(self) -> float | None:
        if self.completed_at:
            return (self.completed_at - self.created_at).total_seconds()
        return None
