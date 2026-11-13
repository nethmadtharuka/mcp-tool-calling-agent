import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { runStore } from "./lib/runs";
import { routes } from "./routes";
import { json, mockBackend } from "./test/helpers";

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

describe("routes", () => {
  beforeEach(() => {
    runStore.clear();
    mockBackend({ "/health": () => json({ status: "ok" }) });
  });

  it.each([
    ["/", "Agent Workspace"],
    ["/execution", "Execution"],
    ["/history", "Run History"],
    ["/tools", "Connected Tools"],
    ["/providers", "Providers"],
    ["/settings", "Settings"],
    ["/nope", "Page not found"],
    ["/execution/run_000000", "Run run_000000"],
  ])("%s renders %s", async (path, heading) => {
    renderAt(path);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeTruthy();
  });

  it("shows the backend as healthy from GET /health", async () => {
    renderAt("/");
    expect(await screen.findByText("API healthy")).toBeTruthy();
  });

  it("shows the backend as unreachable when /health fails", async () => {
    mockBackend({});
    renderAt("/");
    expect(await screen.findByText("API unreachable")).toBeTruthy();
  });
});

describe("workspace journey", () => {
  beforeEach(() => runStore.clear());

  it("runs the agent, shows the answer, and lists the run in history", async () => {
    mockBackend({
      "/health": () => json({ status: "ok" }),
      "/api/agent/run": () => json({ response: "Your pinned version is the latest." }),
    });
    const user = userEvent.setup();
    const router = renderAt("/");

    const runButton = screen.getByRole("button", { name: "Run agent" });
    expect((runButton as HTMLButtonElement).disabled).toBe(true); // empty input

    await user.click(screen.getByRole("button", { name: "Try an example" }));
    await user.keyboard("{Control>}{Enter}{/Control}");

    expect(await screen.findByText("Your pinned version is the latest.")).toBeTruthy();
    expect(screen.getByText("Completed")).toBeTruthy();

    await user.click(screen.getByRole("link", { name: /View run run_/ }));
    expect(router.state.location.pathname).toMatch(/^\/execution\/run_[0-9a-f]{6}$/);
    expect(await screen.findByText("Your pinned version is the latest.")).toBeTruthy();

    await router.navigate("/history");
    const table = await screen.findByRole("table");
    expect(within(table).getByText(/langchain-mcp-adapters/)).toBeTruthy();
    expect(screen.getByText("Showing 1 of 1 runs stored in this browser")).toBeTruthy();
  });

  it("shows a clear error and a retry path when the LLM call fails", async () => {
    mockBackend({
      "/health": () => json({ status: "ok" }),
      "/api/agent/run": () => json({ detail: "The LLM provider request failed. See server logs for details." }, 502),
    });
    const user = userEvent.setup();
    renderAt("/");

    await user.type(screen.getByLabelText("Task for the agent"), "list my repos");
    await user.click(screen.getByRole("button", { name: "Run agent" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("The LLM provider request failed");
    expect(alert.textContent).toContain("HTTP 502");
    expect(screen.getByRole("button", { name: /Edit and retry/ })).toBeTruthy();
  });
});
