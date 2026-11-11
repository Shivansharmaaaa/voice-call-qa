# Voice Call QA

Rule-based quality checks for voice-agent call transcripts, where **each agent defines what "good" means for itself**.

> Independent demo built by Shivansh Sharma as a sample for Hunar.AI's domain (conversational voice agents for frontline hiring). Not affiliated with or endorsed by Hunar.AI. All calls in this repo are synthetic; the company name in them ("Kaam Connect") is made up.

## Try it: https://voice-call-qa.vercel.app

- **Overview:** each agent's dashboard, showing only the checks that agent runs.
- **Calls:** all 120 synthetic calls, filterable by failing check. Each call opens turn by turn, with every finding pinned to the turn it's about and the planted ground truth beside it.
- **Playground:** pick an agent, tick the faults to plant (skip a question, interrupt the agent, slip into English, go silent…), generate a call, edit any turn, optionally edit the agent's YAML spec, and score it live. Results can be saved in your browser.
- **Benchmark:** precision and recall of every check against the planted faults.

(The old static snapshot is still at https://shivansharmaaaa.github.io/voice-call-qa/.)

## What it does

A voice agent can sound fine and still drift: it skips a screening question, asks two things in one breath, repeats itself, hangs up early, or slips out of its language persona. Each slip is rare, so it hides inside averages.

This service takes a call transcript (turns with speaker, text and timestamps), runs the checks the agent's spec turns on, and returns findings that point at specific turns, plus a 0-100 score. It rolls calls up per agent, and can store them in a database when self-hosted.

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
                 React + TypeScript app (web/)  ── fetch /api/* ──┐
                                                                   ▼
agents/*.yaml ─► spec.py ─► engine.py ─► checks/* ─► Report ─► FastAPI (callqa/api.py)
                                 ▲                                 │
          synth.py (calls with planted faults) ─► in-memory demo ──┤
                                                                   └─► store.py (SQLAlchemy, optional: CALLQA_DB)
```

**Hosting.** On Vercel the React build is served as static files and `api/index.py` runs the same FastAPI app as a Python serverless function. Serverless functions have no lasting disk, so the hosted demo generates and scores the 120 synthetic calls in memory at start-up (well under a second), `/api/score` is stateless, and calls you score in the Playground are saved in your own browser. Self-hosted, set `CALLQA_DB` to any SQLAlchemy URL (SQLite or Postgres) and `POST /api/calls` stores scored calls, with findings as queryable rows.

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
pip install -r requirements-dev.txt
pytest -q                               # 26 tests
python -m callqa.evaluate               # benchmark against planted faults
cd web && npm install && npm run build  # React app -> web/dist
cd .. && uvicorn callqa.api:app         # API + app on http://127.0.0.1:8000 (serves web/dist)
# or, for frontend work: uvicorn on :8765 and `cd web && npm run dev` (proxies /api)
```

Score a call:

```bash
curl -X POST https://voice-call-qa.vercel.app/api/score -H 'content-type: application/json' -d '{"call": {
  "id": "c1", "agent_id": "field-sales-screener", "ended_by": "agent",
  "turns": [
    {"speaker": "agent", "text": "Namaste, main Priya bol rahi hoon.", "start": 0, "end": 2},
    {"speaker": "user",  "text": "Haan ji", "start": 2.5, "end": 3}
  ]}}'
```

Endpoints (interactive docs at `/api/docs`):

| Endpoint | What it does |
|---|---|
| `GET /api/agents` | specs, flows, checks and YAML for each agent |
| `GET /api/agents/{id}/summary` | per-agent rollup: fail rate per check, metrics, score histogram, most skipped steps |
| `GET /api/calls?agent=&check=&q=` | call explorer |
| `GET /api/calls/{id}` | one scored call with turn-level findings and planted ground truth |
| `POST /api/score` | score a call without storing it; optional `spec_yaml` scores it against an edited spec |
| `POST /api/generate` | make a synthetic call with the faults you ask for |
| `POST /api/calls` | score and store (self-hosted with `CALLQA_DB` only; the hosted demo returns 503) |
| `GET /api/benchmark` | precision/recall against planted faults |

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
- `pytest -q`: 26 tests pass (each check and exemption, spec validation, every API endpoint including edited-spec scoring and fault generation, read-only vs database mode, and a benchmark floor).
- `npm run build`: TypeScript type-check and production build pass.
- Clicked through by hand in a browser, locally (uvicorn) and on the Vercel deployment: overview, call explorer and filters, call detail, Playground (generate → score), benchmark; phone width (375 px) checked for sideways scrolling.
- The live API was checked with curl: health, summary, benchmark, explorer, and a generate-then-score round trip.
- No frontend unit tests yet.

## Likely interview questions

1. *Why rules instead of an LLM judge?* Rules are cheap, deterministic and explainable per turn, and they give a baseline. An LLM judge is the next step for paraphrases, but it needs its own evaluation against labels like these.
2. *How do you avoid counting a restart after an interruption as a repeat?* The earlier turn is marked `interrupted`; if it is the agent's previous turn and the new turn contains most of its tokens, it's exempt.
3. *Why does the dashboard differ per agent?* Each spec enables its own checks and weights, so a Hinglish agent never shows a language failure rate that would mean nothing for it.
4. *What would break first on real calls?* Step matching on paraphrases and STT errors, then question counting on unpunctuated output.
5. *Why does the hosted demo keep data in memory?* Serverless functions have no lasting disk. Scoring is pure and fast, so the demo regenerates its 120 calls at start-up and the Playground is stateless; persistence is a config switch (`CALLQA_DB`) for self-hosting.
6. *How would you scale this to a million calls a day?* The checks are pure functions over a transcript, so run them in a queue consumer (one call per message), write findings in batches, and pre-aggregate the per-agent rollups instead of computing them on read.
7. *Why is the score so coarse?* A per-check pass/fail with weights is easy to explain to an ops team. Per-finding penalties are possible but harder to reason about.
