"""Train one step classifier per agent and export it to callqa/models/<agent>.json.

Run: python ml/train.py        (needs scikit-learn: pip install -r requirements-dev.txt)

Steps:
  1. Load hand-labelled utterances (ml/train_utterances.yaml).
  2. Augment: Hinglish spelling variants, dropped letters, case and punctuation noise,
     so the model sees the kind of variation STT and Hinglish produce.
  3. 5-fold cross-validation on the training set (accuracy reported).
  4. Fit TF-IDF (character n-grams, sublinear tf) + logistic regression on everything.
  5. Score the HELD-OUT paraphrases (ml/test_paraphrases.yaml), which are never trained on.
  6. Pick the confidence threshold from out-of-fold training predictions (never the test set).
  7. Export vocabulary, idf, weights, intercepts and threshold as JSON for plain-Python inference.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import StratifiedKFold, cross_val_predict, cross_val_score
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from callqa.ml import MODELS_DIR, features  # noqa: E402

SEED = 13
SPELLING = [("ee", "i"), ("aa", "a"), ("rehte", "rahte"), ("hai", "he"), ("kya", "kia"), ("hoon", "hu"),
            ("kitna", "kitnaa"), ("kitne", "kitnay"), ("aap", "ap"), ("mein", "me"), ("ke", "k"), ("w", "v")]


def augment(text: str, rng: random.Random, n: int = 3) -> list[str]:
    out = []
    for _ in range(n):
        t = text
        for a, b in SPELLING:
            if a in t and rng.random() < 0.35:
                t = t.replace(a, b)
        words = t.split()
        if len(words) > 3 and rng.random() < 0.4:  # simulate a dropped letter (STT or typing)
            i = rng.randrange(len(words))
            if len(words[i]) > 3:
                k = rng.randrange(1, len(words[i]) - 1)
                words[i] = words[i][:k] + words[i][k + 1:]
        t = " ".join(words)
        if rng.random() < 0.5:
            t = t.lower()
        if rng.random() < 0.3:
            t += "?"
        out.append(t)
    return out


def make_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(analyzer=features, sublinear_tf=True, norm="l2", lowercase=False)


def make_model():
    return LogisticRegression(C=8.0, max_iter=5000, class_weight="balanced")


def pick_threshold(X: list[str], y: list[str], cv) -> tuple[float, float]:
    """Choose the confidence below which a sentence counts as 'other', using out-of-fold
    predictions on the training sentences. Ties go to the higher threshold (fewer false matches)."""
    pipe = make_pipeline(make_vectorizer(), make_model())
    proba = cross_val_predict(pipe, X, y, cv=cv, method="predict_proba")
    classes = sorted(set(y))
    best = (0.0, 0.0)
    for t in [round(0.15 + 0.05 * i, 2) for i in range(12)]:
        pred = [classes[r.argmax()] if r.max() >= t else "other" for r in proba]
        acc = sum(p == g for p, g in zip(pred, y)) / len(y)
        if acc >= best[1]:
            best = (t, acc)
    return best


def export(agent_id: str, vec: TfidfVectorizer, clf: LogisticRegression, meta: dict) -> dict:
    """Everything plain-Python inference needs (see callqa/ml.py), as JSON-ready data."""
    classes = [str(c) for c in clf.classes_]
    coef = clf.coef_  # (n_classes, n_features)
    inv = sorted(vec.vocabulary_.items(), key=lambda kv: kv[1])
    return {
        "agent_id": agent_id,
        "classes": classes,
        "vocab": {f: int(i) for f, i in inv},
        "idf": [round(float(v), 6) for v in vec.idf_],
        "weights": [[round(float(coef[k][j]), 6) for k in range(len(classes))] for j in range(len(inv))],
        "intercept": [round(float(v), 6) for v in clf.intercept_],
        "meta": meta,
    }


def rows(block: dict) -> tuple[list[str], list[str]]:
    X, y = [], []
    for label, texts in block.items():
        for t in texts:
            X.append(t)
            y.append(label)
    return X, y


def main() -> None:
    train = yaml.safe_load((ROOT / "ml" / "train_utterances.yaml").read_text(encoding="utf-8"))
    test = yaml.safe_load((ROOT / "ml" / "test_paraphrases.yaml").read_text(encoding="utf-8"))
    rng = random.Random(SEED)
    MODELS_DIR.mkdir(exist_ok=True)
    report = {}
    for agent_id, block in train.items():
        X, y = rows(block)
        Xa, ya = list(X), list(y)
        for t, label in zip(X, y):
            for v in augment(t, rng):
                Xa.append(v)
                ya.append(label)

        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
        # Cross-validate on the original sentences only, so augmented copies can't leak across folds.
        cv_acc = cross_val_score(make_pipeline(make_vectorizer(), make_model()), X, y, cv=cv).mean()
        threshold, thr_acc = pick_threshold(X, y, cv)

        vec = make_vectorizer()
        clf = make_model()
        clf.fit(vec.fit_transform(Xa), ya)

        Xt, yt = rows(test[agent_id])
        proba = clf.predict_proba(vec.transform(Xt))
        pred = [str(clf.classes_[row.argmax()]) if row.max() >= threshold else "other" for row in proba]
        test_acc = accuracy_score(yt, pred)
        mistakes = [{"text": t, "true": a, "predicted": b, "p": round(float(r.max()), 2)}
                    for t, a, b, r in zip(Xt, yt, pred, proba) if a != b]
        print(f"\n== {agent_id}: {len(X)} sentences (+{len(Xa) - len(X)} augmented), "
              f"{len(vec.vocabulary_)} features")
        print(f"5-fold CV accuracy (training set): {cv_acc:.3f}")
        print(f"Confidence threshold (from CV):    {threshold:.2f} (CV accuracy with it {thr_acc:.3f})")
        print(f"Held-out paraphrase accuracy:       {test_acc:.3f} on {len(Xt)} sentences")
        print(classification_report(yt, pred, zero_division=0))
        for m in mistakes:
            print("  miss:", m)

        model = export(agent_id, vec, clf, {
            "trained_sentences": len(X), "augmented_rows": len(Xa), "features": len(vec.vocabulary_),
            "cv_accuracy": round(float(cv_acc), 3), "heldout_accuracy": round(float(test_acc), 3),
            "heldout_sentences": len(Xt), "threshold": threshold,
            "algorithm": "char 2-4-gram TF-IDF + logistic regression"})
        (MODELS_DIR / f"{agent_id}.json").write_text(json.dumps(model, ensure_ascii=False, separators=(",", ":")),
                                                     encoding="utf-8")
        report[agent_id] = {**model["meta"], "heldout_mistakes": mistakes}
    (ROOT / "ml" / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
