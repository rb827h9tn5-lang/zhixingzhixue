from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func

from ..extensions import db
from ..models import AgentRun, AgentStep


class AgentTraceService:
    @staticmethod
    def start(
        *,
        user_id: int,
        task_type: str,
        input_data: dict[str, Any] | None = None,
    ) -> AgentRun:
        run = AgentRun(
            user_id=user_id,
            task_type=task_type,
            status="running",
            input_json=input_data or {},
        )
        db.session.add(run)
        db.session.flush()
        return run

    @staticmethod
    def record_step(
        run: AgentRun,
        *,
        agent_name: str,
        action: str,
        status: str = "passed",
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        evidence_count: int = 0,
        error_message: str = "",
    ) -> AgentStep:
        sequence = (
            db.session.query(func.max(AgentStep.sequence))
            .filter(AgentStep.run_id == run.id)
            .scalar()
            or 0
        ) + 1
        now = datetime.utcnow()
        step = AgentStep(
            run_id=run.id,
            sequence=sequence,
            agent_name=agent_name,
            action=action,
            status=status,
            input_json=input_data or {},
            output_json=output_data or {},
            evidence_count=max(0, int(evidence_count)),
            error_message=error_message,
            completed_at=now if status != "running" else None,
        )
        db.session.add(step)
        db.session.flush()
        return step

    @staticmethod
    def finish(
        run: AgentRun,
        *,
        output_data: dict[str, Any] | None = None,
        status: str = "passed",
    ) -> AgentRun:
        run.status = status
        run.output_json = output_data or {}
        run.completed_at = datetime.utcnow()
        db.session.flush()
        return run

    @staticmethod
    def fail(run: AgentRun, error: Exception | str) -> AgentRun:
        message = str(error)
        AgentTraceService.record_step(
            run,
            agent_name="System",
            action="执行流程失败",
            status="failed",
            error_message=message,
        )
        return AgentTraceService.finish(
            run,
            output_data={"error": message},
            status="failed",
        )

    @staticmethod
    def list_user_runs(
        user_id: int,
        *,
        task_type: str = "",
        limit: int = 20,
    ) -> list[AgentRun]:
        query = AgentRun.query.filter_by(user_id=user_id)
        if task_type:
            query = query.filter_by(task_type=task_type)
        return (
            query.order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            .limit(max(1, min(limit, 100)))
            .all()
        )
