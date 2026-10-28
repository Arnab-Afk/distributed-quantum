export interface OracleProvenance {
  bundle_hash: string;
  bundle: {
    workflow_run_id: string;
    workflow_definition_id: "options-pricing" | "risk-analysis" | "portfolio-optimization";
    oracle_refs: {
      provider: string;
      feed: string;
      round_id: string;
      value: string;
      observed_at: string;
    }[];
  };
}
