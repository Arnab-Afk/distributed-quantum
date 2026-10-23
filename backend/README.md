# Backend V2

`backend` is the next backend foundation for the decentralized quantum
service network. It starts with a thin FastAPI platform edge, explicit
configuration, typed models, and a protocol-first package layout that will
grow into the full migration plan described in `backend-migration.md`.

## Provenance

See [PROVENANCE.md](PROVENANCE.md) for the versioned canonical hashing and Merkle
proof format, backward-compatible bundle fields, and Ethereum anchoring handoff.

## Kubo RPC client

`quantum_backend_v2.content.kubo.KuboClient` targets the pinned Kubo **v0.43.1**
service from #59/#60. Use it on the backend's **asyncio** loop, not inside the
libp2p Trio thread. It is optional: this change adds no startup probe, automatic
uploads, gateway reads or quantum-job integration.

Configuration flows through `AppSettings.from_env()` into `settings.kubo`:

| Variable | Default / purpose |
|---|---|
| `KUBO_RPC_URL` | `http://kubo:5001`; HTTP(S) root or `/api/v0` base |
| `KUBO_RPC_SECRET` | Private raw token shared with Kubo; required only when constructing the client |
| `KUBO_RPC_TIMEOUT_SECONDS` | `30`; finite I/O and total-operation timeout, maximum `300` |
| `KUBO_RPC_MAX_RESPONSE_BYTES` | `4194304`; decoded response budget, maximum 64 MiB |

The default hostname resolves inside Compose's `content_network`. Outside Docker,
use a protected connection; **do not publish RPC publicly**. URLs containing
credentials, query parameters or fragments are rejected. Redirects and environment
proxies are disabled; tokens are masked in settings and omitted from client errors.

```python
from quantum_backend_v2.config import KuboSettings
from quantum_backend_v2.content.kubo import KuboClient, KuboError


async def maybe_store(payload: bytes, config: KuboSettings) -> str | None:
    try:
        async with KuboClient(config) as client:
            added = await client.add(payload)
            return added.cid
    except KuboError:
        # Keep the original execution result; storage is optional.
        return None
```

For repeated operations, reuse one client outside the loop. `async with`/`aclose()`
closes its HTTP session; binary input files remain caller-owned, but multipart
encoding may seek to their beginning and advance their cursor. Inputs may be
bytes or regular binary files; do not pass blocking pipes/custom blocking readers.

| Method | Typed result |
|---|---|
| `add(data, pin=True)` | CIDv1 and reported DAG size (not necessarily original file length) |
| `pin_add(cid, recursive=True)` / `pin_rm(cid, recursive=True)` | Acknowledged pin CIDs; unpinning is not immediate deletion |
| `pin_ls(cid=None)` | CID-to-pin metadata map; empty listings are valid; an indirect pin reports its pinned root in `through` |
| `block_stat(cid)` | Reported CID and block size, not independent byte verification |

`KuboRejectedError` covers invalid client configuration/arguments, rejected HTTP
requests (including disallowed redirects) and explicit RPC/pin errors. Kubo sends
most command errors, such as an invalid CID or `pin_rm`/`pin_ls` on an unpinned
CID, as HTTP 500 with a JSON error body; a well-formed one with code 0 (normal),
1 (client) or 4 (forbidden) is rejected.
`KuboUnavailableError` covers timeouts/transport failures, HTTP 408/429/502-504,
any other HTTP 500 (implementation errors, rate limits, Kubo-internal context
timeouts, non-Kubo bodies) and invalid/incomplete responses. The total-operation
timeout includes upload time, so raise it for large inputs. Errors expose only
operation/category/status, never remote error text. Cancellation propagates.
**No automatic retries:** a failed or
timed-out mutation may already have stored blocks or changed pins; reconcile its
outcome rather than blindly replaying it. CAR import follows in the final #61 slice.

Kubo can put a late error in an HTTP trailer after status 200. The default
HTTP/1.1 transport uses public `httpcore`/`h11` interfaces to detect it before
returning a result; plain HTTPX otherwise drops these trailers. There is no
private monkeypatch or replacement TLS/parser stack. Use a direct endpoint or a
proxy that preserves trailers. Responses are read completely within the budget;
compressed responses are rejected, and raw server bodies/headers should not be logged.
See the pinned [RPC commands](https://github.com/ipfs/kubo/tree/v0.43.1/core/commands)
and [late-error emitter](https://github.com/ipfs/go-ipfs-cmds/blob/v0.16.1/http/responseemitter.go).

```bash
uv run --frozen pytest tests/unit/test_kubo*.py -q
```

MockTransport covers the five standard methods; local wire-level tests exercise actual
chunked HTTP trailers, fragmentation, pooling and privacy without external services.
CAR import and the opt-in full RPC integration check follow separately.

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
