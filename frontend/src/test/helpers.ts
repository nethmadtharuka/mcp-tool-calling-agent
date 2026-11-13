import { vi } from "vitest";

export const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

/** Route fetch calls by path; anything unrouted fails like a dead backend. */
export function mockBackend(routes: Record<string, () => Response | Promise<Response>>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const path = new URL(String(input), "http://localhost").pathname;
    const handler = routes[path];
    if (!handler) throw new TypeError("Failed to fetch");
    return handler();
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
