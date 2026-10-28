import { afterEach, expect, mock, test } from "bun:test";

let user = null;
let assertion = null;
mock.module("server-only", () => ({}));
mock.module("../src/features/auth/server/session", () => ({ getSession: async () => ({ user }) }));
mock.module("../src/features/auth/server/backend-assertion", () => ({ backendAssertion: () => assertion }));
const { financeBackendFetch } = await import("../src/shared/server/finance-backend-fetch");
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; user = null; assertion = null; });

test("unauthenticated requests never contact the backend", async () => {
  globalThis.fetch = mock(() => { throw new Error("must not fetch"); });
  expect((await financeBackendFetch("https://backend.invalid")).status).toBe(401);
  expect(globalThis.fetch).not.toHaveBeenCalled();
});

test("missing signing configuration fails closed", async () => {
  user = { id: "owner", email: "owner@example.test" };
  expect((await financeBackendFetch("https://backend.invalid")).status).toBe(503);
});

test("requests use the signed session identity and disable caching", async () => {
  user = { id: "owner", email: "owner@example.test" };
  assertion = "Bearer signed-owner";
  globalThis.fetch = mock(async (_url, init) => {
    expect(init.headers.get("Authorization")).toBe(assertion);
    expect(init.cache).toBe("no-store");
    expect(init.redirect).toBe("error");
    return new Response("{}", { status: 200 });
  });
  expect((await financeBackendFetch("https://backend.invalid", { headers: { Authorization: "Bearer spoofed" } })).status).toBe(200);
});
