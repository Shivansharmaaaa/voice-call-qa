"""Turn scored calls into API-friendly dicts and per-agent rollups. Shared by the in-memory demo and the SQL store."""
from __future__ import annotations

from dataclasses import asdict

from .models import AgentSpec, Call, Report


def report_dict(call: Call, spec: AgentSpec, report: Report, extra: dict | None = None) -> dict:
    failed = report.failed_checks()
    breakdown = [{"check": n, "weight": spec.check(n).weight, "passed": n not in failed,
                  "findings": sum(1 for f in report.findings if f.check == n and f.severity == "fail")}
                 for n in report.checks_run]
    out = {"id": call.id, "agent_id": call.agent_id, "ended_by": call.ended_by, "score": report.score,
           "turns": [asdict(t) for t in call.turns], "findings": [asdict(f) for f in report.findings],
           "metrics": {k: round(v, 3) for k, v in report.metrics.items()}, "breakdown": breakdown,
           "failed_checks": sorted(failed)}
    out.update(extra or {})
    return out


def summarize(spec: AgentSpec, calls: list[dict]) -> dict:
    """Per-agent rollup. Only the checks this agent runs appear, so each agent gets its own dashboard."""
    enabled = [n for n in spec.checks if spec.check(n).enabled]
    n = len(calls)
    fail_rate = {c: round(sum(1 for x in calls if c in x["failed_checks"]) / n, 3) if n else 0.0 for c in enabled}
    skipped: dict[str, int] = {}
    for x in calls:
        for f in x["findings"]:
            if f["code"] == "skipped_step":
                step = f["detail"].split("'")[1]
                skipped[step] = skipped.get(step, 0) + 1
    keys = sorted({k for x in calls for k in x["metrics"]})
    avg = {k: round(sum(x["metrics"].get(k, 0) for x in calls) / n, 3) for k in keys} if n else {}
    hist = [0] * 10
    for x in calls:
        hist[min(int(x["score"] // 10), 9)] += 1
    worst = sorted(calls, key=lambda x: x["score"])[:5]
    return {"agent_id": spec.id, "name": spec.name, "persona": spec.persona, "calls": n,
            "mean_score": round(sum(x["score"] for x in calls) / n, 1) if n else None,
            "clean_calls": sum(1 for x in calls if not x["failed_checks"]),
            "fail_rate_by_check": fail_rate, "weights": {c: spec.check(c).weight for c in enabled},
            "avg_metrics": avg, "most_skipped_steps": dict(sorted(skipped.items(), key=lambda kv: -kv[1])),
            "score_histogram": hist, "worst_calls": [{"id": x["id"], "score": x["score"]} for x in worst]}
