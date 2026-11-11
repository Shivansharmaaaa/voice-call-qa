import { useEffect, useState } from "react";
import { Agent, api, Benchmark, CHECK_LABEL } from "../api";
import { href } from "../router";

const REPO = "https://github.com/Shivansharmaaaa/voice-call-qa";

export function Agents() {
  const [agents, setAgents] = useState<Agent[]>([]);
  useEffect(() => { api.agents().then(setAgents).catch(() => {}); }, []);
  return (
    <div className="page">
      <h1>Agent specs</h1>
      <p className="lead">Each agent writes down what a good call means for it. The checks, weights and thresholds come from here, so two agents can be judged differently on the same behaviour.</p>
      {agents.map((a) => (
        <section key={a.id} className="card">
          <h2>{a.name}</h2>
          <p className="muted small">persona <b>{a.persona}</b>{a.allowed_english.length > 0 && <> · English words allowed: {a.allowed_english.join(", ")}</>}</p>
          <div className="two">
            <div>
              <h4>Call flow</h4>
              <ol className="flow">
                {a.flow.map((s) => (
                  <li key={s.id}><b>{s.id}</b>{!s.required && <span className="muted small"> (optional)</span>}
                    <div className="muted small">matches: {s.match.join(" · ")}</div></li>
                ))}
              </ol>
              <h4>Checks</h4>
              <ul className="plain">
                {a.checks.map((c) => (
                  <li key={c.name} className="small">
                    <span className={`dot ${c.enabled ? "dot-ok" : "dot-off"}`} /> {CHECK_LABEL[c.name] ?? c.name}{" "}
                    <span className="muted">{c.enabled ? `weight ${c.weight}` : "off for this agent"}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h4>Spec (YAML)</h4>
              <pre className="yaml">{a.yaml}</pre>
            </div>
          </div>
        </section>
      ))}
      <p><a className="btn" href={href("/playground")}>Edit a spec in the playground</a></p>
    </div>
  );
}

const NAME: Record<string, string> = {
  "coverage:skipped_step": "Skipped step",
  "early_exit:early_exit": "Agent hung up early",
  "language:off_persona": "Off-persona turn",
  "latency:slow_response": "Slow response",
  "one_question:multiple_questions": "Two questions in a turn",
  "order:out_of_order": "Steps out of order",
  "repeats:repeat": "Unexplained repeat",
};
const MNF: Record<string, string> = {
  restart: "Restart after the caller interrupted",
  caller_asked: "Repeat the caller asked for",
  compliance: "Repeated compliance line",
  hangup: "Caller hung up early",
};

export function BenchmarkPage() {
  const [b, setB] = useState<Benchmark | null>(null);
  useEffect(() => { api.benchmark().then(setB).catch(() => {}); }, []);
  return (
    <div className="page">
      <h1>How accurate are the checks?</h1>
      <p className="lead">Every synthetic call starts clean, then faults are planted on purpose and recorded. The checker is scored against that record.</p>
      {!b && <div className="card muted">Loading…</div>}
      {b && (
        <>
          <div className="card table-wrap">
            <h3>Should be flagged ({b.calls} calls)</h3>
            <table className="calls">
              <thead><tr><th>Finding</th><th>Caught</th><th>False alarms</th><th>Missed</th><th>Precision</th><th>Recall</th></tr></thead>
              <tbody>
                {Object.entries(b.per_finding).map(([k, r]) => (
                  <tr key={k}><td>{NAME[k] ?? k}</td><td>{r.tp}</td><td>{r.fp}</td><td>{r.fn}</td>
                    <td>{r.precision.toFixed(2)}</td><td className={r.recall < 1 ? "warn-text" : ""}>{r.recall.toFixed(2)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card">
            <h3>Must NOT be flagged</h3>
            <ul className="plain">
              {Object.entries(b.must_not_flag).map(([k, v]) => (
                <li key={k}><span className={`dot ${v.wrongly_flagged ? "dot-bad" : "dot-ok"}`} /> {MNF[k] ?? k}: planted {v.planted}, wrongly flagged <b>{v.wrongly_flagged}</b></li>
              ))}
            </ul>
          </div>
          <div className="card note">
            <h3>Read these numbers carefully</h3>
            <p>The calls come from the same templates the match phrases were written for, so this shows the rules do what they claim. It is not a measure of real-world accuracy: real calls have paraphrases, accents and STT errors.</p>
            <p>The missed double questions are in transcripts whose punctuation was stripped. Counting question marks can't see them, so the checker raises a "no punctuation" warning on those calls instead of passing them silently.</p>
          </div>
        </>
      )}
    </div>
  );
}

export function About() {
  return (
    <div className="page narrow">
      <h1>About</h1>
      <p className="lead">Voice Call QA is a small, explainable quality layer for voice agents. It is rule-based on purpose: every finding points at a turn and says why.</p>
      <div className="card">
        <h3>Why "what counts" is per agent</h3>
        <p>A metric like repeat rate is easy to compute and hard to define. If the caller interrupts and the agent restarts, that is not a repeat. If the caller says "phir se boliye", repeating is correct. A compliance line may have to be said twice. And switching between Hindi and English is natural for a Hinglish recruiter but a mistake for a Hindi-only agent. So each agent's spec decides which checks run, their weights and their thresholds.</p>
      </div>
      <div className="card">
        <h3>How it's built</h3>
        <ul>
          <li>Python rule engine: 7 checks, each a pure function over a transcript.</li>
          <li>FastAPI service; the hosted demo runs as a serverless function and scores 120 synthetic calls in memory.</li>
          <li>Optional SQLAlchemy storage (SQLite or Postgres) when self-hosted.</li>
          <li>React + TypeScript front end.</li>
          <li>Synthetic call generator with planted faults, used for the benchmark and the playground. 26 automated tests.</li>
        </ul>
      </div>
      <div className="card">
        <h3>Limits</h3>
        <ul>
          <li>Phrase matching misses paraphrased questions. An embedding or LLM judge is the natural next step, measured against the same labels.</li>
          <li>Transcripts only, no audio. Latency comes from timestamps.</li>
          <li>Language detection covers Hindi and English only.</li>
          <li>Synthetic data only; never tested on real calls.</li>
        </ul>
      </div>
      <div className="card note">
        <p>Independent demo built by Shivansh Sharma as a sample for Hunar.AI's domain (conversational voice agents for frontline hiring). Not affiliated with or endorsed by Hunar.AI. The company name in the calls ("Kaam Connect") is made up.</p>
        <p><a href={REPO} target="_blank" rel="noreferrer">Source code and README on GitHub →</a></p>
      </div>
    </div>
  );
}
