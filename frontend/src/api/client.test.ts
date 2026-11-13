import { describe, expect, it } from "vitest";
import { json, mockBackend } from "../test/helpers";
import { ApiError, checkHealth, runAgent } from "./client";

async function failure(p: Promise<unknown>): Promise<ApiError> {
  try {
    await p;
  } catch (e) {
    if (e instanceof ApiError) return e;
    throw e;
  }
  throw new Error("expected an ApiError");
}

describe("runAgent", () => {
  it("posts the message and returns the response string", async () => {
    const fetchMock = mockBackend({ "/api/agent/run": () => json({ response: "hi there" }) });
    await expect(runAgent("hello")).resolves.toBe("hi there");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/agent/run");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ message: "hello" });
  });

  it("maps 502 to an LLM error with the server's safe detail", async () => {
    mockBackend({ "/api/agent/run": () => json({ detail: "The LLM provider request failed. See server logs for details." }, 502) });
    const e = await failure(runAgent("x"));
    expect(e.kind).toBe("llm");
    expect(e.status).toBe(502);
    expect(e.message).toMatch(/LLM provider request failed/);
  });

  it("maps 500 to a server error and keeps config messages", async () => {
    mockBackend({ "/api/agent/run": () => json({ detail: "LLM_API_KEY is required when LLM_PROVIDER='gemini'." }, 500) });
    const e = await failure(runAgent("x"));
    expect(e.kind).toBe("server");
    expect(e.message).toContain("LLM_API_KEY is required");
  });

  it("maps 422 validation lists to a readable message", async () => {
    mockBackend({ "/api/agent/run": () => json({ detail: [{ loc: ["body", "message"], msg: "too short" }] }, 422) });
    const e = await failure(runAgent("x"));
    expect(e.kind).toBe("validation");
    expect(e.message).toBe("The request was rejected as invalid.");
  });

  it("handles a non-JSON 500 page", async () => {
    mockBackend({ "/api/agent/run": () => new Response("<html>Internal Server Error</html>", { status: 500 }) });
    const e = await failure(runAgent("x"));
    expect(e.kind).toBe("server");
    expect(e.message).toBe("The agent failed with an internal error.");
  });

  it.each([502, 503, 504])("treats a gateway %i without the backend's JSON as unreachable, not an LLM failure", async (status) => {
    mockBackend({ "/api/agent/run": () => new Response("", { status }) });
    const e = await failure(runAgent("x"));
    expect(e.kind).toBe("network");
    expect(e.status).toBe(status);
  });

  it("reports an unreachable backend as a network error", async () => {
    mockBackend({});
    const e = await failure(runAgent("x"));
    expect(e.kind).toBe("network");
  });

  it("rejects a 200 without a response string", async () => {
    mockBackend({ "/api/agent/run": () => json({ answer: "wrong shape" }) });
    expect((await failure(runAgent("x"))).kind).toBe("unexpected");
  });
});

describe("checkHealth", () => {
  it("is true only for {status: ok}", async () => {
    mockBackend({ "/health": () => json({ status: "ok" }) });
    await expect(checkHealth()).resolves.toBe(true);
    mockBackend({ "/health": () => json({ status: "degraded" }) });
    await expect(checkHealth()).resolves.toBe(false);
  });

  it("treats a gateway 502 (dead backend behind a proxy) as unreachable", async () => {
    mockBackend({ "/health": () => new Response("", { status: 502 }) });
    expect((await failure(checkHealth())).kind).toBe("network");
  });
});
