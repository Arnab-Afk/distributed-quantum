# Chain registry — Part of #2

The registry lists network metadata and supported operations. Base Sepolia's
existing wallet service now reads token, escrow, and explorer metadata from it.
Ethereum Sepolia remains available for metadata and explorer links only.

## Configuration and identifiers

`src/quantum_backend_v2/chains/registry.toml` ships inside the Python package.
Bootstrap loads and validates it once, before creating persistence and peer runtimes,
then passes the immutable registry to the API. Invalid configuration prevents
startup. Parsing uses `tomllib` or the existing `tomli` dependency on Python 3.10.

Base Sepolia remains the default. In a CAIP-2 ID, `eip155` identifies the
Ethereum-compatible family and the number identifies the network.

| Network | Canonical ID | AgentKit alias | CDP alias |
| --- | --- | --- | --- |
| Base Sepolia | `eip155:84532` | `base-sepolia` | `base-sepolia` |
| Ethereum Sepolia | `eip155:11155111` | `ethereum-sepolia` | `ethereum-sepolia` |

`registry.resolve()` returns the configured default; `registry.resolve(name)`
accepts a canonical ID, legacy alias, or provider alias. An empty, unknown, or
disabled name raises an error rather than silently selecting Base Sepolia.
Matching is exact and case-sensitive. Duplicate IDs and ambiguous aliases across
entries, including provider mappings, are rejected. There is no global active network.

`QB2_CHAIN_REGISTRY_PATH` optionally selects another TOML file through application
settings; unset uses package data. Relative paths use the working directory.
`NETWORK` selects the wallet network by alias or canonical ID. When unset, the
registry default applies; the packaged default remains Base Sepolia. Empty or
unknown values fail startup. Wallet endpoints use an application-scoped service
with the same immutable registry as the public chain endpoint. Standalone
`AgentKitService` callers load these settings too, or accept an injected registry
and explicit network. Injected registries use their own default, without reading
process-wide network selection.

Mainnet entries must have `enabled = false`. Disabled entries cannot be resolved
for operations and are omitted from the public list. Existing wallet records must
resolve to the selected network before balance queries, provider reconstruction,
transfers, escrow operations, or faucet instructions. Mismatches fail instead of
using the same address on a different chain. Stored network aliases and unique
wallet indexes are unchanged; this is not yet multi-network wallet persistence.

## Credentials and operation capabilities

`rpc_env_var` stores an environment-variable **name**, never a URL or key.
`QB2_BASE_SEPOLIA_RPC_URL` and `QB2_ETHEREUM_SEPOLIA_RPC_URL` are documented in
`.env.example` for future adapters. Neither is required or resolved in this slice.

Base Sepolia declares `explorer_url`, `create_wallet`, `get_balance`,
`transfer_stablecoin`, `aave_supply`, `aave_withdraw`, and `faucet_instructions`.
The service checks each operation before provider or RPC calls. Transaction
capabilities require explorer metadata; transfer and supply also require balance
queries. Aave operations require an explicit pool address. Wallet capabilities
are currently restricted to the existing Base Sepolia provider mapping; adding
another network requires provider validation and implementation coverage.

Ethereum Sepolia declares only `explorer_url`. Listing its provider aliases does
not enable wallet operations. Unimplemented capabilities such as
`verify_transaction` still fail validation. The explorer adapter and the legacy
`utils.basescan` wrappers perform no network I/O. They validate reference shape,
not checksums, existence, ownership, or transaction success.

The faucet endpoint returns manual instructions; it does not send funds. Balance
queries use Web3, not the CDP token-balance endpoint. RPC environment-variable
references remain reserved; this migration retains AgentKit's public RPC defaults.

Explorer templates deliberately support only HTTPS URLs of the form
`https://HOST/tx/{tx_hash}`, `/address/{address}`, and `/block/{block_number}`.
Credentials, query strings, fragments, and extra formatting fields are forbidden.
Custom explorer URL shapes require a deliberate schema/adapter change.

Loader errors report validation reasons without raw values, field locations,
file paths, or parser details. Keep validator messages free of user input; unknown
field names can also contain secrets. Do not log raw TOML or direct Pydantic errors.

## Public API

`GET /api/v1/chains` is public and requires no wallet credentials, RPC, or database query.

The response has `default_chain_id` and an ordered `chains` list. Each enabled
entry contains exactly:

- `chain_id`, `family`, `display_name`, `testnet`
- `native_token`: `symbol`, `decimals`
- `stablecoin`: `symbol`, `decimals`, `address`, or `null`
- `explorers`: `transaction`, `address`, `block` templates
- `capabilities`: the operations declared above for each network

RPC configuration, provider aliases, and escrow configuration are excluded from
responses and OpenAPI.

## Adding another EVM testnet

1. Verify its ID, token metadata, and explorer against official sources. Check
   locked provider versions for each operation before adding provider mappings.
2. Copy a `[[chains]]` entry and replace network-specific fields. Use a unique
   `eip155:NUMBER` without leading zeros and unique aliases. Unknown provider
   mappings and stablecoin metadata can be omitted.
3. Set `testnet = true`, choose `enabled`, and declare only implemented capabilities.
4. Document its RPC environment-variable reference in `.env.example`.
5. Add metadata expectations and run the focused tests below.

## Verified sources and provider limits

Checked October 21, 2026:

- [CAIP-2](https://standards.chainagnostic.org/CAIPs/caip-2) defines the namespaced
  identifier. This slice intentionally accepts only canonical decimal EVM IDs.
- [Base network details](https://docs.base.org/get-started/connect-to-base)
  specify Base Sepolia ID `84532`, ETH, and its explorer.
- [Ethereum client Sepolia metadata](https://github.com/eth-clients/sepolia)
  specifies ID `11155111` and its explorers.
- [Ethereum's ether reference](https://ethereum.org/developers/docs/intro-to-ether/)
  defines 18 decimal places. Both entries use ETH as the native token.
- [Circle's contract list](https://developers.circle.com/stablecoins/usdc-contract-addresses)
  supplies both test USDC addresses. [Circle's USDC reference](https://github.com/circlefin/skills/blob/master/plugins/circle/skills/use-usdc/SKILL.md)
  documents the six-decimal ERC-20 representation. These are test tokens.
- The [AgentKit 0.7.4 distribution](https://pypi.org/project/coinbase-agentkit/0.7.4/)
  was inspected using the wheel URL and SHA-256 from `uv.lock`:
  `coinbase_agentkit/network/network.py` maps both IDs; the wallet provider's
  `_get_cdp_sdk_network` maps both aliases.
- The [CDP SDK 1.45.1 distribution](https://pypi.org/project/cdp-sdk/1.45.1/)
  was inspected the same way. Its `ListEvmTokenBalancesNetwork` enum includes
  `base`, `base-sepolia`, and `ethereum`, **not `ethereum-sepolia`**.
  [Coinbase's balance documentation](https://docs.cdp.coinbase.com/server-wallets/v2/using-the-wallet-api/managing-accounts)
  lists the same subset. Thus Ethereum Sepolia is suitable for this metadata/link
  layer, but general wallet support cannot be inferred from its alias. This
  restriction concerns CDP token-balance queries; the existing service reads
  balances directly through Web3.

## Validation and remaining work

From `backend`, with project dependencies installed:

```bash
uv run --no-sync pytest tests/unit/test_chain_registry.py tests/unit/test_chain_adapter.py tests/unit/test_chains_api.py -q
uv run --no-sync pytest tests/unit/test_chains_bootstrap.py tests/unit/test_wallet_registry_service.py tests/unit/test_basescan_registry.py -q
uv run --no-sync ruff check src/quantum_backend_v2/chains src/quantum_backend_v2/api/routers/chains.py tests/unit/test_chain*.py
uv run --no-sync mypy --follow-imports=silent src/quantum_backend_v2/chains src/quantum_backend_v2/api/routers/chains.py
```

The first command runs isolated registry/API tests. Bootstrap tests exercise the
real app factory and lifespan with persistence, recovery, peers, and legacy external
service clients mocked;
they require the backend's other import-time dependencies. Neither group uses a
database, blockchain, or wallet. They do not verify live peer or wallet integration.

The dependency fix pins the published libp2p 0.6.0 release and removes the moving
archive URL; see [Local development](README.md#local-development). The bootstrap
unit tests still mock peer services. The existing `test_libp2p_peerstore.py` tests
exercise the real library with temporary SQLite files.
`tests/network/test_libp2p_transport.py` verifies real bidirectional RPC, discovery
delivery, and shutdown between two local peers without external services.

## Existing escrow configuration

The Base Sepolia Aave pool `0x07eA79F68B2B3df564D0A34F8e19D9B1e339814b` was
moved from the service to the registry without changing it. Its capability flags
preserve existing transaction-building paths; they do not verify deployment or
reserve compatibility. The [current Aave address book](https://github.com/bgd-labs/aave-address-book/blob/main/src/AaveV3BaseSepolia.sol)
lists a different pool and a different test USDC reserve from this application's
Circle test USDC. Do not substitute one of those addresses alone: pool/token
compatibility and existing positions need a separate escrow review. No live
Aave transaction or contract verification was performed for this migration.

This is **Part of #2**, not its completion. Remaining slices must verify and enable
additional wallet networks, add transaction verification, design network-aware
wallet/payment persistence, propagate application-scoped services through the
remaining proposal/agent orchestration, and add a frontend selector. Existing
payment recording and confirmation semantics remain unchanged.
