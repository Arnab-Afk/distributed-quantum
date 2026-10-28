import { describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { optionsRequestSchema } from "../src/features/options/schemas/options-request.schema";
import { OracleEvidence } from "../src/shared/components/oracle-evidence";
import { PortfolioValuation } from "../src/features/finance/components/portfolio-valuation";

const provenance = {
  bundle_hash: "recorded-hash",
  bundle: {
    workflow_run_id: "opt-test",
    workflow_definition_id: "options-pricing",
    oracle_refs: [
      {
        provider: "chainlink",
        feed: "eip155:11155111/feed",
        round_id: "18446744073709588700",
        value: "2000.00000000",
        observed_at: "2026-10-26T05:47:00Z",
      },
    ],
  },
};

describe("oracle finance", () => {
  test("options validation preserves explicit feed choice", () => {
    const parsed = optionsRequestSchema.parse({
      option_type: "european_call_long",
      current_value: 2000,
      strike_or_cost: 2100,
      time_to_expiry: 1,
      volatility: 0.2,
      risk_free_rate: 0.05,
      chainlink_price: { network: "ethereum-sepolia", feed: "eth-usd" },
    });
    expect(parsed.chainlink_price?.feed).toBe("eth-usd");
    expect(
      optionsRequestSchema.safeParse({
        ...parsed,
        chainlink_price: { network: "mainnet", feed: "eth-usd" },
      }).success,
    ).toBe(false);
  });
  test("exact round and recorded timestamp remain visible", () => {
    const html = renderToStaticMarkup(
      <OracleEvidence provenance={provenance} />,
    );
    expect(html).toContain("18446744073709588700");
    expect(html).toContain("/api/options/opt-test?download=provenance");
    expect(html).not.toContain("data:application/json");
    expect(html).toContain("2026-10-26T05:47:00Z");
    expect(renderToStaticMarkup(<OracleEvidence />)).toBe("");
  });
  test("unsupported assets do not display an invented quantity", () => {
    const html = renderToStaticMarkup(
      <PortfolioValuation
        result={{
          provenance,
          valuation: {
            investment_usd: "1000",
            allocations: {
              classical: [
                {
                  ticker: "ETH-USD",
                  allocation_usd: "500",
                  price_usd: "2000",
                  quantity: "0.25",
                  status: "valued",
                },
                {
                  ticker: "AAPL",
                  allocation_usd: "500",
                  price_usd: null,
                  quantity: null,
                  status: "unsupported_feed",
                },
              ],
              quantum: [],
            },
          },
        }}
      />,
    );
    expect(html).toContain("0.25000000");
    expect(html).toContain("No supported feed");
    expect(html).toContain("not execution quotes");
  });
});

test("switching off live valuation ignores inactive numeric fields", async () => {
  const { portfolioUploadSchema } =
    await import("../src/features/finance/schemas/portfolio-upload.schema");
  const { riskFormSchema } =
    await import("../src/features/risk/schemas/risk-request.schema");
  const portfolio = {
    useChainlink: false,
    investmentUsd: NaN,
    expectedEthPrice: NaN,
  };
  const risk = {
    riskModel: "equity",
    useChainlink: false,
    quantity: NaN,
    expectedEthPrice: NaN,
  };
  expect(portfolioUploadSchema.safeParse(portfolio).success).toBe(true);
  expect(riskFormSchema.safeParse(risk).success).toBe(true);
  expect(
    portfolioUploadSchema.safeParse({ ...portfolio, useChainlink: true })
      .success,
  ).toBe(false);
  expect(
    riskFormSchema.safeParse({ ...risk, useChainlink: true }).success,
  ).toBe(false);
});

test("missing option inputs use readable field messages", () => {
  const result = optionsRequestSchema.safeParse({
    current_value: NaN,
    strike_or_cost: NaN,
    time_to_expiry: NaN,
    volatility: NaN,
    risk_free_rate: NaN,
  });
  expect(result.success).toBe(false);
  const messages = result.error.issues.map((issue) => issue.message);
  expect(messages).toContain("Choose an option type.");
  expect(messages).toContain("Enter a valid current value.");
  expect(messages.join(" ")).not.toMatch(/NaN|enum|Invalid input/);
});
