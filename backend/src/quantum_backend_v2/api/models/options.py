"""Options pricing API models."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from quantum_backend_v2.api.models.prices import ChainlinkPriceRequest


OptionType = Literal[
    "european_call_short",
    "european_call_long",
    "expand",
    "delay",
    "abandon",
    "patent",
    "natural_resource",
    "financial_flexibility",
]


class OptionsJobRequest(BaseModel):
    """Input parameters for a real options pricing job."""

    option_type: OptionType
    chainlink_price: ChainlinkPriceRequest | None = None
    current_value: Annotated[
        float,
        Field(
            gt=0.0,
            allow_inf_nan=False,
            description="S₀, or expected USD price used for oracle deviation checks",
        ),
    ]
    strike_or_cost: Annotated[float, Field(gt=0.0, description="K — strike price or investment cost")]
    time_to_expiry: Annotated[float, Field(gt=0.0, description="T in years")]
    volatility: Annotated[float, Field(gt=0.0, le=5.0, description="σ — annualised volatility")]
    risk_free_rate: Annotated[float, Field(ge=0.0, le=1.0, description="r — annualised risk-free rate")]
    # Short-term option extras
    dividend_per_share: float | None = Field(default=None, ge=0.0)
    days_to_ex_dividend: int | None = Field(default=None, ge=0)
    # Long-term / real option extras
    annual_cost_of_delay: float | None = Field(default=None, ge=0.0)
    # Natural resource extras
    reserve_quantity: float | None = Field(default=None, gt=0.0)
    resource_price_per_unit: float | None = Field(default=None, gt=0.0)
    extraction_cost_per_unit: float | None = Field(default=None, ge=0.0)
    annual_cashflow_after_tax: float | None = Field(default=None, ge=0.0)
    # Financial flexibility extras
    reinvestment_need_pct: float | None = Field(default=None, gt=0.0, le=1.0)
    reinvestment_volatility: float | None = Field(default=None, gt=0.0)
    max_internal_financing_pct: float | None = Field(default=None, gt=0.0, le=1.0)
    cost_of_capital: float | None = Field(default=None, gt=0.0)
    return_on_capital: float | None = Field(default=None)
    # IQAE parameters
    num_uncertainty_qubits: int = Field(default=5, ge=3, le=8)
    epsilon: float = Field(default=0.01, gt=0.0, lt=0.5)
    alpha: float = Field(default=0.05, gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def validate_oracle_option(self) -> OptionsJobRequest:
        if self.chainlink_price is not None and self.option_type not in {
            "european_call_short",
            "european_call_long",
        }:
            raise ValueError("oracle prices currently support european calls only")
        return self


class OptionsSubmitResponse(BaseModel):
    """Response after submitting an options pricing job."""

    job_id: str
    status: str
    option_type: str


class OptionsJobSummary(BaseModel):
    """Summary of an options job for list view."""

    job_id: str
    option_type: str
    status: str
    error: str | None
    created_at: datetime
    updated_at: datetime


class OptionsGreeks(BaseModel):
    """Option Greeks — quantum via finite difference, classical via B-S formulas."""

    delta: float
    gamma: float
    vega: float
    theta: float  # classical only


class OptionsAnalysisResult(BaseModel):
    """Full result for a completed options pricing job."""

    job_id: str
    option_type: OptionType
    request: dict
    provenance: dict | None = None

    # Pricing
    quantum_price: float
    classical_bs_price: float
    classical_binomial_price: float
    price_difference_pct: float

    # Greeks
    quantum_greeks: OptionsGreeks
    classical_greeks: OptionsGreeks

    # IQAE confidence interval
    confidence_interval: list[float]  # [lower, upper]

    # Moneyness
    moneyness: Literal["ITM", "ATM", "OTM"]
    moneyness_ratio: float  # S/K

    # Divergence warning
    divergence_warning: bool
    sigma_zero_fallback: bool

    # Circuit metadata
    num_qubits: int
    circuit_depth: int
    num_iqae_runs: int  # always 5 (price + delta±δ + vega±δ)
    shots_per_run: int
    epsilon: float
    alpha: float

    # Quantum advantage evidence
    classical_mc_samples_equivalent: int
    quadratic_speedup_factor: float

    # Timing
    analysis_duration_ms: int
    generated_at: str


class OptionsJobResponse(BaseModel):
    """Full options job response with results."""

    job_id: str
    option_type: str
    status: str
    error: str | None
    result: OptionsAnalysisResult | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Batch benchmark models
# ---------------------------------------------------------------------------


class BatchOptionsRow(BaseModel):
    """One row in a batch options benchmark CSV."""

    option_type: OptionType
    current_value: Annotated[float, Field(gt=0.0)]
    strike_or_cost: Annotated[float, Field(gt=0.0)]
    time_to_expiry: Annotated[float, Field(gt=0.0)]
    volatility: Annotated[float, Field(gt=0.0, le=5.0)]
    risk_free_rate: Annotated[float, Field(ge=0.0, le=1.0)]
    market_price: float | None = Field(default=None, ge=0.0, description="Observed market price for error comparison")
    # Optional extras (same as OptionsJobRequest)
    annual_cost_of_delay: float | None = None
    reserve_quantity: float | None = None
    resource_price_per_unit: float | None = None
    extraction_cost_per_unit: float | None = None
    annual_cashflow_after_tax: float | None = None
    reinvestment_need_pct: float | None = None
    reinvestment_volatility: float | None = None
    max_internal_financing_pct: float | None = None
    cost_of_capital: float | None = None
    return_on_capital: float | None = None
    # IQAE params per-row (optional; batch defaults used if absent)
    num_uncertainty_qubits: int | None = Field(default=None, ge=3, le=8)
    epsilon: float | None = Field(default=None, gt=0.0, lt=0.5)


class BatchOptionsRowResult(BaseModel):
    """Result for one row in a batch benchmark."""

    row_index: int
    option_type: str
    current_value: float
    strike_or_cost: float
    time_to_expiry: float
    volatility: float
    risk_free_rate: float
    market_price: float | None

    # Prices
    quantum_price: float
    classical_bs_price: float
    classical_binomial_price: float
    price_difference_pct: float  # (quantum - BS) / BS * 100

    # Market error (only if market_price provided)
    quantum_vs_market_pct: float | None
    bs_vs_market_pct: float | None

    # Greeks summary
    quantum_delta: float
    classical_delta: float

    # IQAE metadata
    confidence_interval: list[float]
    moneyness: str
    divergence_warning: bool
    num_qubits: int
    analysis_duration_ms: int


class BatchOptionsSummary(BaseModel):
    """Aggregate statistics for the batch benchmark run."""

    total_rows: int
    succeeded: int
    failed: int
    mean_quantum_bs_diff_pct: float
    mean_quantum_vs_market_pct: float | None  # None if no market prices provided
    mean_bs_vs_market_pct: float | None
    rows_with_divergence_warning: int
    total_duration_ms: int


class BatchOptionsResult(BaseModel):
    """Full batch benchmark response."""

    rows: list[BatchOptionsRowResult]
    errors: list[dict]  # {row_index, error}
    summary: BatchOptionsSummary
