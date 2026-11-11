export type Speaker = "agent" | "user";
export type EndedBy = "agent" | "user" | "system";

export interface Turn {
  speaker: Speaker;
  text: string;
  start: number;
  end: number;
  interrupted: boolean;
}

export interface Finding {
  check: string;
  code: string;
  severity: "fail" | "warn" | "info";
  detail: string;
  turn: number | null;
}

export interface CallInput {
  id: string;
  agent_id: string;
  ended_by: EndedBy;
  turns: Turn[];
}

export interface ScoredCall extends CallInput {
  score: number;
  findings: Finding[];
  metrics: Record<string, number>;
  breakdown: { check: string; weight: number; passed: boolean; findings: number }[];
  failed_checks: string[];
  labels?: string[];
  planted?: string[];
  source: "synthetic" | "playground" | "stored";
}

export interface CheckCfg {
  name: string;
  weight: number;
  enabled: boolean;
  params: Record<string, unknown>;
}

export interface Agent {
  id: string;
  name: string;
  persona: string;
  yaml: string;
  flow: { id: string; match: string[]; required: boolean }[];
  compliance_lines: string[];
  allowed_english: string[];
  checks: CheckCfg[];
  faults: string[];
}

export interface Summary {
  agent_id: string;
  name: string;
  persona: string;
  calls: number;
  mean_score: number | null;
  clean_calls: number;
  fail_rate_by_check: Record<string, number>;
  weights: Record<string, number>;
  avg_metrics: Record<string, number>;
  most_skipped_steps: Record<string, number>;
  score_histogram: number[];
  worst_calls: { id: string; score: number }[];
}

export interface CallRow {
  id: string;
  agent_id: string;
  score: number;
  failed_checks: string[];
  planted: string[] | null;
  source: string;
  turns: number;
}

export interface Fault {
  id: string;
  label: string;
  description: string;
  should_flag: boolean;
}

export interface Generated {
  seed: number;
  call: CallInput;
  labels: string[];
  planted: string[];
  not_planted: string[];
}

export interface Benchmark {
  calls: number;
  per_finding: Record<string, { tp: number; fp: number; fn: number; precision: number; recall: number }>;
  must_not_flag: Record<string, { planted: number; wrongly_flagged: number }>;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { "content-type": "application/json" }, ...init });
  if (!r.ok) {
    let msg = `${r.status}`;
    try {
      const body = await r.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* not JSON */
    }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export const api = {
  agents: () => req<Agent[]>("/api/agents"),
  faults: () => req<Fault[]>("/api/faults"),
  summary: (id: string) => req<Summary>(`/api/agents/${encodeURIComponent(id)}/summary`),
  calls: (params: Record<string, string>) =>
    req<CallRow[]>(`/api/calls?${new URLSearchParams(Object.entries(params).filter(([, v]) => v))}`),
  call: (id: string) => req<ScoredCall>(`/api/calls/${encodeURIComponent(id)}`),
  score: (call: CallInput, spec_yaml?: string) =>
    req<ScoredCall>("/api/score", { method: "POST", body: JSON.stringify({ call, spec_yaml: spec_yaml || null }) }),
  generate: (agent_id: string, faults: string[], seed?: number) =>
    req<Generated>("/api/generate", { method: "POST", body: JSON.stringify({ agent_id, faults, seed }) }),
  benchmark: () => req<Benchmark>("/api/benchmark"),
};

export const CHECK_LABEL: Record<string, string> = {
  coverage: "Required steps covered",
  order: "Steps in order",
  early_exit: "No early hang-up",
  one_question: "One question per turn",
  repeats: "No unexplained repeats",
  language: "Stays in persona",
  latency: "Responds quickly",
};

export function scoreTone(score: number): "good" | "mid" | "bad" {
  return score >= 85 ? "good" : score >= 65 ? "mid" : "bad";
}
