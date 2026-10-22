import { describe, expect, mock, test } from "bun:test";
import { focusManager, QueryClient, QueryClientProvider, QueryObserver } from "@tanstack/react-query";
import { createElement } from "react";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { renderToStaticMarkup } from "react-dom/server";
import { ProvenanceDetails, RunProvenance } from "../src/features/runs/components/run-provenance";
import { RunDetailPanel } from "../src/features/runs/components/run-detail-page-client";
import { safeEvidenceUrl, verificationReportSchema } from "../src/features/runs/lib/provenance";

function report(status) {
  return {
    bundle_id: "bundle-1", status, checked_at: "2026-10-21T00:00:00Z",
    checks: [
      { kind: "hash", name: "bundle_hash", status: status === "unverified" ? "failed" : "passed", message: status === "unverified" ? "Commitment mismatch" : "Commitment matches", reference: null, url: null },
      { kind: "storage", name: "storage_content", status: status === "verified" ? "passed" : "unavailable", message: status === "verified" ? "Retrieved bundle matches" : "No adapter", reference: "fixture-cid", url: "https://example.org/ipfs/fixture-cid" },
      { kind: "anchor", name: "anchor_transaction", status: status === "verified" ? "passed" : "unavailable", message: status === "verified" ? "Confirmed anchor root matches" : "No adapter", reference: "fixture-tx", url: "https://example.org/tx/fixture-tx" },
    ],
  };
}

function render(props) {
  return renderToStaticMarkup(createElement(ProvenanceDetails, props));
}

describe("run provenance", () => {
  test.each([
    ["verified", "Verified"], ["partially_verified", "Partially verified"], ["unverified", "Unverified"],
  ])("renders %s badge", (status, label) => {
    expect(render({ recorded: true, report: report(status) })).toContain(`role="status">${label}`);
  });

  test("distinguishes verified and partially verified badge treatments", () => {
    expect(render({ recorded: true, report: report("verified") }))
      .toMatch(/data-variant="default"[^>]*role="status">Verified/);
    expect(render({ recorded: true, report: report("partially_verified") }))
      .toMatch(/data-variant="secondary"[^>]*role="status">Partially verified/);
  });

  test("uses human check labels and handles unknown check names safely", () => {
    const evidence = report("partially_verified");
    const html = render({ recorded: true, report: evidence });
    expect(html).toContain("Stored evidence");
    expect(html).toContain("Anchor transaction");
    expect(html).not.toContain("storage_content");
    expect(html).not.toContain("anchor_transaction");
    evidence.checks[0].name = "__proto__";
    expect(render({ recorded: true, report: evidence })).toContain("Additional check");
  });

  test.each(["queued", "running", "failed", "cancelled", "completed"])(
    "renders the provenance card only for completed runs (%s)", (status) => {
      const client = new QueryClient();
      try {
        const html = renderToStaticMarkup(createElement(QueryClientProvider, { client },
          createElement(AppRouterContext.Provider, { value: { push: mock() } },
            createElement(RunDetailPanel, { run: {
              jobId: "run-1", status, provenanceBundleId: null,
              createdAt: "2026-10-21T00:00:00Z", progress: null, result: null, planId: null,
            } }),
          ),
        ));
        expect(html.includes("Result provenance")).toBe(status === "completed");
        expect(html.includes("No provenance bundle recorded")).toBe(status === "completed");
      } finally {
        client.clear();
      }
    },
  );

  test("focus does not refetch evidence, but explicit refresh still does", async () => {
    const originalFetch = globalThis.fetch;
    const fetchMock = mock(async () => Response.json(report("verified")));
    const client = new QueryClient();
    let unsubscribe;
    globalThis.fetch = fetchMock;
    focusManager.setFocused(false);
    client.mount();
    try {
      renderToStaticMarkup(createElement(QueryClientProvider, { client },
        createElement(RunProvenance, { bundleId: "bundle-1" }),
      ));
      const query = client.getQueryCache().getAll()[0];
      expect(query.options.refetchOnWindowFocus).toBe(false);
      const observer = new QueryObserver(client, { ...query.options, staleTime: 0 });
      unsubscribe = observer.subscribe(() => {});
      await observer.refetch({ cancelRefetch: false });
      expect(fetchMock.mock.calls.length).toBe(1);
      focusManager.setFocused(true);
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(fetchMock.mock.calls.length).toBe(1);
      await observer.refetch();
      expect(fetchMock.mock.calls.length).toBe(2);
    } finally {
      unsubscribe?.();
      client.unmount();
      client.clear();
      focusManager.setFocused(undefined);
      globalThis.fetch = originalFetch;
    }
  });

  test("renders both storage and anchor links with safe external-link attributes", () => {
    const html = render({ recorded: true, report: report("partially_verified") });
    expect(html).toContain('href="https://example.org/ipfs/fixture-cid"');
    expect(html).toContain('href="https://example.org/tx/fixture-tx"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain("Unavailable");
  });

  test("missing, loading and error states never claim successful verification", () => {
    expect(render({ recorded: false })).toContain("No provenance bundle recorded");
    const loading = render({ recorded: true, loading: true, report: report("verified") });
    expect(loading).toContain("Checking evidence");
    expect(loading).not.toContain('role="status">Verified');
    const error = render({ recorded: true, error: true, report: report("verified") });
    expect(error).toContain('role="alert"');
    expect(error).toContain('role="status">Unverified');
    expect(error).not.toContain('href=');
  });

  test("rejects executable, credential-bearing and malformed evidence URLs", () => {
    for (const url of ["javascript:alert(1)", "data:text/html,test", "https://user:secret@example.org", "/relative", "invalid"]) {
      expect(safeEvidenceUrl(url)).toBeUndefined();
    }
    const unsafe = report("unverified");
    unsafe.checks[1].url = "javascript:alert(1)";
    expect(render({ recorded: true, report: unsafe })).not.toContain('href="javascript:');
  });

  test("validates the API report rather than trusting an unchecked type cast", () => {
    expect(verificationReportSchema.safeParse(report("partially_verified")).success).toBe(true);
    expect(verificationReportSchema.safeParse({ ...report("verified"), status: "probably_fine" }).success).toBe(false);
  });
});
