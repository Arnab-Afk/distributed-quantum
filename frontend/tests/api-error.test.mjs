import { expect, test } from "bun:test";
import { readApiError } from "../src/shared/lib/api-error";

test("validation details are readable without echoing submitted input", async () => {
  const response = Response.json({
    detail: [
      { msg: "price must be positive", input: "private", ctx: {} },
      { msg: "quantity is required" },
    ],
  });
  expect(await readApiError(response, "Failed")).toBe(
    "price must be positive; quantity is required",
  );
});

test("text errors and non-JSON failures have a safe display message", async () => {
  expect(
    await readApiError(Response.json({ detail: "feed is stale" }), "Failed"),
  ).toBe("feed is stale");
  expect(await readApiError(new Response("<html>error</html>"), "Failed")).toBe(
    "Failed",
  );
  expect(
    await readApiError(
      Response.json({ detail: { secret: "private" } }),
      "Failed",
    ),
  ).toBe("Failed");
});
