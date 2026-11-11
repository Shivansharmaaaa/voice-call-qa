"""Language-persona check.

The same behaviour can be right or wrong depending on the agent: switching between
Hindi and English is natural for a Hinglish recruiter, but breaks a strictly Hindi
persona. So the spec decides:
  - mixed:        any mix is fine; only reported as a metric.
  - hindi_only:   a turn fails if too much of it is English (spec.allowed_english excluded).
  - english_only: a turn fails if too much of it is Hindi.
"""
from __future__ import annotations

from ..models import AgentSpec, Call, Finding
from ..text import language_profile


def check_language(call: Call, spec: AgentSpec, params: dict) -> tuple[list[Finding], dict]:
    max_share = float(params.get("max_off_share", 0.34))
    min_tokens = int(params.get("min_off_tokens", 3))
    findings, shares = [], []
    for i, t in enumerate(call.turns):
        if t.speaker != "agent":
            continue
        prof = language_profile(t.text, spec.allowed_english)
        if not prof["total"]:
            continue
        shares.append(prof["hindi_share"])
        if spec.persona == "hindi_only":
            off, share = prof["english"], prof["english_share"]
        elif spec.persona == "english_only":
            off, share = prof["hindi"], prof["hindi_share"]
        else:
            continue
        if off >= min_tokens and share > max_share:
            findings.append(Finding("language", "off_persona", "fail",
                                    f"{share:.0%} of this turn is outside the {spec.persona} persona", turn=i))
    return findings, {"agent_hindi_share": sum(shares) / len(shares) if shares else 0.0}
