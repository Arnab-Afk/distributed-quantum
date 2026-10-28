import { z } from "zod/v4";

export const optionsRequestSchema = z.object({
  option_type: z.enum(
    [
      "european_call_short",
      "european_call_long",
      "expand",
      "delay",
      "abandon",
      "patent",
      "natural_resource",
      "financial_flexibility",
    ],
    { error: "Choose an option type." },
  ),
  chainlink_price: z
    .object({
      network: z.literal("ethereum-sepolia"),
      feed: z.literal("eth-usd"),
    })
    .optional(),
  current_value: z
    .number({ error: "Enter a valid current value." })
    .positive("Enter a value greater than zero."),
  strike_or_cost: z
    .number({ error: "Enter a valid strike or cost." })
    .positive("Enter a value greater than zero."),
  time_to_expiry: z
    .number({ error: "Enter a valid time to expiry." })
    .positive("Enter a value greater than zero."),
  volatility: z
    .number({ error: "Enter a valid volatility." })
    .positive("Enter a value greater than zero.")
    .max(5),
  risk_free_rate: z
    .number({ error: "Enter a valid risk-free rate." })
    .min(0)
    .max(1),
  dividend_per_share: z.number().optional(),
  days_to_ex_dividend: z.number().optional(),
  annual_cost_of_delay: z.number().optional(),
  reserve_quantity: z.number().optional(),
  resource_price_per_unit: z.number().optional(),
  extraction_cost_per_unit: z.number().optional(),
  annual_cashflow_after_tax: z.number().optional(),
  reinvestment_need_pct: z.number().optional(),
  reinvestment_volatility: z
    .number({ error: "Enter a valid volatility." })
    .optional(),
  max_internal_financing_pct: z.number().optional(),
  cost_of_capital: z.number().optional(),
  return_on_capital: z.number().optional(),
  num_uncertainty_qubits: z.number().int().min(3).max(8).optional(),
  epsilon: z
    .number()
    .positive("Enter a value greater than zero.")
    .lt(0.5)
    .optional(),
  alpha: z
    .number()
    .positive("Enter a value greater than zero.")
    .lt(1)
    .optional(),
});

export type OptionsRequestFormValues = z.infer<typeof optionsRequestSchema>;
