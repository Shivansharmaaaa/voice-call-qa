import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ScoredCall } from "../api";
import { CallView } from "../components/CallView";

afterEach(cleanup);

const call: ScoredCall = {
  id: "t-1",
  agent_id: "field-sales-screener",
  ended_by: "agent",
  source: "synthetic",
  score: 72.7,
  turns: [
    { speaker: "agent", text: "Aapka notice period kitna hai?", start: 0, end: 2, interrupted: false },
    { speaker: "user", text: "Ek mahina", start: 2.5, end: 3, interrupted: false },
    { speaker: "agent", text: "Aapka notice period", start: 6.5, end: 7.5, interrupted: true },
    { speaker: "user", text: "Haan boliye", start: 7.5, end: 8, interrupted: false },
  ],
  findings: [
    { check: "latency", code: "slow_response", severity: "fail", detail: "agent took 3.5s to respond (limit 2.0s)", turn: 2, step: null },
    { check: "coverage", code: "skipped_step", severity: "fail", detail: "required step 'salary' was skipped", turn: null },
  ],
  metrics: { repeat_rate: 0, gap_p95_s: 3.2 },
  breakdown: [
    { check: "coverage", weight: 3, passed: false, findings: 1 },
    { check: "latency", weight: 1, passed: false, findings: 1 },
    { check: "repeats", weight: 2, passed: true, findings: 0 },
  ],
  failed_checks: ["coverage", "latency"],
  labels: ["latency:slow_response", "repeats:repeat"],
  planted: ["slow_response:line_2", "repeat:notice_period"],
};

describe("CallView", () => {
  it("pins a turn finding under that turn and marks the silence before it", () => {
    render(<CallView call={call} />);
    const turn = screen.getByText("Aapka notice period").closest(".turn") as HTMLElement;
    expect(within(turn).getByText(/took 3.5s to respond/)).toBeTruthy();
    expect(within(turn).getByText("cut off")).toBeTruthy();
    expect(screen.getByText("3.5 s silence")).toBeTruthy();
  });

  it("shows call-level findings separately", () => {
    render(<CallView call={call} />);
    const card = screen.getByText("Call-level findings").closest(".card") as HTMLElement;
    expect(within(card).getByText(/'salary' was skipped/)).toBeTruthy();
  });

  it("compares planted faults with what was found", () => {
    render(<CallView call={call} />);
    const card = screen.getByText("What was planted").closest(".card") as HTMLElement;
    expect(within(card).getByText("latency:slow_response").parentElement?.textContent).toContain("caught");
    expect(within(card).getByText("repeats:repeat").parentElement?.textContent).toContain("missed");
  });

  it("shows the score ring with an accessible label", () => {
    render(<CallView call={call} />);
    expect(screen.getByRole("img", { name: "score 72.7 of 100" })).toBeTruthy();
  });
});

describe("model matches", () => {
  it("labels steps found by the trained model and names the matcher", () => {
    const withModel: ScoredCall = {
      ...call,
      matcher: "hybrid",
      findings: [{ check: "coverage", code: "ml_step_match", severity: "info", turn: 0, step: "location",
        detail: "step 'location' recognised by the trained model (p=0.62); no rule phrase matched" }],
    };
    render(<CallView call={withModel} />);
    const turn = screen.getByText("Aapka notice period kitna hai?").closest(".turn") as HTMLElement;
    expect(within(turn).getByText("Model")).toBeTruthy();
    expect(screen.getByText("Rules + model")).toBeTruthy();
  });
});
