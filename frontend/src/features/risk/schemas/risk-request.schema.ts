import { z } from "zod/v4";

export const riskUploadSchema = z.object({
  risk_model: z.enum(["equity", "credit"]),
});

export const riskFormSchema = z
  .object({
    riskModel: z.enum(["equity", "credit"]),
    useChainlink: z.boolean(),
    quantity: z.union([z.number(), z.nan()]),
    expectedEthPrice: z.union([z.number(), z.nan()]),
  })
  .superRefine((values, context) => {
    if (!values.useChainlink || values.riskModel !== "equity") return;
    for (const field of ["quantity", "expectedEthPrice"] as const) {
      if (!Number.isFinite(values[field]) || values[field] <= 0) {
        context.addIssue({
          code: "custom",
          path: [field],
          message: "Enter a positive value.",
        });
      }
    }
  });

export type RiskUploadFormValues = z.infer<typeof riskUploadSchema>;
