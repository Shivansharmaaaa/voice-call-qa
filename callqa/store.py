"""Persistence: agent specs, scored calls and their findings (SQLite by default, any SQLAlchemy URL works)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from .models import AgentSpec, Report
from .spec import load_spec_text


class Base(DeclarativeBase):
    pass


class AgentRow(Base):
    __tablename__ = "agents"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    spec_yaml: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CallRow(Base):
    __tablename__ = "calls"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    ended_by: Mapped[str] = mapped_column(String(10))
    turns: Mapped[list] = mapped_column(JSON)
    metrics: Mapped[dict] = mapped_column(JSON)
    checks_run: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    findings: Mapped[list[FindingRow]] = relationship(back_populates="call", cascade="all, delete-orphan")


class FindingRow(Base):
    __tablename__ = "findings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_id: Mapped[str] = mapped_column(ForeignKey("calls.id"), index=True)
    check: Mapped[str] = mapped_column(String(40), index=True)
    code: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))
    detail: Mapped[str] = mapped_column(Text)
    turn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    call: Mapped[CallRow] = relationship(back_populates="findings")


class Store:
    def __init__(self, url: str = "sqlite:///callqa.db"):
        self.engine = create_engine(url)
        Base.metadata.create_all(self.engine)

    def put_agent(self, yaml_text: str) -> AgentSpec:
        spec = load_spec_text(yaml_text)
        with Session(self.engine) as s:
            s.merge(AgentRow(id=spec.id, name=spec.name, spec_yaml=yaml_text, updated_at=datetime.now(timezone.utc)))
            s.commit()
        return spec

    def get_agent(self, agent_id: str) -> AgentSpec | None:
        with Session(self.engine) as s:
            row = s.get(AgentRow, agent_id)
            return load_spec_text(row.spec_yaml) if row else None

    def list_agents(self) -> list[AgentSpec]:
        with Session(self.engine) as s:
            return [load_spec_text(r.spec_yaml) for r in s.scalars(select(AgentRow).order_by(AgentRow.id))]

    def put_report(self, report: Report, turns: list[dict], ended_by: str) -> None:
        with Session(self.engine) as s:
            existing = s.get(CallRow, report.call_id)
            if existing:
                s.delete(existing)
                s.flush()
            row = CallRow(id=report.call_id, agent_id=report.agent_id, score=report.score, ended_by=ended_by,
                          turns=turns, metrics=report.metrics, checks_run=report.checks_run,
                          created_at=datetime.now(timezone.utc))
            row.findings = [FindingRow(check=f.check, code=f.code, severity=f.severity, detail=f.detail, turn=f.turn)
                            for f in report.findings]
            s.add(row)
            s.commit()

    def get_call(self, call_id: str) -> dict | None:
        with Session(self.engine) as s:
            row = s.get(CallRow, call_id)
            if not row:
                return None
            return {"id": row.id, "agent_id": row.agent_id, "score": row.score, "ended_by": row.ended_by,
                    "metrics": row.metrics, "checks_run": row.checks_run, "turns": row.turns,
                    "findings": [{"check": f.check, "code": f.code, "severity": f.severity, "detail": f.detail,
                                  "turn": f.turn} for f in row.findings]}

    def summary(self, agent_id: str) -> dict:
        """Per-agent rollup. Only the checks this agent runs appear, so each agent gets its own dashboard."""
        spec = self.get_agent(agent_id)
        if spec is None:
            raise KeyError(agent_id)
        with Session(self.engine) as s:
            calls = list(s.scalars(select(CallRow).where(CallRow.agent_id == agent_id)))
            enabled = [n for n in spec.checks if spec.check(n).enabled]
            fail_rate = {}
            for name in enabled:
                failed = sum(1 for c in calls if any(f.check == name and f.severity == "fail" for f in c.findings))
                fail_rate[name] = round(failed / len(calls), 3) if calls else 0.0
            skipped: dict[str, int] = {}
            for c in calls:
                for f in c.findings:
                    if f.code in ("skipped_step",):
                        step = f.detail.split("'")[1]
                        skipped[step] = skipped.get(step, 0) + 1
            metric_keys = sorted({k for c in calls for k in c.metrics})
            avg = {k: round(sum(c.metrics.get(k, 0) for c in calls) / len(calls), 3) for k in metric_keys} if calls else {}
            worst = sorted(calls, key=lambda c: c.score)[:5]
        return {"agent_id": agent_id, "name": spec.name, "persona": spec.persona, "calls": len(calls),
                "mean_score": round(sum(c.score for c in calls) / len(calls), 1) if calls else None,
                "fail_rate_by_check": fail_rate, "avg_metrics": avg,
                "most_skipped_steps": dict(sorted(skipped.items(), key=lambda kv: -kv[1])),
                "worst_calls": [{"id": c.id, "score": c.score} for c in worst]}


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
