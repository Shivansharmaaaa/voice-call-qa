"""Turn-level checks: one question per turn, and response latency."""
from __future__ import annotations

import re

from ..models import AgentSpec, Call, Finding
from ..text import count_questions

PUNCT = re.compile(r"[?？.!,।]")


def check_one_question(call: Call, spec: AgentSpec, params: dict) -> tuple[list[Finding], dict]:
    limit = int(params.get("max_questions", 1))
    agent_turns = [(i, t) for i, t in enumerate(call.turns) if t.speaker == "agent"]
    findings = []
    for i, t in agent_turns:
        n = count_questions(t.text)
        if n > limit:
            findings.append(Finding("one_question", "multiple_questions", "fail",
                                    f"{n} questions in one turn (limit {limit})", turn=i))
    punctuated = sum(1 for _, t in agent_turns if PUNCT.search(t.text))
    if len(agent_turns) >= 3 and punctuated == 0:
        # Without punctuation this check cannot see questions at all, so say so instead of passing silently.
        findings.append(Finding("one_question", "no_punctuation", "warn",
                                "transcript has no punctuation; question counting is unreliable"))
    return findings, {"punctuated_agent_turns": punctuated / len(agent_turns) if agent_turns else 0.0}


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def check_latency(call: Call, spec: AgentSpec, params: dict) -> tuple[list[Finding], dict]:
    max_gap = float(params.get("max_gap_s", 2.0))
    gaps, findings = [], []
    for i in range(1, len(call.turns)):
        prev, cur = call.turns[i - 1], call.turns[i]
        if prev.speaker == "user" and cur.speaker == "agent":
            gap = max(0.0, cur.start - prev.end)
            gaps.append(gap)
            if gap > max_gap:
                findings.append(Finding("latency", "slow_response", "fail",
                                        f"agent took {gap:.1f}s to respond (limit {max_gap:.1f}s)", turn=i))
    return findings, {"gap_p50_s": round(_percentile(gaps, 0.5), 2), "gap_p95_s": round(_percentile(gaps, 0.95), 2)}
