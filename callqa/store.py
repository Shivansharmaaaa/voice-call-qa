"""Optional persistence for self-hosting: scored calls and their findings in any SQLAlchemy database.

The hosted demo runs on serverless functions with no lasting disk, so it does not use this.
Set CALLQA_DB (e.g. sqlite:///callqa.db or a Postgres URL) to turn it on.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CallRow(Base):
    __tablename__ = "calls"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(80), index=True)
    score: Mapped[float] = mapped_column(Float, index=True)
    payload: Mapped[dict] = mapped_column(JSON)  # the full scored call, as returned by the API
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    findings: Mapped[list[FindingRow]] = relationship(back_populates="call", cascade="all, delete-orphan")


class FindingRow(Base):
    """Findings are also stored as rows so they can be queried with SQL (e.g. skipped steps per week)."""
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
    def __init__(self, url: str):
        self.engine = create_engine(url)
        Base.metadata.create_all(self.engine)

    def put(self, scored: dict) -> None:
        with Session(self.engine) as s:
            old = s.get(CallRow, scored["id"])
            if old:
                s.delete(old)
                s.flush()
            row = CallRow(id=scored["id"], agent_id=scored["agent_id"], score=scored["score"], payload=scored,
                          created_at=datetime.now(timezone.utc))
            row.findings = [FindingRow(check=f["check"], code=f["code"], severity=f["severity"],
                                       detail=f["detail"], turn=f["turn"]) for f in scored["findings"]]
            s.add(row)
            s.commit()

    def get(self, call_id: str) -> dict | None:
        with Session(self.engine) as s:
            row = s.get(CallRow, call_id)
            return dict(row.payload) if row else None

    def all(self, agent_id: str | None = None) -> list[dict]:
        with Session(self.engine) as s:
            q = select(CallRow).order_by(CallRow.created_at)
            if agent_id:
                q = q.where(CallRow.agent_id == agent_id)
            return [dict(r.payload) for r in s.scalars(q)]
