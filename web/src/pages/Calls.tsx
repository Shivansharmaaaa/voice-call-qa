import { useEffect, useState } from "react";
import { Agent, api, CallRow, CHECK_LABEL, ScoredCall, scoreTone } from "../api";
import { go, href } from "../router";
import { CallView } from "../components/CallView";

export function Calls({ params }: { params: URLSearchParams }) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [rows, setRows] = useState<CallRow[] | null>(null);
  const [err, setErr] = useState("");
  const agent = params.get("agent") ?? "";
  const check = params.get("check") ?? "";
  const q = params.get("q") ?? "";

  useEffect(() => { api.agents().then(setAgents).catch(() => {}); }, []);
  useEffect(() => {
    setRows(null);
    api.calls({ agent, check, q }).then(setRows).catch((e) => setErr(String(e.message ?? e)));
  }, [agent, check, q]);

  const set = (k: string, v: string) => go("/calls", { agent, check, q, [k]: v });
  const checks = Object.keys(CHECK_LABEL);

  return (
    <div className="page">
      <h1>Calls</h1>
      <div className="card filters">
        <label>Agent
          <select value={agent} onChange={(e) => set("agent", e.target.value)}>
            <option value="">All agents</option>
            {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
        <label>Failing check
          <select value={check} onChange={(e) => set("check", e.target.value)}>
            <option value="">Any</option>
            {checks.map((c) => <option key={c} value={c}>{CHECK_LABEL[c]}</option>)}
          </select>
        </label>
        <label>Search id
          <input defaultValue={q} placeholder="e.g. hindi-006" onKeyDown={(e) => {
            if (e.key === "Enter") set("q", (e.target as HTMLInputElement).value);
          }} />
        </label>
      </div>
      {err && <div className="card error">{err}</div>}
      {!rows && !err && <div className="card muted">Loading…</div>}
      {rows && (
        <div className="card table-wrap">
          <p className="muted small">{rows.length} calls</p>
          <table className="calls">
            <thead><tr><th>Score</th><th>Call</th><th>Failing checks</th><th className="hide-sm">What was planted</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} onClick={() => go(`/call/${r.id}`)}>
                  <td><span className={`score tone-${scoreTone(r.score)}`}>{r.score}</span></td>
                  <td><a className="mono small" href={href(`/call/${r.id}`)}>{r.id}</a><div className="muted small">{r.turns} turns</div></td>
                  <td><div className="chips">{r.failed_checks.map((c) => <span key={c} className="chip chip-bad">{CHECK_LABEL[c] ?? c}</span>)}
                    {r.failed_checks.length === 0 && <span className="muted small">none</span>}</div></td>
                  <td className="hide-sm small muted">{(r.planted ?? []).join(", ") || "clean"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function CallPage({ id }: { id: string }) {
  const [call, setCall] = useState<ScoredCall | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setCall(null);
    api.call(id).then(setCall).catch((e) => setErr(String(e.message ?? e)));
  }, [id]);
  return (
    <div className="page">
      <a className="small" href={href("/calls", call ? { agent: call.agent_id } : undefined)}>← All calls</a>
      {err && <div className="card error">{err}</div>}
      {!call && !err && <div className="card muted">Loading…</div>}
      {call && <CallView call={call} />}
      {call && (
        <div className="card">
          <p>Want to change this call and see what happens?</p>
          <a className="btn" href={href("/playground", { from: call.id })}>Open in the playground</a>
        </div>
      )}
    </div>
  );
}
