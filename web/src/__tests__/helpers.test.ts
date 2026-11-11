import { describe, expect, it } from "vitest";
import { scoreTone } from "../api";
import { href } from "../router";

describe("href", () => {
  it("builds a hash route and drops empty params", () => {
    expect(href("/calls", { agent: "a b", check: "", q: undefined })).toBe("#/calls?agent=a+b");
    expect(href("/about")).toBe("#/about");
  });
});

describe("scoreTone", () => {
  it("uses fixed thresholds", () => {
    expect(scoreTone(85)).toBe("good");
    expect(scoreTone(84.9)).toBe("mid");
    expect(scoreTone(65)).toBe("mid");
    expect(scoreTone(64.9)).toBe("bad");
  });
});
