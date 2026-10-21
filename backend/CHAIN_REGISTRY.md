# Chain registry — Part of #2

The registry lists network metadata and supported operations. This slice supports
only explorer links for addresses, transactions, and blocks. Listing a network
does not enable it in the existing wallet or payment endpoints.

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
This setting **does not change the legacy `NETWORK` setting**.

Mainnet entries must have `enabled = false`. Disabled entries cannot be resolved
for operations and are omitted from the public list. Legacy wallet paths have
not yet been migrated to enforce these guards.

## Credentials and operation capabilities

`rpc_env_var` stores an environment-variable **name**, never a URL or key.
`QB2_BASE_SEPOLIA_RPC_URL` and `QB2_ETHEREUM_SEPOLIA_RPC_URL` are documented in
`.env.example` for future adapters. Neither is required or resolved in this slice.

The only accepted capability is `explorer_url`; an empty list disables it.
Unimplemented capabilities such as `get_balance`, `transfer_stablecoin`, and
`verify_transaction` fail validation. The adapter performs no network I/O. It
validates reference shape, not checksums, existence, ownership, or transaction success.

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
- `capabilities`: currently `["explorer_url"]` for both shipped entries

RPC configuration and provider aliases are excluded from responses and OpenAPI.

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
  slice, but general wallet or balance support cannot be inferred from its alias.

## Validation and remaining work

From `backend`, with project dependencies installed:

```bash
uv run --no-sync pytest tests/unit/test_chain_registry.py tests/unit/test_chain_adapter.py tests/unit/test_chains_api.py -q
uv run --no-sync pytest tests/unit/test_chains_bootstrap.py -q
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

This is **Part of #2**, not its completion. Remaining slices must add and verify
operation-specific wallet/payment adapters, migrate `AgentKitService` and
`basescan` (including their hard-coded addresses and fallback behavior), validate
wallet/payment network fields, design network-aware persistence without assuming
an EVM address identifies one network, and add a frontend selector. No wallet
index, payment flow, provenance code, or feature branch is migrated here.
