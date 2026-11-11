"""Call-flow checks: did the agent cover every required step, in order, and not hang up early?

A step counts as covered at the first place an agent turn asks it. "Place" is
(turn index, character position in that turn), so two steps asked in the same turn
still have an order.

How a step is recognised depends on the spec's step_matcher:
  - phrase: the turn contains one of the step's match phrases (exact, after normalising).
  - ml:     the trained classifier (callqa/ml.py) labels a sentence of the turn as that
            step with probability >= ml_threshold.
  - hybrid: either; whichever comes first in the call wins.
"""
from __future__ import annotations

from functools import lru_cache

from ..ml import clauses, load_model
from ..models import AgentSpec, Call, Finding
from ..text import normalize

Hit = tuple[int, int]  # (turn index, character position within the normalised turn)


def _position(text: str, phrases: list[str]) -> int | None:
    padded = f" {normalize(text)} "
    found = [padded.find(f" {normalize(p)} ") for p in phrases]
    found = [i for i in found if i >= 0]
    return min(found) if found else None


@lru_cache(maxsize=4096)
def _predict(agent_id: str, sentence: str) -> tuple[str, float]:
    model = load_model(agent_id)
    return model.predict(sentence) if model else ("other", 0.0)


def step_hits(call: Call, spec: AgentSpec) -> tuple[dict[str, Hit], dict[str, tuple[str, float]], str]:
    """Returns (first hit per step, how each was recognised, the matcher actually used)."""
    mode = spec.step_matcher
    if mode != "phrase" and load_model(spec.id) is None:
        mode = "phrase"  # no trained model for this agent: fall back to rules
    step_ids = {s.id for s in spec.flow}
    model = load_model(spec.id)
    threshold = spec.ml_threshold if spec.ml_threshold is not None else (model.meta.get("threshold", 0.4) if model else 1.0)
    hits: dict[str, Hit] = {}
    source: dict[str, tuple[str, float]] = {}
    for i, turn in enumerate(call.turns):
        if turn.speaker != "agent":
            continue
        found: list[tuple[int, int, str, str, float]] = []  # (pos, phrase-first tiebreak, step, how, p)
        if mode in ("phrase", "hybrid"):
            for step in spec.flow:
                pos = _position(turn.text, step.match)
                if pos is not None:
                    found.append((pos, 0, step.id, "phrase", 1.0))
        if mode in ("ml", "hybrid"):
            for offset, sentence in clauses(turn.text):
                label, p = _predict(spec.id, sentence)
                if label in step_ids and p >= threshold:
                    found.append((offset, 1, label, "ml", p))
        for pos, _, step_id, how, p in sorted(found):
            if step_id not in hits:
                hits[step_id] = (i, pos)
                source[step_id] = (how, p)
    return hits, source, mode


def first_hits(call: Call, spec: AgentSpec) -> dict[str, Hit]:
    return step_hits(call, spec)[0]


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
    hits, source, mode = step_hits(call, spec)
    skipped, _ = _missing(spec, hits)
    findings = [Finding("coverage", "skipped_step", "fail", f"required step '{s}' was skipped", step=s)
                for s in skipped]
    for step_id, (how, p) in source.items():
        if how == "ml":
            findings.append(Finding("coverage", "ml_step_match", "info",
                                    f"step '{step_id}' recognised by the trained model (p={p:.2f}); no rule phrase matched",
                                    turn=hits[step_id][0], step=step_id))
    if spec.step_matcher != "phrase" and mode == "phrase":
        findings.append(Finding("coverage", "ml_unavailable", "warn",
                                "no trained model for this agent; used phrase rules instead"))
    required = [s for s in spec.flow if s.required]
    covered = sum(1 for s in required if s.id in hits)
    return findings, {"step_coverage": covered / len(required) if required else 1.0,
                      "steps_found_by_model": float(sum(1 for how, _ in source.values() if how == "ml"))}


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
