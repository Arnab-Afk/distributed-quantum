# Wallet portfolio risk analyzer (issue #19)

Read-only VaR/CVaR for public EVM addresses using registry adapters and the existing equity risk engine.

## API

`POST /api/v1/risk/analyze-wallet`

```json
{
  "address": "0x…",
  "networks": [],
  "lookback_days": 252,
  "num_uncertainty_qubits": 4,
  "epsilon": 0.05,
  "alpha": 0.05
}
```

- Auth required (same as other risk routes). Analysis itself never prompts for signatures or approvals.
- Empty `networks` selects every enabled EVM chain with `get_balance` (currently Base Sepolia).
- Resolve ENS client-side before calling; the body accepts a hex address only.

## Pricing

| Holding | Source |
| --- | --- |
| Stablecoin (USDC) | Assumed 1.00 USD peg (`stablecoin-peg`) |
| Native ETH | Chainlink `eth-usd` on a registry chain with `get_price` (Ethereum Sepolia) |

Holdings that cannot be priced appear under `unpriceable_holdings` and are excluded from VaR weights. Every priced row and the top-level `data_sources` list include source kind, detail, and `observed_at`.

## Frontend

Risk Lab (`/risk`) includes a wallet field (address or ENS) that posts through `/api/risk/analyze-wallet` to the backend.

## Tests

```bash
uv run --no-sync pytest tests/unit/test_wallet_portfolio.py -q
```
