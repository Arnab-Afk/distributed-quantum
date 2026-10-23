# Backend V2

`backend` is the next backend foundation for the decentralized quantum
service network. It starts with a thin FastAPI platform edge, explicit
configuration, typed models, and a protocol-first package layout that will
grow into the full migration plan described in `backend-migration.md`.

## Provenance

See [PROVENANCE.md](PROVENANCE.md) for the versioned canonical hashing and Merkle
proof format, backward-compatible bundle fields, and Ethereum anchoring handoff.

## Kubo RPC foundation

Optional `AppSettings.kubo` reads the deployment's existing `KUBO_RPC_SECRET`,
plus `KUBO_RPC_URL` (default `http://kubo:5001`),
`KUBO_RPC_TIMEOUT_SECONDS` (default 30 seconds, maximum 300), and
`KUBO_RPC_MAX_RESPONSE_BYTES` (default 4 MiB, maximum 64 MiB). The token is masked;
missing credentials do not prevent backend configuration loading. There are no
startup probes or automatic content uploads. Use a private endpoint, never a
browser-visible secret or publicly published admin port.

Kubo can send an error only in a trailer after HTTP 200. The internal HTTP/1.1
POST transport detects it using public `httpcore`/`h11` interfaces, keeping native
pooling/TLS/timeouts without private monkeypatches. Direct dependencies are the
already-locked versions, not new packages/upgrades. SDK methods follow separately.
See the pinned [late-error emitter](https://github.com/ipfs/go-ipfs-cmds/blob/v0.16.1/http/responseemitter.go).

```bash
uv run --frozen pytest tests/unit/test_kubo_config.py tests/unit/test_kubo_transport.py -q
```

## Current Milestone

The current scaffold establishes:

- a clean Python package layout under `src/quantum_backend_v2/`
- a thin versioned FastAPI application
- explicit configuration loading
- a first health endpoint
- room for protocol, package, and swarm layers to grow independently

The public `GET /api/v1/chains` endpoint lists configured testnets and the
operations supported by the new chain layer. See [Chain registry](CHAIN_REGISTRY.md)
for its configuration, public fields, tests, and the remaining wallet migration.

## Local Development

Use [uv](https://docs.astral.sh/uv/) from this directory so the virtualenv includes runtime and dev tools. Running plain `pytest` from your shell can pick a global interpreter (for example a pyenv shim) that does not have project dependencies installed, which often surfaces as `ModuleNotFoundError: No module named 'beanie'`.

```bash
cd backend
uv sync --locked
uv run pytest
make run
```

libp2p is pinned to the published `0.6.0` release. Its previous dependency URL
tracked GitHub's moving `main` branch, so the downloaded source could disagree
with `uv.lock`. Keep the release pin and use `uv sync --locked` for reproducible
installs; update the version and lockfile together when deliberately upgrading.

The dev dependencies include `tomli` because mypy checks Python 3.10 compatibility,
including the TOML fallback, even when development uses a newer Python version.

To verify real libp2p message exchange and discovery locally:

```bash
uv run --locked pytest tests/network/test_libp2p_transport.py -q
```

This test starts two peers on loopback with temporary SQLite files and ephemeral
ports, then verifies shutdown. It needs no MongoDB, wallet credentials, or remote peers.

`make run` is the normal local startup path. `make run-clean` removes the local
libp2p peerstore and peer-log files first, then starts the backend with a clean
embedded dev swarm.

These `make` targets are set up for both macOS and Windows. On macOS they use
`bash` from your `PATH`. On Windows they default to Git Bash at
`C:/Program Files/Git/bin/bash.exe`. If one machine uses a different Bash
location, override it per command, for example
`make BASH=/custom/path/to/bash run`.

With pip instead of uv:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```

Postgres: set `QB2_POSTGRES_TARGET=local` when you want `QB2_POSTGRES_LOCAL_DSN` to apply (for example a local database named `qds`). If `QB2_POSTGRES_TARGET=neon`, the local DSN is ignored and the Neon DSNs are used.
