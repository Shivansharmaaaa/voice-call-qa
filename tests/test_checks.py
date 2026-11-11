"""Hand-written calls, one behaviour per test, so each rule is pinned down explicitly."""
from pathlib import Path

import pytest

from callqa import Call, Turn, load_spec_file, score_call

AGENTS = Path(__file__).resolve().parent.parent / "agents"
SALES = load_spec_file(AGENTS / "field_sales_screener.yaml")
RIDER = load_spec_file(AGENTS / "rider_onboarding_hindi.yaml")

SALES_SCRIPT = [
    ("agent", "Namaste, main Kaam Connect se Priya bol rahi hoon."), ("user", "Haan ji"),
    ("agent", "Yeh call quality ke liye record ho rahi hai, theek hai?"), ("user", "Haan"),
    ("agent", "Aapne field sales ki job ke liye apply kiya tha, kya aap interested hain?"), ("user", "Haan"),
    ("agent", "Aap abhi kis area mein rehte hain?"), ("user", "Andheri"),
    ("agent", "Aapko sales mein kitne saal ka experience hai?"), ("user", "Do saal"),
    ("agent", "Aapka notice period kitna hai?"), ("user", "Ek mahina"),
    ("agent", "Aapki current salary kitni hai?"), ("user", "Pandrah hazaar"),
    ("agent", "Kal subah gyarah baje interview ka slot chalega?"), ("user", "Haan"),
    ("agent", "Dhanyavaad, details SMS par aa jayengi."),
]


def build(lines, agent="field-sales-screener", ended_by="agent", gap=0.8, interrupted=()):
    turns, t = [], 0.0
    for i, (speaker, text) in enumerate(lines):
        turns.append(Turn(speaker, text, round(t, 2), round(t + 2.0, 2), interrupted=i in interrupted))
        t += 2.0 + gap
    return Call(id="t", agent_id=agent, turns=turns, ended_by=ended_by)


def codes(report, severity="fail"):
    return {f"{f.check}:{f.code}" for f in report.findings if f.severity == severity}


def test_clean_call_scores_100():
    r = score_call(build(SALES_SCRIPT), SALES)
    assert codes(r) == set()
    assert r.score == 100.0
    assert r.metrics["step_coverage"] == 1.0


def test_skipped_step_is_flagged_and_lowers_score():
    lines = [l for l in SALES_SCRIPT if "notice period" not in l[1]]
    lines.remove(("user", "Ek mahina"))
    r = score_call(build(lines), SALES)
    assert "coverage:skipped_step" in codes(r)
    assert r.score < 100


def test_steps_out_of_order():
    lines = list(SALES_SCRIPT)
    lines[10:12], lines[12:14] = lines[12:14], lines[10:12]  # salary before notice period
    assert "order:out_of_order" in codes(score_call(build(lines), SALES))


def test_agent_hanging_up_early_fails_but_caller_hanging_up_does_not():
    cut = SALES_SCRIPT[:10]
    assert "early_exit:early_exit" in codes(score_call(build(cut, ended_by="agent"), SALES))
    r = score_call(build(cut, ended_by="user"), SALES)
    assert "early_exit:early_exit" not in codes(r)
    assert "early_exit:ended_by_other" in codes(r, "info")


def test_two_questions_in_one_turn():
    lines = list(SALES_SCRIPT)
    lines[10] = ("agent", "Aapka notice period kitna hai? Aur current salary kitni hai?")
    assert "one_question:multiple_questions" in codes(score_call(build(lines), SALES))


def test_missing_punctuation_is_warned_not_silently_passed():
    lines = [(s, t.replace("?", "").replace(",", "").replace(".", "")) for s, t in SALES_SCRIPT]
    r = score_call(build(lines), SALES)
    assert "one_question:no_punctuation" in codes(r, "warn")


def test_plain_repeat_is_counted():
    lines = SALES_SCRIPT[:12] + [("agent", "Aapka notice period kitna hai?"), ("user", "Bataya na, ek mahina")] + SALES_SCRIPT[12:]
    r = score_call(build(lines), SALES)
    assert "repeats:repeat" in codes(r)
    assert r.metrics["repeat_rate"] > 0


def test_repeat_after_caller_asks_is_not_counted():
    lines = SALES_SCRIPT[:11] + [("user", "Sorry, phir se boliye?"), ("agent", "Aapka notice period kitna hai?"),
                                 ("user", "Ek mahina")] + SALES_SCRIPT[12:]
    r = score_call(build(lines), SALES)
    assert "repeats:repeat" not in codes(r)
    assert "repeats:repeat_exempt" in codes(r, "info")


def test_restart_after_interruption_is_not_counted():
    lines = SALES_SCRIPT[:4] + [("agent", "Aapne field sales ki job"), ("user", "Haan haan, boliye")] + SALES_SCRIPT[4:]
    r = score_call(build(lines, interrupted={4}), SALES)
    assert "repeats:repeat" not in codes(r)


def test_repeated_compliance_line_is_not_counted():
    lines = SALES_SCRIPT[:-1] + [("agent", "Yeh call quality ke liye record ho rahi hai, theek hai?"), ("user", "Haan")] + SALES_SCRIPT[-1:]
    assert "repeats:repeat" not in codes(score_call(build(lines), SALES))


def test_short_acknowledgements_are_never_repeats():
    lines = SALES_SCRIPT[:4] + [("agent", "Theek hai ji"), ("user", "Haan"), ("agent", "Theek hai ji"), ("user", "Haan")] + SALES_SCRIPT[4:]
    assert "repeats:repeat" not in codes(score_call(build(lines), SALES))


def test_slow_response():
    lines = SALES_SCRIPT
    call = build(lines)
    call.turns[6].start += 3.0  # long silence before the agent's 4th turn
    call.turns[6].end += 3.0
    assert "latency:slow_response" in codes(score_call(call, SALES))


RIDER_SCRIPT = [
    ("agent", "नमस्ते, मैं काम कनेक्ट से राहुल बोल रहा हूँ।"), ("user", "हाँ जी"),
    ("agent", "यह कॉल गुणवत्ता के लिए रिकॉर्ड की जा रही है, ठीक है?"), ("user", "हाँ"),
    ("agent", "क्या आपके पास अपनी bike है?"), ("user", "हाँ"),
    ("agent", "क्या आपके पास driving licence है?"), ("user", "हाँ"),
    ("agent", "आप किस इलाके में delivery करना चाहेंगे?"), ("user", "करोल बाग"),
    ("agent", "आप हफ्ते में कितने दिन काम कर सकते हैं?"), ("user", "छह दिन"),
    ("agent", "धन्यवाद, आपका दिन शुभ हो।"),
]


def test_hindi_persona_allows_listed_english_words():
    r = score_call(build(RIDER_SCRIPT, agent="rider-onboarding-hindi"), RIDER)
    assert codes(r) == set()


def test_hindi_persona_flags_an_english_turn_but_still_counts_the_step():
    lines = list(RIDER_SCRIPT)
    lines[8] = ("agent", "Which part of the city would you prefer to work in?")
    r = score_call(build(lines, agent="rider-onboarding-hindi"), RIDER)
    assert "language:off_persona" in codes(r)
    assert "coverage:skipped_step" not in codes(r)


def test_spec_and_call_must_match():
    with pytest.raises(ValueError):
        score_call(build(SALES_SCRIPT), RIDER)


def test_two_steps_swapped_inside_one_turn():
    lines = list(SALES_SCRIPT)
    # salary asked before notice period, in a single turn
    lines[10:14] = [("agent", "Aapki current salary kitni hai? Aur aapka notice period kitna hai?"), ("user", "Pandrah hazaar, ek mahina")]
    r = score_call(build(lines), SALES)
    order = [f for f in r.findings if f.code == "out_of_order"]
    assert order and order[0].step == "salary" and "same turn" in order[0].detail  # salary came too early


def test_flow_findings_carry_the_step_id():
    lines = [l for l in SALES_SCRIPT if "notice period" not in l[1]]
    lines.remove(("user", "Ek mahina"))
    skipped = [f for f in score_call(build(lines), SALES).findings if f.code == "skipped_step"]
    assert [f.step for f in skipped] == ["notice_period"]
