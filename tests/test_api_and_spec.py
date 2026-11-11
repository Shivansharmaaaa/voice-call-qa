from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from callqa.api import create_app
from callqa.evaluate import evaluate
from callqa.spec import SpecError, load_dir, load_spec_text
from callqa.synth import generate


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(f"sqlite:///{tmp_path / 't.db'}"))


def test_agents_loaded_with_their_own_checks(client):
    agents = {a["id"]: a for a in client.get("/agents").json()}
    assert "language" in agents["rider-onboarding-hindi"]["checks"]
    assert "language" not in agents["field-sales-screener"]["checks"]


def test_post_call_scores_and_stores(client):
    call = asdict(generate(n_per_agent=1, seed=1)[0].call)
    r = client.post("/calls", json=call)
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["score"] <= 100
    assert client.get(f"/calls/{call['id']}").json()["score"] == body["score"]
    summary = client.get(f"/agents/{call['agent_id']}/summary").json()
    assert summary["calls"] == 1


def test_reposting_a_call_replaces_it(client):
    call = asdict(generate(n_per_agent=1, seed=1)[0].call)
    client.post("/calls", json=call)
    client.post("/calls", json=call)
    assert client.get(f"/agents/{call['agent_id']}/summary").json()["calls"] == 1


def test_bad_input_is_rejected(client):
    assert client.post("/calls", json={"id": "x", "agent_id": "nope", "turns": [
        {"speaker": "agent", "text": "hi", "start": 0, "end": 1}]}).status_code == 404
    assert client.post("/calls", json={"id": "x", "agent_id": "field-sales-screener", "turns": [
        {"speaker": "bot", "text": "hi", "start": 0, "end": 1}]}).status_code == 422
    assert client.post("/calls", json={"id": "x", "agent_id": "field-sales-screener", "turns": [
        {"speaker": "agent", "text": "hi", "start": 2, "end": 1}]}).status_code == 422


def test_put_agent_validates_yaml(client):
    assert client.put("/agents", content="id: a\nname: b\npersona: klingon\nflow: []",
                      headers={"content-type": "text/plain"}).status_code == 422
    ok = "id: tiny\nname: Tiny\npersona: mixed\nflow:\n  - id: hi\n    match: [hello]\n"
    assert client.put("/agents", content=ok, headers={"content-type": "text/plain"}).json()["id"] == "tiny"


def test_dashboard_renders(client):
    r = client.get("/")
    assert r.status_code == 200 and "Voice call QA" in r.text


def test_spec_errors():
    with pytest.raises(SpecError):
        load_spec_text("id: a\nname: b\npersona: mixed\nflow:\n  - id: x\n    match: [a]\n  - id: x\n    match: [b]\n")
    with pytest.raises(SpecError):
        load_spec_text("id: a\nname: b\npersona: mixed\nflow: []\nchecks:\n  vibes: {}\n")


def test_benchmark_floor():
    """Guards against regressions on the synthetic set. Not a claim about real calls."""
    from pathlib import Path
    specs = load_dir(Path(__file__).resolve().parent.parent / "agents")
    result = evaluate(generate(), specs)
    for key, row in result["per_finding"].items():
        assert row["precision"] >= 0.95, key
        assert row["recall"] >= 0.85, key
    assert all(v["wrongly_flagged"] == 0 for v in result["must_not_flag"].values())
