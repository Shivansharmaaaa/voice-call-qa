# Voice Call QA

Rule-based quality checks for voice-agent call transcripts, where **each agent defines what "good" means for itself**.

> Independent demo built by Shivansh Sharma as a sample for Hunar.AI's domain (conversational voice agents for frontline hiring). Not affiliated with or endorsed by Hunar.AI. All calls in this repo are synthetic; the company name in them ("Kaam Connect") is made up.

**Live dashboard (static snapshot of the 120 synthetic calls):** https://shivansharmaaaa.github.io/voice-call-qa/

## What it does

A voice agent can sound fine and still drift: it skips a screening question, asks two things in one breath, repeats itself, hangs up early, or slips out of its language persona. Each slip is rare, so it hides inside averages.

This service takes a call transcript (turns with speaker, text and timestamps), runs the checks the agent's spec turns on, and returns findings that point at specific turns, plus a 0-100 score. It stores every call and rolls them up per agent.

The main idea: **a metric is easy to compute but hard to define**. "Repeat rate" is a good example:

| Situation | Counted as a repeat? |
|---|---|
| Agent says the same question again for no reason | **Yes** |
| Caller interrupted the agent and it restarted the sentence | No |
| Caller said "phir se boliye" / "sorry?" | No |
| Agent repeated a compliance line the spec allows to repeat | No |
| Short acknowledgement ("haan ji", "theek hai") | Ignored |

The same goes for language. Hindi-English switching is correct for a Hinglish recruiter and a persona break for a strictly Hindi agent, so the **spec** decides, and the dashboard shows only the checks that agent actually runs.

## How it works

```
agents/*.yaml  ──►  spec.py (validate)  ──►  engine.py  ──►  checks/*  ──►  Report (findings, metrics, score)
                                              ▲                                   │
POST /calls (transcript JSON) ────────────────┘                                   ▼
                                                                         store.py (SQLAlchemy) ──► GET /agents/{id}/summary, dashboard
```

**Agent spec** (`agents/rider_onboarding_hindi.yaml`, shortened):

```yaml
id: rider-onboarding-hindi
persona: hindi_only
allowed_english: ["bike", "driving licence", "delivery", "app", "otp", "link"]
flow:
  - id: vehicle
    match: ["अपनी bike", "own bike"]
  - id: area
    match: ["किस इलाके", "which part of the city"]
  ...
compliance_lines: ["यह कॉल गुणवत्ता के लिए रिकॉर्ड की जा रही है"]
checks:
  coverage: {weight: 3}
  language: {weight: 2, max_off_share: 0.34}
  latency: {weight: 1, max_gap_s: 2.5}
```

**Checks**

| Check | Finds | How |
|---|---|---|
| `coverage` | a required step was skipped | step = first agent turn containing one of its match phrases; "skipped" only if a *later* step was reached |
| `order` | steps asked out of order | first-hit turn indices must follow the flow order |
| `early_exit` | agent ended the call before required steps | uses `ended_by`; if the caller hung up it is reported as info, not a failure |
| `one_question` | more than N questions in one turn | counts `?`; warns when the transcript has no punctuation at all |
| `repeats` | unexplained repeats | similarity = max(character ratio, token Jaccard), with the exemptions above |
| `language` | turns outside the persona | Devanagari + a romanised-Hindi word list vs English tokens, after removing allowed English words |
| `latency` | slow agent responses | gap between the caller's turn end and the agent's turn start; p50/p95 reported |

**Score** = weighted share of enabled checks with no failing finding. A call with one skipped step loses the whole `coverage` weight; it is deliberately coarse so a score is easy to explain.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                          # 23 tests
python -m callqa.evaluate          # benchmark against planted faults
python scripts/demo.py             # 120 synthetic calls through the API -> docs/index.html
uvicorn callqa.api:app --reload    # API + dashboard on http://127.0.0.1:8000
```

Score a call:

```bash
curl -X POST localhost:8000/calls -H 'content-type: application/json' -d '{
  "id": "c1", "agent_id": "field-sales-screener", "ended_by": "agent",
  "turns": [
    {"speaker": "agent", "text": "Namaste, main Priya bol rahi hoon.", "start": 0, "end": 2},
    {"speaker": "user",  "text": "Haan ji", "start": 2.5, "end": 3}
  ]}'
```

Endpoints: `GET /agents`, `PUT /agents` (YAML body), `POST /calls`, `GET /calls/{id}`, `GET /agents/{id}/summary`, `GET /` (dashboard). Storage is SQLite by default; set `CALLQA_DB` to any SQLAlchemy URL (e.g. Postgres).

## How well do the checks work?

`callqa/synth.py` builds 120 calls from clean scripts (60 Hinglish, 60 Hindi), then plants faults on purpose and records them as labels. It also plants cases that **must not** be flagged. `callqa/evaluate.py` compares the checker's findings to the labels:

| Finding | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|
| skipped step | 16 | 0 | 0 | 1.00 | 1.00 |
| early exit | 22 | 0 | 0 | 1.00 | 1.00 |
| off-persona turn | 15 | 0 | 0 | 1.00 | 1.00 |
| slow response | 16 | 0 | 0 | 1.00 | 1.00 |
| two questions in a turn | 21 | 0 | 2 | 1.00 | 0.91 |
| out of order | 24 | 0 | 0 | 1.00 | 1.00 |
| repeat | 18 | 0 | 0 | 1.00 | 1.00 |

Must-not-flag cases: 23 restarts after an interruption, 21 caller-requested repeats, 16 repeated compliance lines, 13 caller hang-ups. **None were wrongly flagged.**

**Read these numbers carefully.** The calls come from the same templates the match phrases were written for, so this measures whether the rules do what they claim, not how they would do on real calls. Real transcripts have paraphrases, STT errors and accents these templates don't.

Two things the benchmark did teach:
- The first run had 7 false "skipped step" flags. When the Hindi agent slipped into English, the step's Hindi-only phrases didn't match, so a step that *was* asked looked skipped. Adding English match phrases fixed it. The step matcher needs phrases for every language the agent might use.
- The 2 missed double questions are in calls whose punctuation was stripped (simulated STT output). Counting `?` can't see those questions, so the check now raises a `no_punctuation` warning instead of silently passing.

## Limitations (honest)

- **Phrase matching is brittle.** A paraphrased question ("aap kahan se ho?") won't match `kis area`. Next step: an embedding similarity or an LLM judge for step detection, benchmarked against these rules on the same labels.
- **Text only.** No audio: interruptions, silence and latency come from transcript timestamps.
- **Language detection is a small word list.** Fine for Hindi/English; it does not handle Tamil, Telugu or other code-switched pairs yet.
- **Question counting needs punctuation.** See above.
- **Synthetic data only.** Not tested on real calls.

## Testing status

Run on macOS, Python 3.14:
- `pytest -q`: 23 tests pass (each check and exemption, spec validation, API validation, re-posting a call, dashboard render, and a benchmark floor).
- `python -m callqa.evaluate` and `python scripts/demo.py`: run, numbers above.
- The API was exercised through FastAPI's TestClient (same app object); the uvicorn command above was not part of the test run.

## Likely interview questions

1. *Why rules instead of an LLM judge?* Rules are cheap, deterministic and explainable per turn, and they give a baseline. An LLM judge is the next step for paraphrases, but it needs its own evaluation against labels like these.
2. *How do you avoid counting a restart after an interruption as a repeat?* The earlier turn is marked `interrupted`; if it is the agent's previous turn and the new turn contains most of its tokens, it's exempt.
3. *Why does the dashboard differ per agent?* Each spec enables its own checks and weights, so a Hinglish agent never shows a language failure rate that would mean nothing for it.
4. *What would break first on real calls?* Step matching on paraphrases and STT errors, then question counting on unpunctuated output.
5. *How would you scale this to a million calls a day?* The checks are pure functions over a transcript, so run them in a queue consumer (one call per message), write findings in batches, and pre-aggregate the per-agent rollups instead of computing them on read.
6. *Why is the score so coarse?* A per-check pass/fail with weights is easy to explain to an ops team. Per-finding penalties are possible but harder to reason about.
