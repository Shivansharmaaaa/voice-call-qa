"""Core data types: a call transcript, an agent spec, and what the checks find."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Speaker = Literal["agent", "user"]
EndedBy = Literal["agent", "user", "system"]
Severity = Literal["fail", "warn", "info"]


@dataclass
class Turn:
    speaker: Speaker
    text: str
    start: float  # seconds from call start
    end: float
    interrupted: bool = False  # this turn was cut off by the other side


@dataclass
class Call:
    id: str
    agent_id: str
    turns: list[Turn]
    ended_by: EndedBy = "agent"


@dataclass
class FlowStep:
    id: str
    match: list[str]  # phrases that mean the agent asked or said this step
    required: bool = True


@dataclass
class CheckConfig:
    enabled: bool = True
    weight: float = 1.0
    params: dict = field(default_factory=dict)


@dataclass
class AgentSpec:
    id: str
    name: str
    persona: Literal["mixed", "hindi_only", "english_only"]
    flow: list[FlowStep]
    compliance_lines: list[str] = field(default_factory=list)
    allowed_english: list[str] = field(default_factory=list)  # loanwords fine in a Hindi persona
    checks: dict[str, CheckConfig] = field(default_factory=dict)
    step_matcher: Literal["phrase", "ml", "hybrid"] = "phrase"  # how flow steps are recognised
    ml_threshold: float | None = None  # minimum model probability; None = the threshold chosen at training

    def check(self, name: str) -> CheckConfig:
        return self.checks.get(name, CheckConfig(enabled=False, weight=0))


@dataclass
class Finding:
    check: str  # which check produced it, e.g. "repeats"
    code: str  # what it found, e.g. "repeat", "skipped_step"
    severity: Severity
    detail: str
    turn: int | None = None  # index into call.turns, if it points at one turn
    step: str | None = None  # flow step id, for flow findings (so callers never parse `detail`)


@dataclass
class Report:
    call_id: str
    agent_id: str
    score: float  # 0-100, weighted share of enabled checks that passed
    findings: list[Finding]
    metrics: dict[str, float]
    checks_run: list[str]

    def failed_checks(self) -> set[str]:
        return {f.check for f in self.findings if f.severity == "fail"}
