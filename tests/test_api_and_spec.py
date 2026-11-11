from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from callqa.api import create_app
from callqa.evaluate import evaluate
from callqa.spec import SpecError, load_dir, load_spec_text
from callqa.synth import generate

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app(web_dir=None))


@pytest.fixture()
def db_client(tmp_path):
    return TestClient(create_app(db_url=f"sqlite:///{tmp_path / 't.db'}", web_dir=None))


def test_demo_data_loaded(client):
    h = client.get("/api/health").json()
    assert h["demo_calls"] == 120 and h["persistence"] is False


def test_agents_have_their_own_checks(client):
    agents = {a["id"]: a for a in client.get("/api/agents").json()}
    rider = {c["name"]: c for c in agents["rider-onboarding-hindi"]["checks"]}
    sales = {c["name"]: c for c in agents["field-sales-screener"]["checks"]}
    assert rider["language"]["enabled"] and not sales["language"]["enabled"]
    assert "english" not in agents["field-sales-screener"]["faults"]


def test_summary_and_explorer(client):
    s = client.get("/api/agents/rider-onboarding-hindi/summary").json()
    assert s["calls"] == 60 and sum(s["score_histogram"]) == 60
    failing = client.get("/api/calls", params={"agent": "rider-onboarding-hindi", "check": "language"}).json()
    assert failing and all("language" in c["failed_checks"] for c in failing)
    one = client.get(f"/api/calls/{failing[0]['id']}").json()
    assert "language:off_persona" in one["labels"]


def test_score_is_stateless_and_accepts_an_edited_spec(client):
    call = asdict(generate(n_per_agent=1, seed=1)[0].call)
    r = client.post("/api/score", json={"call": call})
    assert r.status_code == 200 and 0 <= r.json()["score"] <= 100
    assert client.get(f"/api/calls/{call['id']}").json()["source"] == "synthetic"  # unchanged
    yaml = client.get("/api/agents").json()[0]["yaml"].replace("max_gap_s: 2.0", "max_gap_s: 0.1")
    strict = client.post("/api/score", json={"call": call, "spec_yaml": yaml}).json()
    assert "latency" in strict["failed_checks"]


def test_score_rejects_bad_input(client):
    base = {"id": "x", "agent_id": "field-sales-screener"}
    assert client.post("/api/score", json={"call": {**base, "agent_id": "nope", "turns": [
        {"speaker": "agent", "text": "hi", "start": 0, "end": 1}]}}).status_code == 404
    assert client.post("/api/score", json={"call": {**base, "turns": [
        {"speaker": "bot", "text": "hi", "start": 0, "end": 1}]}}).status_code == 422
    assert client.post("/api/score", json={"call": {**base, "turns": [
        {"speaker": "agent", "text": "hi", "start": 2, "end": 1}]}}).status_code == 422
    assert client.post("/api/score", json={"call": {**base, "turns": [
        {"speaker": "agent", "text": "hi", "start": 0, "end": 1}]}, "spec_yaml": "id: a\nname: b\npersona: x\nflow: []"}).status_code == 422


def test_generate_plants_what_was_asked(client):
    r = client.post("/api/generate", json={"agent_id": "rider-onboarding-hindi", "faults": ["english", "restart"], "seed": 5}).json()
    assert "language:off_persona" in r["labels"]
    assert any(p.startswith("restart_after_interrupt") for p in r["planted"])
    scored = client.post("/api/score", json={"call": r["call"]}).json()
    assert "language" in scored["failed_checks"] and "repeats" not in scored["failed_checks"]
    assert client.post("/api/generate", json={"agent_id": "field-sales-screener", "faults": ["nope"]}).status_code == 422


def test_hosted_demo_is_read_only_but_db_mode_stores(client, db_client):
    call = asdict(generate(n_per_agent=1, seed=1)[0].call) | {"id": "mine-1"}
    assert client.post("/api/calls", json=call).status_code == 503
    assert db_client.post("/api/calls", json=call).status_code == 200
    db_client.post("/api/calls", json=call)  # re-posting replaces
    assert db_client.get("/api/calls/mine-1").json()["source"] == "stored"
    assert db_client.get("/api/agents/field-sales-screener/summary").json()["calls"] == 61


def test_benchmark_endpoint(client):
    b = client.get("/api/benchmark").json()
    assert b["calls"] == 120 and "repeats:repeat" in b["per_finding"]


def test_fallback_dashboard_renders(client):
    assert "Voice call QA" in client.get("/").text


def test_spec_errors():
    with pytest.raises(SpecError):
        load_spec_text("id: a\nname: b\npersona: mixed\nflow:\n  - id: x\n    match: [a]\n  - id: x\n    match: [b]\n")
    with pytest.raises(SpecError):
        load_spec_text("id: a\nname: b\npersona: mixed\nflow: []\nchecks:\n  vibes: {}\n")


def test_benchmark_floor():
    """Guards against regressions on the synthetic set. Not a claim about real calls."""
    result = evaluate(generate(), load_dir(ROOT / "agents"))
    for key, row in result["per_finding"].items():
        assert row["precision"] >= 0.95, key
        assert row["recall"] >= 0.85, key
    assert all(v["wrongly_flagged"] == 0 for v in result["must_not_flag"].values())


def test_importing_the_api_builds_nothing():
    import importlib
    import callqa.api as mod
    importlib.reload(mod)
    assert not hasattr(mod, "app")


def test_rate_limiter_window():
    from callqa.api import RateLimiter
    rl = RateLimiter(limit=2, window_s=60)
    assert rl.allow("a", now=0) and rl.allow("a", now=1)
    assert not rl.allow("a", now=2)
    assert rl.allow("b", now=2)
    assert rl.allow("a", now=62)


def test_posts_are_rate_limited_per_client():
    c = TestClient(create_app(web_dir=None, writes_per_minute=3))
    body = {"agent_id": "field-sales-screener", "faults": []}
    codes = [c.post("/api/generate", json=body, headers={"x-forwarded-for": "1.2.3.4"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    assert c.post("/api/generate", json=body, headers={"x-forwarded-for": "5.6.7.8"}).status_code == 200
    assert c.get("/api/health").status_code == 200  # reads are not limited


@pytest.mark.skipif(not __import__("os").environ.get("CALLQA_TEST_PG"), reason="set CALLQA_TEST_PG to a Postgres URL")
def test_database_mode_on_postgres():
    import os
    from sqlalchemy import create_engine, text
    url = os.environ["CALLQA_TEST_PG"]
    c = TestClient(create_app(db_url=url, web_dir=None))
    call = asdict(generate(n_per_agent=1, seed=2)[0].call) | {"id": "pg-test-1"}
    assert c.post("/api/calls", json=call).status_code == 200
    assert c.post("/api/calls", json=call).status_code == 200  # replace, not duplicate
    assert c.get("/api/calls/pg-test-1").json()["source"] == "stored"
    with create_engine(url).connect() as conn:
        assert conn.execute(text("select count(*) from calls where id = 'pg-test-1'")).scalar() == 1
        conn.execute(text("delete from findings where call_id = 'pg-test-1'"))
        conn.execute(text("delete from calls where id = 'pg-test-1'"))
        conn.commit()
