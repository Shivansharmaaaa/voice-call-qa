"""Trained step classifier: which flow step (if any) is this agent sentence asking?

Model: character n-gram TF-IDF + multinomial logistic regression, one model per agent,
trained with scikit-learn by ml/train.py on hand-labelled utterances.

Why character n-grams: Hinglish transcripts spell the same word many ways
("rehte", "rahte", "rhte"; "kitna", "kitnaa"), and mix Devanagari with Latin script.
Character pieces of words survive those variations where whole-word matching fails.

Inference here is plain Python (no numpy or scikit-learn) so it fits in a small
serverless function. tests/test_ml.py checks it gives the same probabilities as
scikit-learn on the same inputs.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from .text import normalize

MODELS_DIR = Path(__file__).resolve().parent / "models"
NGRAM_RANGE = (2, 4)
CLAUSE_SPLIT = re.compile(r"[?？.!।]+")


def features(text: str) -> list[str]:
    """Character 2-4-grams inside word boundaries, plus whole words. Shared by training and inference."""
    out: list[str] = []
    for word in normalize(text).split():
        padded = f" {word} "
        for n in range(NGRAM_RANGE[0], NGRAM_RANGE[1] + 1):
            out.extend(padded[i:i + n] for i in range(len(padded) - n + 1))
        out.append(f"w:{word}")
    return out


def clauses(text: str) -> list[tuple[int, str]]:
    """Split a turn into sentences, keeping each one's character offset in the normalised turn."""
    parts, pos = [], 0
    for piece in CLAUSE_SPLIT.split(text):
        norm = normalize(piece)
        if norm:
            parts.append((pos, piece))
            pos += len(norm) + 1
    return parts or [(0, text)]


class StepModel:
    def __init__(self, data: dict):
        self.agent_id: str = data["agent_id"]
        self.classes: list[str] = data["classes"]
        self.vocab: dict[str, int] = data["vocab"]
        self.idf: list[float] = data["idf"]
        self.weights: list[list[float]] = data["weights"]  # feature-major: weights[feature][class]
        self.intercept: list[float] = data["intercept"]
        self.meta: dict = data.get("meta", {})

    def proba(self, text: str) -> dict[str, float]:
        counts = Counter(f for f in features(text) if f in self.vocab)
        vec = {self.vocab[f]: (1.0 + math.log(c)) * self.idf[self.vocab[f]] for f, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        logits = list(self.intercept)
        for j, v in vec.items():
            w = self.weights[j]
            for k in range(len(logits)):
                logits[k] += w[k] * v / norm
        top = max(logits)
        exps = [math.exp(z - top) for z in logits]
        total = sum(exps)
        return {c: e / total for c, e in zip(self.classes, exps)}

    def predict(self, text: str) -> tuple[str, float]:
        p = self.proba(text)
        label = max(p, key=p.get)
        return label, p[label]


@lru_cache(maxsize=None)
def load_model(agent_id: str) -> StepModel | None:
    path = MODELS_DIR / f"{agent_id}.json"
    if not path.exists():
        return None
    return StepModel(json.loads(path.read_text(encoding="utf-8")))
