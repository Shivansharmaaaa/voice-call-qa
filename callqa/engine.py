"""Run an agent's enabled checks on one call and score it."""
from __future__ import annotations

from .checks import REGISTRY
from .models import AgentSpec, Call, Report


def score_call(call: Call, spec: AgentSpec) -> Report:
    if call.agent_id != spec.id:
        raise ValueError(f"call is for agent '{call.agent_id}', spec is '{spec.id}'")
    findings, metrics, ran = [], {}, []
    for name, fn in REGISTRY.items():
        cfg = spec.check(name)
        if not cfg.enabled:
            continue
        ran.append(name)
        f, m = fn(call, spec, cfg.params)
        findings.extend(f)
        metrics.update(m)
    failed = {f.check for f in findings if f.severity == "fail"}
    total = sum(spec.check(n).weight for n in ran)
    passed = sum(spec.check(n).weight for n in ran if n not in failed)
    score = round(100 * passed / total, 1) if total else 100.0
    return Report(call_id=call.id, agent_id=spec.id, score=score, findings=findings, metrics=metrics, checks_run=ran)
