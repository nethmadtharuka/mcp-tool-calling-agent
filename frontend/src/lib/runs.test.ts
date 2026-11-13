import { beforeEach, describe, expect, it } from "vitest";
import { json, mockBackend } from "../test/helpers";
import { _reloadRunsForTests, runStore } from "./runs";

const settled = async (id: string) => {
  for (let i = 0; i < 50 && runStore.get(id)?.status === "running"; i++) await new Promise((r) => setTimeout(r, 0));
  return runStore.get(id);
};

describe("runStore", () => {
  beforeEach(() => runStore.clear());

  it("records a completed run with its response and duration", async () => {
    mockBackend({ "/api/agent/run": () => json({ response: "done" }) });
    const id = runStore.start("read the README");
    expect(id).toMatch(/^run_[0-9a-f]{6}$/);
    expect(runStore.get(id)?.status).toBe("running");

    const run = await settled(id);
    expect(run).toMatchObject({ status: "completed", response: "done", request: "read the README" });
    expect(run?.finishedAt).toBeGreaterThanOrEqual(run?.startedAt ?? Infinity);
  });

  it("flags the backend's step-limit notice as stopped", async () => {
    mockBackend({ "/api/agent/run": () => json({ response: "Stopped: reached the limit of 8 tool steps without a final answer." }) });
    expect((await settled(runStore.start("loop")))?.status).toBe("stopped");
  });

  it("records failures with their kind", async () => {
    mockBackend({ "/api/agent/run": () => json({ detail: "The LLM provider request failed." }, 502) });
    const run = await settled(runStore.start("x"));
    expect(run).toMatchObject({ status: "failed", error: { kind: "llm", status: 502 } });
  });

  it("persists newest first, and marks runs cut off by a reload as interrupted", async () => {
    mockBackend({ "/api/agent/run": () => new Promise<Response>(() => {}) }); // never answers
    const first = runStore.start("first");
    const second = runStore.start("second");
    expect(runStore.getAll().map((r) => r.id)).toEqual([second, first]);

    _reloadRunsForTests();
    expect(runStore.getAll().map((r) => [r.id, r.status])).toEqual([
      [second, "interrupted"],
      [first, "interrupted"],
    ]);
  });

  it("survives corrupt storage", () => {
    localStorage.setItem("mcp-agent.runs.v1", "{not json");
    _reloadRunsForTests();
    expect(runStore.getAll()).toEqual([]);
  });
});
