import { afterEach, beforeEach, describe, expect, test } from "bun:test";

import { getProvider } from "../src/features/vault-pinning/services/index.ts";

const realFetch = globalThis.fetch;

let calls;

function fakeFetch(response) {
  calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return response;
  };
}

beforeEach(() => {
  process.env.NEXT_PUBLIC_LIGHTHOUSE_KEY = "test-key";
});

afterEach(() => {
  globalThis.fetch = realFetch;
  delete process.env.NEXT_PUBLIC_LIGHTHOUSE_KEY;
});

describe("lighthouse pinning provider (shown as Filecoin)", () => {
  test("is registered next to Pinata and shown as Filecoin", () => {
    expect(getProvider("lighthouse").displayName).toBe("Filecoin (via Lighthouse)");
    expect(getProvider("pinata").displayName).toBe("Pinata");
  });

  test("uploads to Lighthouse with the API key and returns the CID and size", async () => {
    fakeFetch(
      Response.json({ Name: "vault.json", Hash: "QmTestHash", Size: "58" }),
    );

    const result = await getProvider("lighthouse").pin("bagaTestCid", { a: 1 });

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("https://upload.lighthouse.storage/api/v0/add");
    expect(calls[0].init.headers.Authorization).toBe("Bearer test-key");
    expect(result.cid).toBe("QmTestHash");
    expect(result.size).toBe(58);
  });

  test("surfaces the upload error instead of reporting a pin", async () => {
    fakeFetch(new Response("quota exceeded", { status: 402 }));

    await expect(getProvider("lighthouse").pin("bagaTestCid", {})).rejects.toThrow(
      "Lighthouse upload failed (402)",
    );
  });

  test("fails with a clear message when the API key is missing", async () => {
    delete process.env.NEXT_PUBLIC_LIGHTHOUSE_KEY;
    fakeFetch(Response.json({}));

    await expect(getProvider("lighthouse").pin("bagaTestCid", {})).rejects.toThrow(
      "NEXT_PUBLIC_LIGHTHOUSE_KEY",
    );
    expect(calls).toHaveLength(0);
  });
});
