import type { OracleProvenance } from "@/shared/types/oracle";

export interface PortfolioAllocation {
  ticker: string;
  allocation_usd: string;
  price_usd: string | null;
  quantity: string | null;
  status: "valued" | "unsupported_feed";
}
export type FinanceResult = Record<string, unknown> & {
  provenance?: OracleProvenance;
  valuation?: { investment_usd: string; allocations: { classical: PortfolioAllocation[]; quantum: PortfolioAllocation[] } };
};

// --- Backend (snake_case) types ---

export interface BackendFinancialSubmitResponse {
  job_id: string;
  status: string;
  problem_type: string;
}

export interface BackendFinancialJobSummary {
  job_id: string;
  filename: string;
  problem_type: string | null;
  status: string;
  row_count: number | null;
  col_count: number | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface BackendFinancialJobResponse {
  job_id: string;
  filename: string;
  problem_type: string | null;
  status: string;
  row_count: number | null;
  col_count: number | null;
  error: string | null;
  result: FinanceResult | null;
  created_at: string;
  updated_at: string;
}

export interface BackendFinancialComparisonResponse {
  job_id: string;
  filename: string;
  generated_at: string;
  fairness: Record<string, unknown>;
  dataset: Record<string, unknown>;
  problem: Record<string, unknown>;
  classical: Record<string, unknown>;
  quantum: Record<string, unknown>;
  scorecard: Record<string, unknown>;
  evidence: Record<string, unknown>;
  verdict: Record<string, unknown>;
}

// --- UI-facing camelCase types ---

export interface FinanceJobSummary {
  jobId: string;
  filename: string;
  problemType: string | null;
  status: string;
  rowCount: number | null;
  colCount: number | null;
  error: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface FinanceJobDetail {
  jobId: string;
  filename: string;
  problemType: string | null;
  status: string;
  rowCount: number | null;
  colCount: number | null;
  error: string | null;
  result: FinanceResult | null;
  createdAt: string;
  updatedAt: string;
}

export interface FinanceComparison {
  jobId: string;
  filename: string;
  generatedAt: string;
  fairness: Record<string, unknown>;
  dataset: Record<string, unknown>;
  problem: Record<string, unknown>;
  classical: Record<string, unknown>;
  quantum: Record<string, unknown>;
  scorecard: Record<string, unknown>;
  evidence: Record<string, unknown>;
  verdict: Record<string, unknown>;
}
