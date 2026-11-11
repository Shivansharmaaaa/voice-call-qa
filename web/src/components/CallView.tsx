import { CHECK_LABEL, Finding, ScoredCall, scoreTone } from "../api";

const SEV_LABEL = { fail: "Fail", warn: "Warning", info: "Not counted" } as const;

function Badge({ f }: { f: Finding }) {
  return (
    <div className={`finding sev-${f.severity}`}>
      <span className="finding-tag">{SEV_LABEL[f.severity]}</span>
      <span>
        <b>{CHECK_LABEL[f.check] ?? f.check}</b> · {f.detail}
      </span>
    </div>
  );
}

export function ScoreRing({ score, size = 84 }: { score: number; size?: number }) {
  const r = (size - 10) / 2;
  const c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className={`ring tone-${scoreTone(score)}`} role="img"
      aria-label={`score ${score} of 100`}>
      <circle cx={size / 2} cy={size / 2} r={r} className="ring-bg" />
      <circle cx={size / 2} cy={size / 2} r={r} className="ring-fg" strokeDasharray={`${(c * score) / 100} ${c}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle">{Math.round(score)}</text>
    </svg>
  );
}

function plantedMatch(label: string, found: Set<string>) {
  return found.has(label);
}

export function CallView({ call }: { call: ScoredCall }) {
  const byTurn = new Map<number, Finding[]>();
  const callLevel: Finding[] = [];
  for (const f of call.findings) {
    if (f.turn === null) callLevel.push(f);
    else byTurn.set(f.turn, [...(byTurn.get(f.turn) ?? []), f]);
  }
  const found = new Set(call.findings.filter((f) => f.severity === "fail").map((f) => `${f.check}:${f.code}`));
  const fails = call.findings.filter((f) => f.severity === "fail").length;

  return (
    <div className="callview">
      <div className="card call-head">
        <ScoreRing score={call.score} />
        <div className="call-head-text">
          <div className="muted small">{call.agent_id} · ended by {call.ended_by === "user" ? "the caller" : call.ended_by}</div>
          <h2 className="mono">{call.id}</h2>
          <div className="muted">
            {call.turns.length} turns · {fails === 0 ? "no failures" : `${fails} failing finding${fails > 1 ? "s" : ""}`}
          </div>
        </div>
      </div>

      <div className="callgrid">
        <div className="card transcript">
          <h3>Transcript</h3>
          {call.turns.map((t, i) => {
            const prev = call.turns[i - 1];
            const gap = prev ? Math.max(0, t.start - prev.end) : 0;
            const fs = byTurn.get(i) ?? [];
            const slow = fs.some((f) => f.code === "slow_response");
            return (
              <div key={i}>
                {i > 0 && (gap >= 1.5 || slow) && (
                  <div className={`gap ${slow ? "gap-bad" : ""}`}>{gap.toFixed(1)} s silence</div>
                )}
                <div className={`turn turn-${t.speaker}`}>
                  <div className="turn-meta">
                    <span>#{i}</span>
                    <span>{t.speaker === "agent" ? "Agent" : "Caller"}</span>
                    <span>{t.start.toFixed(1)}s</span>
                    {t.interrupted && <span className="pill pill-warn">cut off</span>}
                  </div>
                  <div className={`bubble ${fs.some((f) => f.severity === "fail") ? "bubble-fail" : ""}`}>{t.text}</div>
                  {fs.map((f, k) => <Badge key={k} f={f} />)}
                </div>
              </div>
            );
          })}
        </div>

        <div className="side">
          <div className="card">
            <h3>Score breakdown</h3>
            <p className="muted small">Each check this agent runs either passes or fails, weighted by the agent's spec.</p>
            {call.breakdown.map((b) => (
              <div key={b.check} className="brow">
                <span className={`dot ${b.passed ? "dot-ok" : "dot-bad"}`} />
                <span className="grow">{CHECK_LABEL[b.check] ?? b.check}</span>
                <span className="muted small">weight {b.weight}</span>
              </div>
            ))}
          </div>

          {callLevel.length > 0 && (
            <div className="card">
              <h3>Call-level findings</h3>
              {callLevel.map((f, k) => <Badge key={k} f={f} />)}
            </div>
          )}

          <div className="card">
            <h3>Metrics</h3>
            <dl className="metrics">
              {Object.entries(call.metrics).map(([k, v]) => (
                <div key={k}>
                  <dt>{k.replace(/_/g, " ")}</dt>
                  <dd>{k.includes("share") || k.includes("rate") || k.includes("coverage") || k.includes("punctuated") ? `${Math.round(v * 100)}%` : v}</dd>
                </div>
              ))}
            </dl>
          </div>

          {call.planted && (
            <div className="card">
              <h3>What was planted</h3>
              <p className="muted small">Ground truth from the generator, so you can check the checker.</p>
              {call.planted.length === 0 && <p>Nothing: a clean call.</p>}
              <ul className="plain">
                {call.planted.map((p) => <li key={p} className="mono small">{p}</li>)}
              </ul>
              {call.labels && call.labels.length > 0 && (
                <>
                  <h4>Expected failures</h4>
                  <ul className="plain">
                    {call.labels.map((l) => (
                      <li key={l} className="small">
                        <span className={`dot ${plantedMatch(l, found) ? "dot-ok" : "dot-bad"}`} /> {l}{" "}
                        <span className="muted">{plantedMatch(l, found) ? "caught" : "missed"}</span>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
