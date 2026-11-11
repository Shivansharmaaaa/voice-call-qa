"""Call-flow checks: did the agent cover every required step, in order, and not hang up early?

A step counts as covered at the first place an agent turn contains one of its match
phrases. "Place" is (turn index, character position in that turn), so two steps asked
in the same turn still have an order.
"""
from __future__ import annotations

from ..models import AgentSpec, Call, Finding
from ..text import normalize

Hit = tuple[int, int]  # (turn index, character position within the normalised turn)


def _position(text: str, phrases: list[str]) -> int | None:
    padded = f" {normalize(text)} "
    found = [padded.find(f" {normalize(p)} ") for p in phrases]
    found = [i for i in found if i >= 0]
    return min(found) if found else None


def first_hits(call: Call, spec: AgentSpec) -> dict[str, Hit]:
    hits: dict[str, Hit] = {}
    for i, turn in enumerate(call.turns):
        if turn.speaker != "agent":
            continue
        for step in spec.flow:
            if step.id in hits:
                continue
            pos = _position(turn.text, step.match)
            if pos is not None:
                hits[step.id] = (i, pos)
    return hits


def _missing(spec: AgentSpec, hits: dict[str, Hit]) -> tuple[list[str], list[str]]:
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
    skipped, _ = _missing(spec, hits)
    findings = [Finding("coverage", "skipped_step", "fail", f"required step '{s}' was skipped", step=s)
                for s in skipped]
    required = [s for s in spec.flow if s.required]
    covered = sum(1 for s in required if s.id in hits)
    return findings, {"step_coverage": covered / len(required) if required else 1.0}


def check_order(call: Call, spec: AgentSpec, params: dict) -> tuple[list[Finding], dict]:
    hits = first_hits(call, spec)
    findings = []
    latest_step: str | None = None
    latest: Hit = (-1, -1)
    for step in spec.flow:
        if step.id not in hits:
            continue
        if hits[step.id] < latest:
            where = "earlier in the same turn" if hits[step.id][0] == latest[0] else "first"
            findings.append(Finding("order", "out_of_order", "fail",
                                    f"'{step.id}' comes after '{latest_step}' in the flow but was asked {where}",
                                    turn=hits[step.id][0], step=step.id))
        else:
            latest_step, latest = step.id, hits[step.id]
    return findings, {}


def check_early_exit(call: Call, spec: AgentSpec, params: dict) -> tuple[list[Finding], dict]:
    hits = first_hits(call, spec)
    _, not_reached = _missing(spec, hits)
    if not not_reached:
        return [], {}
    if call.ended_by == "agent":
        return [Finding("early_exit", "early_exit", "fail",
                        f"agent ended the call before: {', '.join(not_reached)}", step=not_reached[0])], {}
    who = "caller" if call.ended_by == "user" else "line (system)"
    return [Finding("early_exit", "ended_by_other", "info",
                    f"call ended by the {who} before: {', '.join(not_reached)}", step=not_reached[0])], {}
