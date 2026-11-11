"""HTTP API (everything under /api) plus the built web app at /.

Local:  uvicorn --factory callqa.api:create_app
Hosted: api/index.py builds the same app as a Vercel serverless function.

Nothing is built at import time: create_app() generates and scores the demo data.

The 120 synthetic demo calls are generated and scored in memory at start-up, so the
app works with no database. Set CALLQA_DB to also persist calls posted to /api/calls.
"""
from __future__ import annotations

import html
import os
import random
import time
from collections import defaultdict, deque
from dataclasses import asdict
from functools import cached_property
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import score_call
from .evaluate import evaluate
from .models import AgentSpec, Call, Turn
from .spec import SpecError, load_spec_text
from .store import Store
from .summary import report_dict, summarize
from .synth import FAULTS, SCRIPTS, generate, make_call

ROOT = Path(__file__).resolve().parent.parent

FAULT_INFO = {
    "skip": ("Skip a question", "The agent jumps over a required screening step.", True),
    "swap": ("Swap two questions", "Two steps are asked in the wrong order.", True),
    "early_exit": ("Agent hangs up early", "The agent ends the call before the required steps.", True),
    "user_hangup": ("Caller hangs up", "The caller ends the call early. Must NOT count against the agent.", False),
    "double": ("Two questions at once", "Two questions in one breath.", True),
    "repeat": ("Unprompted repeat", "The agent asks the same thing again for no reason.", True),
    "restart": ("Interrupted, then restarts", "The caller cuts in and the agent restarts the line. Must NOT count.", False),
    "asked_repeat": ("Caller asks for a repeat", "\"Phir se boliye?\" then the agent repeats. Must NOT count.", False),
    "english": ("Slips into English", "An English turn from a Hindi-only agent (Hindi agent only).", True),
    "compliance_repeat": ("Repeats the recording notice", "A compliance line said again. Must NOT count.", False),
    "slow": ("Slow response", "A 3-4.5 s silence before the agent answers.", True),
    "no_punctuation": ("STT drops punctuation", "Simulates unpunctuated transcripts: a known blind spot.", False),
}


class TurnIn(BaseModel):
    speaker: str = Field(pattern="^(agent|user)$")
    text: str = Field(max_length=1000)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    interrupted: bool = False


class CallIn(BaseModel):
    id: str = Field(default="playground", min_length=1, max_length=120)
    agent_id: str
    ended_by: str = Field(default="agent", pattern="^(agent|user|system)$")
    turns: list[TurnIn] = Field(min_length=1, max_length=200)


class ScoreIn(BaseModel):
    call: CallIn
    spec_yaml: str | None = Field(default=None, max_length=20_000)  # optional edited spec to score against


class GenerateIn(BaseModel):
    agent_id: str
    faults: list[str] = []
    seed: int | None = None


class RateLimiter:
    """Sliding-window limit per client IP. In-memory, so on serverless each instance counts separately:
    it stops one client hammering an instance, it is not a global quota."""

    def __init__(self, limit: int, window_s: float = 60.0):
        self.limit, self.window = limit, window_s
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        if len(self.hits) > 10_000:  # forget idle clients so memory stays bounded
            for k in [k for k, v in self.hits.items() if not v][:5_000]:
                del self.hits[k]
        return True


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


class Demo:
    """The synthetic dataset, scored once and kept in memory."""

    def __init__(self, agents_dir: Path):
        self.yaml = {}
        self.specs: dict[str, AgentSpec] = {}
        for p in sorted(agents_dir.glob("*.yaml")):
            text = p.read_text(encoding="utf-8")
            spec = load_spec_text(text)
            self.specs[spec.id], self.yaml[spec.id] = spec, text
        self.samples = generate()
        self.calls: dict[str, dict] = {}
        for s in self.samples:
            spec = self.specs[s.call.agent_id]
            rep = score_call(s.call, spec)
            self.calls[s.call.id] = report_dict(s.call, spec, rep, {"labels": s.labels, "planted": s.planted,
                                                                     "source": "synthetic"})

    @cached_property
    def benchmark(self) -> dict:
        return evaluate(self.samples, self.specs)


def _to_call(body: CallIn) -> Call:
    for t in body.turns:
        if t.end < t.start:
            raise HTTPException(422, "a turn ends before it starts")
    return Call(id=body.id, agent_id=body.agent_id, ended_by=body.ended_by,
                turns=[Turn(**t.model_dump()) for t in body.turns])


def create_app(db_url: str | None = None, agents_dir: Path = ROOT / "agents",
               web_dir: Path | None = ROOT / "web" / "dist", writes_per_minute: int = 60) -> FastAPI:
    demo = Demo(agents_dir)
    db_url = db_url or os.environ.get("CALLQA_DB")
    store = Store(db_url) if db_url else None
    app = FastAPI(title="Voice call QA", version="0.2.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])
    app.state.demo, app.state.store = demo, store
    limiter = RateLimiter(writes_per_minute)

    @app.middleware("http")
    async def limit_posts(request: Request, call_next):
        if request.method == "POST" and request.url.path.startswith("/api/") and not limiter.allow(client_ip(request)):
            return JSONResponse({"detail": "too many requests, try again in a minute"}, status_code=429)
        return await call_next(request)

    def all_calls(agent_id: str | None = None) -> list[dict]:
        calls = [c for c in demo.calls.values() if not agent_id or c["agent_id"] == agent_id]
        if store:
            calls += [c for c in store.all(agent_id) if c["id"] not in demo.calls]
        return calls

    @app.get("/api/health")
    def health():
        return {"ok": True, "demo_calls": len(demo.calls), "persistence": bool(store)}

    @app.get("/api/agents")
    def agents():
        return [{"id": s.id, "name": s.name, "persona": s.persona, "yaml": demo.yaml[s.id],
                 "flow": [asdict(f) for f in s.flow], "compliance_lines": s.compliance_lines,
                 "allowed_english": s.allowed_english,
                 "checks": [{"name": n, "weight": c.weight, "params": c.params, "enabled": c.enabled}
                            for n, c in s.checks.items()],
                 "faults": [f for f in FAULTS if f != "english" or SCRIPTS[s.id]["english"]]}
                for s in demo.specs.values()]

    @app.get("/api/faults")
    def faults():
        return [{"id": k, "label": v[0], "description": v[1], "should_flag": v[2]} for k, v in FAULT_INFO.items()]

    @app.get("/api/agents/{agent_id}/summary")
    def summary(agent_id: str):
        spec = demo.specs.get(agent_id)
        if not spec:
            raise HTTPException(404, "agent not found")
        return summarize(spec, all_calls(agent_id))

    @app.get("/api/calls")
    def list_calls(agent: str | None = None, check: str | None = None, q: str | None = None,
                   max_score: float | None = None, limit: int = Query(200, le=500)):
        rows = []
        for c in all_calls(agent):
            if check and check not in c["failed_checks"]:
                continue
            if q and q.lower() not in c["id"].lower():
                continue
            if max_score is not None and c["score"] > max_score:
                continue
            rows.append({k: c.get(k) for k in ("id", "agent_id", "score", "failed_checks", "planted", "source")}
                        | {"turns": len(c["turns"])})
        return rows[:limit]

    @app.get("/api/calls/{call_id}")
    def get_call(call_id: str):
        c = demo.calls.get(call_id) or (store.get(call_id) if store else None)
        if c is None:
            raise HTTPException(404, "call not found")
        return c

    @app.post("/api/score")
    def score(body: ScoreIn):
        """Score a call without storing it. Optionally score it against an edited spec."""
        if body.spec_yaml:
            try:
                spec = load_spec_text(body.spec_yaml)
            except SpecError as e:
                raise HTTPException(422, f"spec: {e}")
            if spec.id != body.call.agent_id:
                raise HTTPException(422, f"spec id '{spec.id}' does not match the call's agent '{body.call.agent_id}'")
        else:
            spec = demo.specs.get(body.call.agent_id)
            if not spec:
                raise HTTPException(404, f"unknown agent '{body.call.agent_id}'")
        call = _to_call(body.call)
        return report_dict(call, spec, score_call(call, spec), {"source": "playground"})

    @app.post("/api/calls")
    def post_call(body: CallIn):
        """Score and store a call. Needs CALLQA_DB; the hosted demo is read-only."""
        if not store:
            raise HTTPException(503, "this deployment has no database; use /api/score (results are kept in your browser)")
        spec = demo.specs.get(body.agent_id)
        if not spec:
            raise HTTPException(404, f"unknown agent '{body.agent_id}'")
        call = _to_call(body)
        scored = report_dict(call, spec, score_call(call, spec), {"source": "stored"})
        store.put(scored)
        return scored

    @app.post("/api/generate")
    def generate_call(body: GenerateIn):
        """Make a synthetic call with exactly the faults asked for (where the script allows them)."""
        if body.agent_id not in demo.specs:
            raise HTTPException(404, "agent not found")
        bad = [f for f in body.faults if f not in FAULTS]
        if bad:
            raise HTTPException(422, f"unknown faults: {bad}")
        seed = body.seed if body.seed is not None else random.randrange(1_000_000)
        s = make_call(body.agent_id, 0, random.Random(seed), set(body.faults), call_id=f"generated-{seed}")
        asked = set(body.faults)
        planted_kinds = {p.split(":")[0].split(" ")[0] for p in s.planted}
        alias = {"restart_after_interrupt": "restart", "caller_asked_repeat": "asked_repeat",
                 "english_turn": "english", "slow_response": "slow"}
        got = {alias.get(k, k) for k in planted_kinds}
        return {"seed": seed, "call": asdict(s.call), "labels": s.labels, "planted": s.planted,
                "not_planted": sorted(asked - got)}

    @app.get("/api/benchmark")
    def benchmark():
        return demo.benchmark

    if web_dir and (web_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    else:
        @app.get("/", response_class=HTMLResponse)
        def dashboard():
            return render_dashboard([summarize(s, all_calls(s.id)) for s in demo.specs.values()])

    return app


def render_dashboard(summaries: list[dict]) -> str:
    """Plain HTML fallback (also used for the static snapshot in docs/)."""
    e = html.escape
    sections = []
    for s in summaries:
        checks = "".join(f"<tr><td>{e(k)}</td><td>{v:.0%}</td></tr>" for k, v in s["fail_rate_by_check"].items())
        metrics = "".join(f"<tr><td>{e(k)}</td><td>{v}</td></tr>" for k, v in s["avg_metrics"].items())
        skipped = ", ".join(f"{e(k)} ({v})" for k, v in s["most_skipped_steps"].items()) or "none"
        worst = ", ".join(f"<code>{e(c['id'])}</code> {c['score']}" for c in s["worst_calls"]) or "none"
        sections.append(f"""
<section><h2>{e(s['name'])}</h2>
<p>{s['calls']} calls · persona <b>{e(s['persona'])}</b> · mean score <b>{s['mean_score']}</b></p>
<div class="grid"><table><tr><th>check (only this agent's)</th><th>calls failing</th></tr>{checks}</table>
<table><tr><th>metric</th><th>average</th></tr>{metrics}</table></div>
<p>Most skipped steps: {skipped}</p><p>Lowest-scoring calls: {worst}</p></section>""")
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Voice call QA</title><style>
body{{font-family:system-ui,sans-serif;margin:0 auto;max-width:960px;padding:16px;color:#1b1b1b;background:#fafaf7}}
section{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:16px;margin:16px 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #eee;padding:6px;text-align:left}}
code{{font-size:12px}}</style></head><body><h1>Voice call QA</h1>
<p>Synthetic demo data. Each agent shows only the checks its own spec turns on.</p>{''.join(sections)}</body></html>"""
