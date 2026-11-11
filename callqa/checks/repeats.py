"""Repeat detection, with the cases where repeating is fine.

A repeat is an agent turn that is near-identical to an earlier agent turn. It does
NOT count when:
  - the earlier turn was cut off by the caller and the agent is restarting it,
  - the caller just asked the agent to repeat ("phir se boliye", "sorry?"),
  - the repeated text is a compliance line the spec allows to be said again.
Short acknowledgements ("haan ji", "theek hai") are ignored entirely.
"""
from __future__ import annotations

from ..models import AgentSpec, Call, Finding
from ..text import asks_for_repeat, containment, contains_phrase, similarity, tokens


def _is_compliance(text: str, spec: AgentSpec) -> bool:
    return any(contains_phrase(text, line) or similarity(text, line) >= 0.85 for line in spec.compliance_lines)


def check_repeats(call: Call, spec: AgentSpec, params: dict) -> tuple[list[Finding], dict]:
    threshold = float(params.get("similarity", 0.85))
    min_tokens = int(params.get("min_tokens", 4))
    findings: list[Finding] = []
    counted = 0
    eligible = 0
    earlier: list[int] = []  # indices of earlier agent turns
    for i, turn in enumerate(call.turns):
        if turn.speaker != "agent":
            continue
        if len(tokens(turn.text)) < min_tokens:
            continue
        eligible += 1
        prev_user = next((call.turns[k] for k in range(i - 1, -1, -1) if call.turns[k].speaker == "user"), None)
        prev_agent = earlier[-1] if earlier else None
        match = None
        for j in earlier:
            other = call.turns[j]
            sim = similarity(turn.text, other.text)
            if other.interrupted and j == prev_agent:
                sim = max(sim, containment(other.text, turn.text))
            if sim >= threshold:
                match = j
                break
        if match is not None:
            other = call.turns[match]
            if other.interrupted and match == prev_agent:
                reason = "restart after the caller interrupted"
            elif prev_user is not None and asks_for_repeat(prev_user.text) and (call.turns[i - 1].speaker == "user"):
                reason = "caller asked for a repeat"
            elif _is_compliance(turn.text, spec):
                reason = "allowed compliance line"
            else:
                reason = None
            if reason:
                findings.append(Finding("repeats", "repeat_exempt", "info",
                                        f"repeat of turn {match} not counted: {reason}", turn=i))
            else:
                counted += 1
                findings.append(Finding("repeats", "repeat", "fail",
                                        f"agent repeated turn {match} without a reason", turn=i))
        earlier.append(i)
    return findings, {"repeat_rate": counted / eligible if eligible else 0.0}
