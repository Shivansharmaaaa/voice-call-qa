import { useEffect, useState } from "react";
import { Agent, api, CHECK_LABEL, Summary } from "../api";
import { href } from "../router";
import { ScoreRing } from "../components/CallView";

function Bars({ s }: { s: Summary }) {
  return (
    <div className="bars">
      {Object.entries(s.fail_rate_by_check).map(([check, rate]) => (
        <a key={check} className="bar-row" href={href("/calls", { agent: s.agent_id, check })}>
          <span className="bar-label">{CHECK_LABEL[check] ?? check}</span>
          <span className="bar-track">
            <span className="bar-fill" style={{ width: `${Math.max(rate * 100, 1)}%` }} />
          </span>
          <span className="bar-val">{Math.round(rate * 100)}%</span>
        </a>
      ))}
    </div>
  );
}

function Histogram({ hist }: { hist: number[] }) {
  const max = Math.max(...hist, 1);
  return (
    <div className="hist" aria-label="score distribution">
      {hist.map((n, i) => (
        <div key={i} className="hist-col" title={`${i * 10}-${i * 10 + 9}: ${n} calls`}>
          <div className="hist-bar" style={{ height: `${(n / max) * 100}%` }} />
          <span>{i * 10}</span>
        </div>
      ))}
    </div>
  );
}

export function Overview() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [sums, setSums] = useState<Summary[]>([]);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.agents()
      .then(async (a) => {
        setAgents(a);
        setSums(await Promise.all(a.map((x) => api.summary(x.id))));
      })
      .catch((e) => setErr(String(e.message ?? e)));
  }, []);

  return (
    <div className="page">
      <section className="hero">
        <h1>Is your voice agent actually following the script?</h1>
        <p>
          Voice Call QA reads call transcripts and checks what matters for <em>that</em> agent: skipped screening
          questions, unexplained repeats, persona breaks, early hang-ups and slow replies. A repeat after the caller
          interrupts, or one the caller asked for, is not held against the agent.
        </p>
        <div className="hero-cta">
          <a className="btn btn-primary" href={href("/playground")}>Try the playground</a>
          <a className="btn" href={href("/calls")}>Browse 120 calls</a>
        </div>
        <p className="muted small">All calls here are synthetic, with faults planted on purpose so the checker can be measured.</p>
      </section>

      {err && <div className="card error">Could not load data: {err}</div>}
      {!err && sums.length === 0 && <div className="card muted">Loading…</div>}

      <div className="agent-grid">
        {sums.map((s) => {
          const agent = agents.find((a) => a.id === s.agent_id);
          const off = agent?.checks.filter((c) => !c.enabled).map((c) => CHECK_LABEL[c.name] ?? c.name) ?? [];
          return (
            <section key={s.agent_id} className="card agent-card">
              <div className="agent-head">
                <ScoreRing score={s.mean_score ?? 0} size={72} />
                <div>
                  <h2>{s.name}</h2>
                  <div className="muted small">
                    persona <b>{s.persona}</b> · {s.calls} calls · {s.clean_calls} clean
                  </div>
                </div>
              </div>
              <h4>Calls failing each check</h4>
              <Bars s={s} />
              {off.length > 0 && <p className="muted small">Not checked for this agent: {off.join(", ")}.</p>}
              <div className="two">
                <div>
                  <h4>Score distribution</h4>
                  <Histogram hist={s.score_histogram} />
                </div>
                <div>
                  <h4>Most skipped steps</h4>
                  <div className="chips">
                    {Object.entries(s.most_skipped_steps).map(([k, v]) => <span key={k} className="chip">{k} · {v}</span>)}
                    {Object.keys(s.most_skipped_steps).length === 0 && <span className="muted small">none</span>}
                  </div>
                  <h4>Lowest scores</h4>
                  <ul className="plain">
                    {s.worst_calls.map((c) => (
                      <li key={c.id}><a className="mono small" href={href(`/call/${c.id}`)}>{c.id}</a> <span className="muted small">{c.score}</span></li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}
