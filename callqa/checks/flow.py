"""Call-flow checks: did the agent cover every required step, in order, and not hang up early?

A step counts as covered on the first agent turn that contains one of its match phrases.
"""
from __future__ import annotations

from ..models import AgentSpec, Call, Finding
from ..text import contains_phrase


def first_hits(call: Call, spec: AgentSpec) -> dict[str, int]:
    hits: dict[str, int] = {}
    for i, turn in enumerate(call.turns):
        if turn.speaker != "agent":
            continue
        for step in spec.flow:
            if step.id not in hits and any(contains_phrase(turn.text, m) for m in step.match):
                hits[step.id] = i
    return hits


def _missing(spec: AgentSpec, hits: dict[str, int]) -> tuple[list[str], list[str]]:
    """Split missing required steps into skipped (a later step was covered) and not reached."""
    skipped, not_reached = [], []
    for idx, step in enumerate(spec.flow):
        if not step.required or step.id in hits:
            continue
        later = any(s.id in hits for s in spec.flow[idx + 1:])
        (skipped if later else not_reached).append(step.id)
    return skipped, not_reached


def check_coverage(call: Call, spec: AgentSpec, params: dict) -> tuple[list[Finding], dict]:
    hits = first_hits(call, spec)
    skipped, not_reached = _missing(spec, hits)
    findings = [Finding("coverage", "skipped_step", "fail", f"required step '{s}' was skipped") for s in skipped]
    required = [s for s in spec.flow if s.required]
    covered = sum(1 for s in required if s.id in hits)
    return findings, {"step_coverage": covered / len(required) if required else 1.0}


def check_order(call: Call, spec: AgentSpec, params: dict) -> tuple[list[Finding], dict]:
    hits = first_hits(call, spec)
    findings = []
    latest_step, latest_turn = None, -1
    for step in spec.flow:
        if step.id not in hits:
            continue
        if hits[step.id] < latest_turn:
            findings.append(Finding("order", "out_of_order", "fail",
                                    f"'{step.id}' was asked after '{latest_step}' in the flow but came first",
                                    turn=hits[step.id]))
        else:
            latest_step, latest_turn = step.id, hits[step.id]
    return findings, {}


def check_early_exit(call: Call, spec: AgentSpec, params: dict) -> tuple[list[Finding], dict]:
    hits = first_hits(call, spec)
    _, not_reached = _missing(spec, hits)
    if not not_reached:
        return [], {}
    if call.ended_by == "agent":
        return [Finding("early_exit", "early_exit", "fail",
                        f"agent ended the call before: {', '.join(not_reached)}")], {}
    who = "caller" if call.ended_by == "user" else "line (system)"
    return [Finding("early_exit", "ended_by_other", "info",
                    f"call ended by the {who} before: {', '.join(not_reached)}")], {}
