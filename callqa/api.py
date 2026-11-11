"""HTTP API and a small dashboard.

Run: uvicorn callqa.api:app --reload   (loads every spec in agents/ on start)
"""
from __future__ import annotations

import html
import os
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .engine import score_call
from .models import Call, Turn
from .spec import SpecError
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


class TurnIn(BaseModel):
    speaker: str = Field(pattern="^(agent|user)$")
    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    interrupted: bool = False


class CallIn(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    agent_id: str
    ended_by: str = Field(default="agent", pattern="^(agent|user|system)$")
    turns: list[TurnIn] = Field(min_length=1)


def create_app(db_url: str | None = None, agents_dir: Path | None = ROOT / "agents") -> FastAPI:
    store = Store(db_url or os.environ.get("CALLQA_DB", "sqlite:///callqa.db"))
    if agents_dir and agents_dir.exists():
        for p in sorted(agents_dir.glob("*.yaml")):
            store.put_agent(p.read_text(encoding="utf-8"))
    app = FastAPI(title="Voice call QA", version="0.1.0")
    app.state.store = store

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/agents")
    def list_agents():
        return [{"id": a.id, "name": a.name, "persona": a.persona,
                 "checks": [n for n in a.checks if a.check(n).enabled]} for a in store.list_agents()]

    @app.put("/agents")
    def put_agent(spec_yaml: str = Body(..., media_type="text/plain")):
        try:
            spec = store.put_agent(spec_yaml)
        except SpecError as e:
            raise HTTPException(422, str(e))
        return {"id": spec.id, "name": spec.name}

    @app.post("/calls")
    def post_call(body: CallIn):
        spec = store.get_agent(body.agent_id)
        if spec is None:
            raise HTTPException(404, f"unknown agent '{body.agent_id}'")
        for t in body.turns:
            if t.end < t.start:
                raise HTTPException(422, "a turn ends before it starts")
        call = Call(id=body.id, agent_id=body.agent_id, ended_by=body.ended_by,
                    turns=[Turn(**t.model_dump()) for t in body.turns])
        report = score_call(call, spec)
        store.put_report(report, [t.model_dump() for t in body.turns], body.ended_by)
        return store.get_call(body.id)

    @app.get("/calls/{call_id}")
    def get_call(call_id: str):
        data = store.get_call(call_id)
        if data is None:
            raise HTTPException(404, "call not found")
        return data

    @app.get("/agents/{agent_id}/summary")
    def summary(agent_id: str):
        try:
            return store.summary(agent_id)
        except KeyError:
            raise HTTPException(404, "agent not found")

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        return render_dashboard([store.summary(a.id) for a in store.list_agents()])

    return app


def render_dashboard(summaries: list[dict]) -> str:
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


app = create_app()
