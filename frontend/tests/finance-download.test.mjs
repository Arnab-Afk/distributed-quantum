import { expect, test } from "bun:test";
import { financeResultResponse } from "../src/shared/server/finance-result-response";

test("downloads recorded evidence as a private JSON attachment", async () => {
  const evidence = { bundle_hash: "hash", bundle: { inputs: { value: 123 } } };
  const res = await financeResultResponse(Response.json({ result: { provenance: evidence } }), true);
  expect(res.headers.get("Content-Disposition")).toBe('attachment; filename="price-provenance.json"');
  expect(res.headers.get("Cache-Control")).toBe("private, no-store");
  expect(await res.json()).toEqual(evidence);
});
test("download requests preserve auth and ownership errors", async () => {
  for (const status of [401, 403, 404, 503]) {
    const res = await financeResultResponse(Response.json({ detail: "unavailable" }, { status }), true);
    expect(res.status).toBe(status);
    expect(res.headers.has("Content-Disposition")).toBe(false);
  }
});
test("jobs without provenance do not download empty evidence", async () => {
  const res = await financeResultResponse(Response.json({ result: null }), true);
  expect(res.status).toBe(404);
  expect(res.headers.has("Content-Disposition")).toBe(false);
});
test("ordinary detail requests retain their response", async () => {
  const body = { result: { value: 42 } };
  const res = await financeResultResponse(Response.json(body), false);
  expect(await res.json()).toEqual(body);
  expect(res.headers.has("Content-Disposition")).toBe(false);
});
