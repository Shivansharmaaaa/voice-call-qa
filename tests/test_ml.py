"""The trained step classifier: parity with scikit-learn, no train/test leakage, real effect on scoring."""
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from callqa import Call, Turn, load_spec_file, score_call
from callqa.evaluate import compare_matchers
from callqa.ml import StepModel, clauses, features, load_model
from callqa.spec import SpecError, load_dir, load_spec_text
from callqa.text import normalize

ROOT = Path(__file__).resolve().parent.parent
TRAIN = yaml.safe_load((ROOT / "ml" / "train_utterances.yaml").read_text(encoding="utf-8"))
TEST = yaml.safe_load((ROOT / "ml" / "test_paraphrases.yaml").read_text(encoding="utf-8"))
SALES = load_spec_file(ROOT / "agents" / "field_sales_screener.yaml")


def test_no_test_sentence_appears_in_training():
    for agent, block in TEST.items():
        train = {normalize(t) for texts in TRAIN[agent].values() for t in texts}
        for texts in block.values():
            for t in texts:
                assert normalize(t) not in train, t


def test_python_inference_matches_scikit_learn():
    sk = pytest.importorskip("sklearn")  # noqa: F841  (training dependency only)
    sys.path.insert(0, str(ROOT / "ml"))
    import train as tr  # ml/train.py

    X, y = tr.rows(TRAIN["field-sales-screener"])
    vec, clf = tr.make_vectorizer(), tr.make_model()
    clf.fit(vec.fit_transform(X), y)
    model = StepModel(tr.export("field-sales-screener", vec, clf, {}))
    samples = ["Aap kahan rehte ho", "Notice period kitna hai", "kitni salary milti h", "ok ji", "zzz qqq"]
    expected = clf.predict_proba(vec.transform(samples))
    for text, row in zip(samples, expected):
        got = model.proba(text)
        for cls, p in zip(clf.classes_, row):
            assert got[str(cls)] == pytest.approx(float(p), abs=1e-4), (text, cls)


def test_serving_does_not_need_scikit_learn():
    code = ("import sys; from callqa.ml import load_model; m = load_model('field-sales-screener'); "
            "print(m.predict('Aap kis area mein rehte ho')[0]); print('sklearn' in sys.modules, 'numpy' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    assert out == ["location", "False", "False"]


def test_shipped_models_load_and_carry_their_threshold():
    for agent in TRAIN:
        m = load_model(agent)
        assert m is not None and set(TRAIN[agent]) == set(m.classes)
        assert 0 < m.meta["threshold"] < 1


def test_features_and_clauses():
    assert " ka" in features("kaam") and "w:kaam" in features("Kaam!")
    parts = clauses("Aapka notice period kitna hai? Aur salary kitni hai?")
    assert [p[1].strip() for p in parts] == ["Aapka notice period kitna hai", "Aur salary kitni hai"]
    assert parts[0][0] < parts[1][0]


def _call(lines, agent="field-sales-screener"):
    turns, t = [], 0.0
    for speaker, text in lines:
        turns.append(Turn(speaker, text, t, t + 2))
        t += 2.8
    return Call(id="m", agent_id=agent, turns=turns, ended_by="agent")


PARAPHRASED = [
    ("agent", "Namaste, main Kaam Connect se Priya bol rahi hoon."), ("user", "Haan"),
    ("agent", "Yeh call quality ke liye record ho rahi hai, theek hai?"), ("user", "Haan"),
    ("agent", "Aapne field sales ki job ke liye apply kiya tha, kya aap interested hain?"), ("user", "Haan"),
    ("agent", "Abhi aap kidhar stay kar rahe ho?"), ("user", "Thane"),            # location, no rule phrase
    ("agent", "Sales line mein aap kitne saalon se ho?"), ("user", "Do saal"),   # experience, no rule phrase
    ("agent", "Aapka notice period kitna hai?"), ("user", "Ek mahina"),
    ("agent", "Aapki current salary kitni hai?"), ("user", "Pandrah hazaar"),
    ("agent", "Kal subah gyarah baje interview ka slot chalega?"), ("user", "Haan"),
    ("agent", "Dhanyavaad, details SMS par aa jayengi."),
]


def test_model_recognises_paraphrases_that_rules_miss():
    rules = score_call(_call(PARAPHRASED), replace(SALES, step_matcher="phrase"))
    hybrid = score_call(_call(PARAPHRASED), replace(SALES, step_matcher="hybrid"))
    assert "coverage" in rules.failed_checks()
    assert "coverage" not in hybrid.failed_checks()
    ml_steps = {f.step for f in hybrid.findings if f.code == "ml_step_match"}
    assert {"location", "experience"} <= ml_steps


def test_missing_model_falls_back_to_rules_and_says_so():
    spec = load_spec_text("id: no-model\nname: x\npersona: mixed\nstep_matcher: ml\nflow:\n  - id: hi\n    match: [hello]\n"
                          "checks:\n  coverage: {}\n")
    r = score_call(Call(id="c", agent_id="no-model", turns=[Turn("agent", "hello there", 0, 1)]), spec)
    assert any(f.code == "ml_unavailable" for f in r.findings)
    assert r.score == 100.0


def test_spec_validates_matcher_settings():
    with pytest.raises(SpecError):
        load_spec_text("id: a\nname: b\npersona: mixed\nstep_matcher: magic\nflow: []\n")
    with pytest.raises(SpecError):
        load_spec_text("id: a\nname: b\npersona: mixed\nml_threshold: 2\nflow: []\n")


def test_ml_beats_rules_on_paraphrased_calls():
    """Regression floor on the paraphrase benchmark (held-out wording)."""
    cmp = compare_matchers(load_dir(ROOT / "agents"), n_per_agent=30)
    para = cmp["paraphrased"]
    assert para["hybrid"]["flow_f1"] >= 0.8
    assert para["hybrid"]["flow_f1"] > para["phrase"]["flow_f1"] + 0.3
    assert cmp["template"]["hybrid"]["flow_f1"] >= 0.98
