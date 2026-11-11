"""Load and validate agent specs from YAML.

The spec is where "what does good look like for this agent" is written down:
which steps the call must cover, which persona it speaks in, which lines it is
allowed to repeat, and which checks count (with their weights and thresholds).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .models import AgentSpec, CheckConfig, FlowStep

KNOWN_CHECKS = {"coverage", "order", "early_exit", "one_question", "repeats", "language", "latency"}
PERSONAS = {"mixed", "hindi_only", "english_only"}
MATCHERS = {"phrase", "ml", "hybrid"}


class SpecError(ValueError):
    pass


def parse_spec(data: dict) -> AgentSpec:
    for key in ("id", "name", "persona", "flow"):
        if key not in data:
            raise SpecError(f"spec is missing '{key}'")
    if data["persona"] not in PERSONAS:
        raise SpecError(f"persona must be one of {sorted(PERSONAS)}")
    flow = []
    seen = set()
    for step in data["flow"]:
        if "id" not in step or not step.get("match"):
            raise SpecError("each flow step needs an id and at least one match phrase")
        if step["id"] in seen:
            raise SpecError(f"duplicate flow step id '{step['id']}'")
        seen.add(step["id"])
        flow.append(FlowStep(id=step["id"], match=[m.lower() for m in step["match"]],
                             required=step.get("required", True)))
    checks = {}
    for name, cfg in (data.get("checks") or {}).items():
        if name not in KNOWN_CHECKS:
            raise SpecError(f"unknown check '{name}'")
        cfg = dict(cfg or {})
        checks[name] = CheckConfig(enabled=cfg.pop("enabled", True), weight=float(cfg.pop("weight", 1.0)),
                                   params=cfg)
    matcher = data.get("step_matcher", "phrase")
    if matcher not in MATCHERS:
        raise SpecError(f"step_matcher must be one of {sorted(MATCHERS)}")
    threshold = data.get("ml_threshold")
    if threshold is not None:
        threshold = float(threshold)
        if not 0 < threshold < 1:
            raise SpecError("ml_threshold must be between 0 and 1")
    return AgentSpec(
        id=data["id"], name=data["name"], persona=data["persona"], flow=flow,
        step_matcher=matcher, ml_threshold=threshold,
        compliance_lines=[c.lower() for c in data.get("compliance_lines", [])],
        allowed_english=[w.lower() for w in data.get("allowed_english", [])],
        checks=checks,
    )


def load_spec_text(text: str) -> AgentSpec:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise SpecError(f"invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise SpecError("spec must be a YAML mapping")
    return parse_spec(data)


def load_spec_file(path: str | Path) -> AgentSpec:
    return load_spec_text(Path(path).read_text(encoding="utf-8"))


def load_dir(path: str | Path) -> dict[str, AgentSpec]:
    return {s.id: s for s in (load_spec_file(p) for p in sorted(Path(path).glob("*.yaml")))}
