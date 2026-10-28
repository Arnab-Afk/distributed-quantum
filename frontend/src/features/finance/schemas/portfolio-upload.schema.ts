import { z } from "zod/v4";

export const portfolioUploadSchema = z
  .object({
    useChainlink: z.boolean(),
    investmentUsd: z.union([z.number(), z.nan()]),
    expectedEthPrice: z.union([z.number(), z.nan()]),
  })
  .superRefine((values, context) => {
    if (!values.useChainlink) return;
    for (const field of ["investmentUsd", "expectedEthPrice"] as const) {
      if (!Number.isFinite(values[field]) || values[field] <= 0) {
        context.addIssue({
          code: "custom",
          path: [field],
          message: "Enter a positive value.",
        });
      }
    }
  });
