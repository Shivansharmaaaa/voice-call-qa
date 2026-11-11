import { useEffect, useMemo, useState } from "react";
import { Agent, api, CallInput, CHECK_LABEL, EndedBy, Fault, Matcher, MATCHER_LABEL, ScoredCall, Turn } from "../api";
import { CallView } from "../components/CallView";
import { href } from "../router";

const SAVE_KEY = "vcqa.saved.v1";

interface Saved {
  savedAt: string;
  result: ScoredCall;
}

function loadSaved(): Saved[] {
  try {
    return JSON.parse(localStorage.getItem(SAVE_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function storeSaved(list: Saved[]) {
  try {
    localStorage.setItem(SAVE_KEY, JSON.stringify(list.slice(0, 20)));
  } catch {
    /* storage blocked: saving is a convenience only */
  }
}

export function Playground({ params }: { params: URLSearchParams }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [faults, setFaults] = useState<Fault[]>([]);
  const [agentId, setAgentId] = useState("");
  const [picked, setPicked] = useState<string[]>(["restart", "repeat"]);
  const [draft, setDraft] = useState<CallInput | null>(null);
  const [truth, setTruth] = useState<{ labels: string[]; planted: string[]; notPlanted: string[] } | null>(null);
  const [dirty, setDirty] = useState(false);
  const [editSpec, setEditSpec] = useState(false);
  const [specYaml, setSpecYaml] = useState("");
  const [result, setResult] = useState<ScoredCall | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<Saved[]>(loadSaved);
  const [paraphrase, setParaphrase] = useState(true);
  const [matcher, setMatcher] = useState<Matcher | "">("");
  const [compare, setCompare] = useState<Record<Matcher, ScoredCall> | null>(null);

  const agent = useMemo(() => agents.find((a) => a.id === agentId), [agents, agentId]);

  useEffect(() => {
    Promise.all([api.agents(), api.faults()]).then(([a, f]) => {
      setAgents(a);
      setFaults(f);
      const from = params.get("from");
      if (from) {
        api.call(from).then((c) => {
          setAgentId(c.agent_id);
          setDraft({ id: `${c.id}-edited`, agent_id: c.agent_id, ended_by: c.ended_by, turns: c.turns });
          setTruth(c.labels ? { labels: c.labels, planted: c.planted ?? [], notPlanted: [] } : null);
          setDirty(false);
          setResult(null);
        });
      } else if (a.length) {
        setAgentId(a[0].id);
      }
    }).catch((e) => setErr(String(e.message ?? e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (agent) setSpecYaml(agent.yaml);
  }, [agent]);

  async function generate() {
    if (!agentId) return;
    setBusy(true);
    setErr("");
    try {
      const g = await api.generate(agentId, picked.filter((f) => agent?.faults.includes(f)), paraphrase);
      setDraft(g.call);
      setTruth({ labels: g.labels, planted: g.planted, notPlanted: g.not_planted });
      setDirty(false);
      setResult(null);
      setCompare(null);
    } catch (e) {
      setErr(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function compareMatchers() {
    if (!draft) return;
    setBusy(true);
    setErr("");
    try {
      const spec = editSpec ? specYaml : undefined;
      const [phrase, ml, hybrid] = await Promise.all(
        (["phrase", "ml", "hybrid"] as Matcher[]).map((m) => api.score(draft, spec, m)),
      );
      setCompare({ phrase, ml, hybrid });
    } catch (e) {
      setErr(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function score() {
    if (!draft) return;
    setBusy(true);
    setErr("");
    try {
      const r = await api.score(draft, editSpec ? specYaml : undefined, matcher || undefined);
      const withTruth = truth && !dirty ? { ...r, labels: truth.labels, planted: truth.planted } : r;
      setResult(withTruth);
      requestAnimationFrame(() => document.getElementById("result")?.scrollIntoView({ behavior: "smooth" }));
    } catch (e) {
      setErr(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  function edit(fn: (turns: Turn[]) => Turn[]) {
    if (!draft) return;
    setDraft({ ...draft, turns: fn(draft.turns.map((t) => ({ ...t }))) });
    setDirty(true);
  }

  function save() {
    if (!result) return;
    const list = [{ savedAt: new Date().toISOString(), result }, ...saved.filter((s) => s.result.id !== result.id)];
    setSaved(list);
    storeSaved(list);
  }

  function remove(id: string) {
    const list = saved.filter((s) => s.result.id !== id);
    setSaved(list);
    storeSaved(list);
  }

  const available = faults.filter((f) => agent?.faults.includes(f.id));

  return (
    <div className="page">
      <h1>Playground</h1>
      <p className="lead">Make a call, break it on purpose, and see what the checker says. Then change the agent's rules and score it again.</p>
      {err && <div className="card error">{err}</div>}

      <div className="card">
        <h3>1. Pick an agent and the faults to plant</h3>
        <div className="row-wrap">
          {agents.map((a) => (
            <button key={a.id} className={`seg ${a.id === agentId ? "seg-on" : ""}`} onClick={() => { setAgentId(a.id); setDraft(null); setResult(null); }}>
              {a.name}
            </button>
          ))}
        </div>
        <div className="fault-grid">
          {available.map((f) => (
            <label key={f.id} className={`fault ${picked.includes(f.id) ? "fault-on" : ""}`}>
              <input type="checkbox" checked={picked.includes(f.id)}
                onChange={(e) => setPicked(e.target.checked ? [...picked, f.id] : picked.filter((x) => x !== f.id))} />
              <span>
                <b>{f.label}</b>
                <span className={`pill ${f.should_flag ? "pill-bad" : "pill-ok"}`}>{f.should_flag ? "should flag" : "must not flag"}</span>
                <span className="muted small block">{f.description}</span>
              </span>
            </label>
          ))}
        </div>
        <p className="muted small">Structural faults (skip, swap, hang-ups) are exclusive: the first one ticked is used.</p>
        <label className="fault fault-wide">
          <input type="checkbox" checked={paraphrase} onChange={(e) => setParaphrase(e.target.checked)} />
          <span>
            <b>Use paraphrased agent wording</b>
            <span className="muted small block">Agent lines come from a held-out set the model never trained on and the rule phrases don't
              cover, e.g. "Abhi aap kidhar stay kar rahe ho?" instead of "Aap kis area mein rehte hain?". This is where rules break.</span>
          </span>
        </label>
        <button className="btn btn-primary" onClick={generate} disabled={busy || !agentId}>Generate a call</button>
      </div>

      {draft && (
        <div className="card">
          <h3>2. Edit the transcript (optional)</h3>
          {truth && (
            <p className="small">
              Planted: <span className="mono">{truth.planted.join(", ") || "nothing"}</span>
              {truth.notPlanted.length > 0 && <span className="muted"> · couldn't fit: {truth.notPlanted.join(", ")}</span>}
              {dirty && <span className="muted"> · you edited it, so the planted list may no longer match</span>}
            </p>
          )}
          <div className="editor">
            {draft.turns.map((t, i) => (
              <div key={i} className={`erow erow-${t.speaker}`}>
                <div className="erow-top">
                  <span className="muted small">#{i}</span>
                  <select value={t.speaker} onChange={(e) => edit((ts) => { ts[i].speaker = e.target.value as Turn["speaker"]; return ts; })}>
                    <option value="agent">Agent</option>
                    <option value="user">Caller</option>
                  </select>
                  <label className="small">start <input type="number" step="0.1" min="0" value={t.start}
                    onChange={(e) => edit((ts) => { ts[i].start = Number(e.target.value); return ts; })} /></label>
                  <label className="small">end <input type="number" step="0.1" min="0" value={t.end}
                    onChange={(e) => edit((ts) => { ts[i].end = Number(e.target.value); return ts; })} /></label>
                  <label className="small"><input type="checkbox" checked={t.interrupted}
                    onChange={(e) => edit((ts) => { ts[i].interrupted = e.target.checked; return ts; })} /> cut off</label>
                  <button className="icon" title="Delete turn" aria-label={`Delete turn ${i}`}
                    onClick={() => edit((ts) => ts.filter((_, k) => k !== i))}>✕</button>
                </div>
                <textarea rows={2} value={t.text} onChange={(e) => edit((ts) => { ts[i].text = e.target.value; return ts; })} />
              </div>
            ))}
          </div>
          <div className="row-wrap">
            <button className="btn" onClick={() => edit((ts) => {
              const last = ts[ts.length - 1];
              const start = last ? +(last.end + 0.8).toFixed(1) : 0;
              return [...ts, { speaker: last?.speaker === "agent" ? "user" : "agent", text: "", start, end: +(start + 2).toFixed(1), interrupted: false }];
            })}>+ Add turn</button>
            <label className="small">Call ended by{" "}
              <select value={draft.ended_by} onChange={(e) => { setDraft({ ...draft, ended_by: e.target.value as EndedBy }); setDirty(true); }}>
                <option value="agent">agent</option>
                <option value="user">caller</option>
                <option value="system">line drop</option>
              </select>
            </label>
          </div>

          <h3>3. Change the agent's rules (optional)</h3>
          <label className="small"><input type="checkbox" checked={editSpec} onChange={(e) => setEditSpec(e.target.checked)} /> Score against an edited spec</label>
          {editSpec && (
            <>
              <p className="muted small">Try: switch <code>persona</code> to <code>hindi_only</code>, set <code>max_gap_s</code> to 1.0, or turn a check off with <code>enabled: false</code>.</p>
              <textarea className="yaml mono" rows={18} value={specYaml} onChange={(e) => setSpecYaml(e.target.value)} spellCheck={false} />
              <button className="btn" onClick={() => agent && setSpecYaml(agent.yaml)}>Reset spec</button>
            </>
          )}
          <h3>4. How should steps be recognised?</h3>
          <div className="row-wrap">
            <button className={`seg ${matcher === "" ? "seg-on" : ""}`} onClick={() => setMatcher("")}>
              Agent default ({agent ? MATCHER_LABEL[agent.step_matcher] : "…"})
            </button>
            {(["phrase", "ml", "hybrid"] as Matcher[]).map((m) => (
              <button key={m} className={`seg ${matcher === m ? "seg-on" : ""}`} onClick={() => setMatcher(m)}>{MATCHER_LABEL[m]}</button>
            ))}
          </div>
          <p className="muted small">
            Rules look for exact phrases. The model is a character n-gram classifier trained on labelled agent sentences
            {agent?.model && <> ({agent.model.trained_sentences} sentences, {agent.model.features.toLocaleString()} features)</>}; it handles
            paraphrases and Hinglish spelling.
          </p>
          <div className="row-wrap sticky-actions">
            <button className="btn btn-primary" onClick={score} disabled={busy}>{busy ? "Scoring…" : "Score this call"}</button>
            <button className="btn" onClick={compareMatchers} disabled={busy}>Compare rules vs model</button>
          </div>
        </div>
      )}

      {compare && (
        <div className="card">
          <h3>Same call, three ways of recognising steps</h3>
          <div className="compare">
            {(["phrase", "ml", "hybrid"] as Matcher[]).map((m) => {
              const r = compare[m];
              const failing = r.failed_checks.map((c) => CHECK_LABEL[c] ?? c);
              const byModel = r.findings.filter((f) => f.code === "ml_step_match").length;
              return (
                <button key={m} className="compare-col" onClick={() => setResult(truth && !dirty ? { ...r, labels: truth.labels, planted: truth.planted } : r)}>
                  <span className="muted small">{MATCHER_LABEL[m]}</span>
                  <span className={`score tone-${r.score >= 85 ? "good" : r.score >= 65 ? "mid" : "bad"}`}>{r.score}</span>
                  <span className="small">{failing.length ? `fails: ${failing.join(", ")}` : "passes every check"}</span>
                  {byModel > 0 && <span className="small muted">{byModel} step{byModel > 1 ? "s" : ""} found by the model</span>}
                  <span className="small linklike">view details</span>
                </button>
              );
            })}
          </div>
          {truth && !dirty && (
            <p className="small muted">Planted: {truth.planted.join(", ") || "nothing (a clean call)"}. Expected failures: {truth.labels.join(", ") || "none"}.</p>
          )}
        </div>
      )}

      {result && (
        <div id="result">
          <CallView call={result} />
          <div className="row-wrap"><button className="btn" onClick={save}>Save to this browser</button></div>
        </div>
      )}

      <div className="card">
        <h3>Saved in this browser</h3>
        <p className="muted small">The hosted demo has no database, so calls you score are kept only in your browser.</p>
        {saved.length === 0 && <p className="muted small">Nothing saved yet.</p>}
        <ul className="plain">
          {saved.map((s) => (
            <li key={s.result.id} className="saved-row">
              <button className="linklike mono small" onClick={() => setResult(s.result)}>{s.result.id}</button>
              <span className="muted small">score {s.result.score} · {new Date(s.savedAt).toLocaleString()}</span>
              <button className="icon" aria-label="Remove" onClick={() => remove(s.result.id)}>✕</button>
            </li>
          ))}
        </ul>
        <p className="small"><a href={href("/agents")}>See the agent specs →</a></p>
      </div>
    </div>
  );
}
