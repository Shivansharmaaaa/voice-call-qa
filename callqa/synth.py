"""Synthetic screening calls with planted faults and ground-truth labels.

Real call recordings are private, so every call here is generated. Each call starts
from a clean script, then faults are planted on purpose (a skipped step, a repeated
question, an English turn in a Hindi call...). The labels record exactly what was
planted, so the checker can be measured against them.

Some changes are planted that must NOT be flagged (a restart after the caller
interrupts, a repeat the caller asked for, a repeated compliance line, the caller
hanging up). They test false positives.

The company name in the scripts ("Kaam Connect") is made up.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .models import Call, Turn

SCRIPTS = {
    "field-sales-screener": {
        "consent_text": "Yeh call quality ke liye record ho rahi hai, theek hai?",
        "repeat_request": ["Sorry, phir se boliye?", "Kya bola aapne? Samjha nahi.", "Ek baar dobara boliye?"],
        "interjection": ["Haan haan, boliye", "Ji ji", "Ek second, haan boliye"],
        "steps": [
            ("greet", ["Namaste, main Kaam Connect se Priya bol rahi hoon.", "Namaste ji, main Kaam Connect se bol rahi hoon."],
             ["Haan ji, boliye", "Namaste"]),
            ("consent", ["Yeh call quality ke liye record ho rahi hai, theek hai?"], ["Haan theek hai", "Ji, chalega"]),
            ("role_interest", ["Aapne field sales ki job ke liye apply kiya tha, kya aap abhi bhi interested hain?",
                               "Field sales wali job ke liye kya aap abhi bhi interested hain?"],
             ["Haan, interested hoon", "Ji haan, abhi bhi dhoondh raha hoon"]),
            ("location", ["Aap abhi kis area mein rehte hain?", "Aapka ghar kis area mein hai?"],
             ["Andheri East mein", "Thane West mein rehta hoon"]),
            ("experience", ["Aapko sales mein kitne saal ka experience hai?", "Sales ka experience kitna hai aapka?"],
             ["Do saal", "Ek saal, ek retail store mein"]),
            ("notice_period", ["Aapka notice period kitna hai?", "Current job mein notice period kitne din ka hai?"],
             ["Ek mahina", "Pandrah din"]),
            ("salary", ["Aapki current salary kitni hai?", "Abhi aapko salary kitni milti hai?"],
             ["Pandrah hazaar", "Athaara hazaar mahina"]),
            ("interview_slot", ["Kal subah gyarah baje interview ka slot chalega?",
                                "Parso dopahar teen baje interview ka slot theek rahega?"],
             ["Haan chalega", "Ji, theek hai"]),
            ("close", ["Dhanyavaad, aapko SMS par saari details mil jayengi.", "Dhanyavaad ji, details SMS par aa jayengi."],
             ["Theek hai, thank you"]),
        ],
        "english": {},
    },
    "rider-onboarding-hindi": {
        "consent_text": "यह कॉल गुणवत्ता के लिए रिकॉर्ड की जा रही है, ठीक है?",
        "repeat_request": ["माफ़ कीजिए, फिर से बोलिए?", "क्या कहा आपने? समझ नहीं आया।", "दोबारा बोलिए?"],
        "interjection": ["हाँ हाँ, बोलिए", "जी जी", "एक सेकंड, हाँ बोलिए"],
        "steps": [
            ("greet", ["नमस्ते, मैं काम कनेक्ट से राहुल बोल रहा हूँ।", "नमस्ते जी, मैं काम कनेक्ट से बोल रहा हूँ।"],
             ["हाँ जी, बोलिए", "नमस्ते"]),
            ("consent", ["यह कॉल गुणवत्ता के लिए रिकॉर्ड की जा रही है, ठीक है?"], ["हाँ ठीक है", "जी, ठीक है"]),
            ("vehicle", ["क्या आपके पास अपनी bike है?", "delivery के लिए क्या अपनी bike है आपके पास?"],
             ["हाँ, मेरे पास bike है", "जी, अपनी bike है"]),
            ("licence", ["क्या आपके पास driving licence है?", "आपका driving licence बना हुआ है क्या?"],
             ["हाँ, licence है", "जी, पिछले साल बना"]),
            ("area", ["आप किस इलाके में delivery करना चाहेंगे?", "आप शहर के किस इलाके में काम करना पसंद करेंगे?"],
             ["करोल बाग के आसपास", "लक्ष्मी नगर में"]),
            ("availability", ["आप हफ्ते में कितने दिन काम कर सकते हैं?", "हफ्ते में आप कितने दिन आ पाएंगे?"],
             ["हफ्ते में छह दिन", "पाँच दिन"]),
            ("app_link", ["मैं आपको app का link भेज रहा हूँ, उसमें OTP डालिए।"], ["ठीक है"]),
            ("close", ["धन्यवाद, आपका दिन शुभ हो।", "धन्यवाद जी, जल्द बात होगी।"], ["धन्यवाद"]),
        ],
        "english": {
            "vehicle": "Do you have your own bike for the deliveries?",
            "licence": "Could you please confirm that your driving licence is valid?",
            "area": "Which part of the city would you prefer to work in?",
            "availability": "How many days every week are you available to work?",
        },
    },
}


@dataclass
class Sample:
    call: Call
    labels: list[str]  # "check:code" that SHOULD be flagged as fail
    planted: list[str] = field(default_factory=list)  # everything planted, including must-not-flag cases


def _turns_from_lines(lines: list[tuple[str, str, bool]], rng: random.Random, slow_at: int | None) -> list[Turn]:
    turns, t = [], 0.0
    for idx, (speaker, text, interrupted) in enumerate(lines):
        if idx:
            prev_speaker = lines[idx - 1][0]
            if speaker == "agent" and prev_speaker == "user":
                gap = rng.uniform(3.0, 4.5) if idx == slow_at else rng.uniform(0.4, 1.4)
            else:
                gap = rng.uniform(0.2, 0.9)
            t += gap
        dur = 0.4 + 0.3 * len(text.split())
        if interrupted:
            dur *= 0.6
        turns.append(Turn(speaker=speaker, text=text, start=round(t, 2), end=round(t + dur, 2), interrupted=interrupted))
        t += dur
    return turns


def make_call(agent_id: str, n: int, rng: random.Random) -> Sample:
    sc = SCRIPTS[agent_id]
    steps = [(sid, rng.choice(a), rng.choice(u)) for sid, a, u in sc["steps"]]
    labels: list[str] = []
    planted: list[str] = []
    ended_by = "agent"
    middle = list(range(2, len(steps) - 1))  # never touch greet, consent or close

    # 1. One structural change at most.
    structural = rng.choices(["none", "skip", "swap", "early_exit", "user_hangup"], [0.4, 0.15, 0.15, 0.15, 0.15])[0]
    if structural == "skip":
        i = rng.choice(middle[:-1])
        if sc["steps"][i][0] != "app_link":
            labels.append("coverage:skipped_step")
        planted.append(f"skip:{steps[i][0]}")
        steps.pop(i)
    elif structural == "swap":
        i = rng.choice(middle[:-1])
        steps[i], steps[i + 1] = steps[i + 1], steps[i]
        labels.append("order:out_of_order")
        planted.append(f"swap:{steps[i + 1][0]}<->{steps[i][0]}")
    elif structural in ("early_exit", "user_hangup"):
        k = rng.choice(middle[1:-1])
        steps = steps[: k + 1]
        if structural == "early_exit":
            labels.append("early_exit:early_exit")
        else:
            ended_by = "user"
        planted.append(f"{structural}:after_{steps[-1][0]}")

    # 2. Turn-level changes. Each picks a different middle step that is still in the call.
    free = [i for i in range(2, len(steps)) if steps[i][0] != "close"]
    rng.shuffle(free)
    lines: list[tuple[str, str, bool]] = []
    plan: dict[int, str] = {}
    for kind, p in [("double", 0.2), ("repeat", 0.2), ("restart", 0.2), ("asked_repeat", 0.2),
                    ("english", 0.25 if sc["english"] else 0.0)]:
        if free and rng.random() < p:
            i = free.pop()
            if kind == "double" and (i + 1 >= len(steps) or steps[i + 1][0] == "close" or (i + 1) in plan
                                     or "?" not in steps[i][1] or "?" not in steps[i + 1][1]):
                continue
            if kind == "english" and steps[i][0] not in sc["english"]:
                continue
            plan[i] = kind
            if kind == "double" and (i + 1) in free:
                free.remove(i + 1)

    skip_next = False
    for i, (sid, a, u) in enumerate(steps):
        if skip_next:
            skip_next = False
            continue
        kind = plan.get(i)
        if kind == "double":
            nsid, na, nu = steps[i + 1]
            lines += [("agent", f"{a} {na}", False), ("user", f"{u}, {nu}", False)]
            labels.append("one_question:multiple_questions")
            planted.append(f"double:{sid}+{nsid}")
            skip_next = True
        elif kind == "repeat":
            lines += [("agent", a, False), ("user", u, False), ("agent", a, False), ("user", u, False)]
            labels.append("repeats:repeat")
            planted.append(f"repeat:{sid}")
        elif kind == "restart":
            words = a.split()
            cut = " ".join(words[: max(2, int(len(words) * 0.55))])
            lines += [("agent", cut, True), ("user", rng.choice(sc["interjection"]), False),
                      ("agent", a, False), ("user", u, False)]
            planted.append(f"restart_after_interrupt:{sid} (must not flag)")
        elif kind == "asked_repeat":
            lines += [("agent", a, False), ("user", rng.choice(sc["repeat_request"]), False),
                      ("agent", a, False), ("user", u, False)]
            planted.append(f"caller_asked_repeat:{sid} (must not flag)")
        elif kind == "english":
            lines += [("agent", sc["english"][sid], False), ("user", u, False)]
            labels.append("language:off_persona")
            planted.append(f"english_turn:{sid}")
        else:
            lines += [("agent", a, False)]
            if sid != "close":
                lines += [("user", u, False)]

    # 3. Repeated compliance line later in the call (must not flag).
    if len(lines) > 8 and rng.random() < 0.15:
        pos = len(lines) - 1 if lines[-1][0] == "agent" else len(lines)  # just before the closing line
        lines[pos:pos] = [("agent", sc["consent_text"], False), ("user", sc["steps"][1][2][0], False)]
        planted.append("compliance_repeat (must not flag)")

    # 4. One slow agent response.
    slow_at = None
    if rng.random() < 0.2:
        options = [i for i in range(1, len(lines)) if lines[i][0] == "agent" and lines[i - 1][0] == "user"]
        if options:
            slow_at = rng.choice(options)
            labels.append("latency:slow_response")
            planted.append(f"slow_response:line_{slow_at}")

    turns = _turns_from_lines(lines, rng, slow_at)

    # 5. STT noise: some transcripts arrive with no punctuation at all.
    if rng.random() < 0.12:
        for t in turns:
            t.text = re.sub(r"[?？.,!।]", "", t.text)
        planted.append("no_punctuation")

    return Sample(Call(id=f"{agent_id}-{n:03d}", agent_id=agent_id, turns=turns, ended_by=ended_by),
                  sorted(set(labels)), planted)


def generate(n_per_agent: int = 60, seed: int = 7) -> list[Sample]:
    rng = random.Random(seed)
    return [make_call(agent_id, n, rng) for agent_id in SCRIPTS for n in range(n_per_agent)]


def save(samples: list[Sample], path: str | Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps({"call": asdict(s.call), "labels": s.labels, "planted": s.planted},
                               ensure_ascii=False) + "\n")


def call_from_dict(d: dict) -> Call:
    return Call(id=d["id"], agent_id=d["agent_id"], ended_by=d.get("ended_by", "agent"),
                turns=[Turn(**t) for t in d["turns"]])
