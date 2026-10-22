<div align="center">

# Distributed Quantum Services

**Quantum operations as discoverable peer-to-peer network services, orchestrated over py-libp2p and analyzed with Qiskit.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![Qiskit](https://img.shields.io/badge/Qiskit-1.x-6929C4?logo=ibm&logoColor=white)](https://qiskit.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/QMeshPy/distributed-quantum?color=brightgreen)](https://github.com/QMeshPy/distributed-quantum/commits/main)

</div>

---

## What this is

A research platform that treats quantum operations as network services. A FastAPI coordinator discovers worker peers over py-libp2p (GossipSub), compiles OpenQASM circuits into distributed execution plans, routes fragments to workers over libp2p streams, and assembles results with Qiskit statevector simulation. A Next.js operator console shows the peer network, job lifecycle, and quantum analysis live.

The same infrastructure powers a QAOA portfolio optimizer that benchmarks quantum against classical baselines.

[Watch the demo video](https://www.loom.com/share/8c5a546cb99a4a98996e738bf23c3e7a)

> **Scope:** this is a proof-of-concept on simulators, not a quantum hardware stack. Auth is dev-mode only.

### Applications

| Application | What it does | Status |
|---|---|---|
| Circuit orchestration | Normalize OpenQASM, plan, and execute distributed fragments across worker peers | Available |
| Financial modelling | QAOA portfolio benchmarks against classical optimization | Available |
| Risk and options | Simulated VaR, CVaR, credit-risk, and option-pricing experiments | Available |
| Molecular workflows | Drug-discovery research pipeline with simulated quantum stages | Experimental |

### Architecture

```
  Next.js operator console  ──(BFF proxy, REST)──▶  FastAPI coordinator
                                                          │
                                           py-libp2p runtime (Trio)
                                      Ed25519 host · GossipSub · stream RPC
                                                          │
                                       ┌──────────────────┼──────────────────┐
                                  Worker peer        Worker peer        Worker peer

  Persistence: Postgres (event-sourced) · MongoDB (projections) · JSONL (peer log)
```

### Headline result

97% of QAOA runtime is classical COBYLA parameter search, not the quantum circuit, so adding quantum nodes yields at most 1.03x speedup (Amdahl's Law). The advantage shows up in scaling: classical wins at 10 to 20 assets, and QAOA wins from about 40 assets (3.2x faster at 40, 9.5x at 60). The full analysis is in the [research paper draft](https://github.com/QMeshPy/documentations/blob/main/research/RESEARCH_PAPER_DRAFT.md).

---

## Quick start

**Prerequisites:** Python 3.11+ with [uv](https://github.com/astral-sh/uv), Node.js 20+, and Docker (full stack only).

**Backend** (http://localhost:8081, Swagger at `/docs`):

```bash
cd backend
make install
make run          # or `make run-clean` to reset runtime state
```

**Frontend** (http://localhost:3000):

```bash
cd frontend
npm install
npm run dev
```

Create `frontend/.env.local` first:

```
QUANTUM_BACKEND_URL=http://localhost:8081
NEXT_PUBLIC_TRIAL_DISABLED=true
```

**Full stack with Docker:**

```bash
cp .env.example .env     # add your Neon Postgres and Atlas MongoDB credentials
docker compose up --build
```

---

## Platform content node (Kubo)

The Compose stack includes **Kubo v0.43.1**, pinned by release tag and multi-platform
image digest. With current Docker Engine/Compose, start only the content node:

```bash
docker compose up -d --wait kubo
docker compose exec kubo ipfs --api=/ip4/127.0.0.1/tcp/5001 diag healthy
docker compose stop kubo
```

No provider credentials or backend startup are required. Compose may warn about
unset variables for the existing backend, even when starting only Kubo. If port
8080 is in use, run `KUBO_GATEWAY_PORT=18080 docker compose up -d --wait kubo`
(or set that variable in `.env`). The gateway remains loopback-only.

| Interface | Exposure |
|---|---|
| Swarm `4001/tcp` and `4001/udp` | Published for IPFS peers, separate from quantum-worker libp2p |
| Gateway `8080/tcp` | `127.0.0.1:8080` only; read content at `/ipfs/<CID>` |
| Admin RPC `5001/tcp` | **Not published** or proxied by Caddy; trusted Compose containers use `http://kubo:5001` |

The named `kubo_data` volume persists `/data/ipfs` across container recreation.
Stopping/removing a container does not remove it. Volume deletion permanently
removes this node's data and identity; do not use `docker compose down --volumes`
on a deployment unless you intend to delete **all** that project's named volumes.
The backend has no Kubo health dependency: content failures must not block compute.

`IPFS_PROFILE=server` applies **only when a new repository is initialized**. It
turns off mDNS and NAT port mapping and filters private swarm addresses. The
image sets `Addresses.API=/ip4/0.0.0.0/tcp/5001` and
`Addresses.Gateway=/ip4/0.0.0.0/tcp/8080` **inside the container**. Host exposure is
controlled by the mappings above. Existing repositories are not reconfigured;
back up the volume and review migrations/configuration before changing versions.
See the pinned [release](https://github.com/ipfs/kubo/releases/tag/v0.43.1),
[profile/configuration reference](https://github.com/ipfs/kubo/blob/v0.43.1/docs/config.md#server-profile),
[image entrypoint](https://github.com/ipfs/kubo/blob/v0.43.1/bin/container_daemon),
and [healthcheck](https://github.com/ipfs/kubo/blob/v0.43.1/Dockerfile).

Checks require Python 3.10+ (via uv) and Docker Compose with `up --wait` support:

```bash
uv run --no-project python -m unittest discover -s scripts -p test_kubo_compose.py -v
uv run --no-project python scripts/smoke_kubo.py
```

The first command checks deployment configuration without starting containers.
The optional live smoke test extracts only Kubo into a uniquely named temporary
project, ignores project `.env` values, uses random host ports and runs **offline**.
It checks health/profile, RPC host-binding absence, loopback gateway, matching
add/cat bytes and CIDs, and retained content/pin after container recreation. It
attempts to remove only its own container/network/volume, including on failure.
If cleanup also fails, it reports the disposable project label without replacing
the original error. Command failures identify the operation without dumping
possibly sensitive output. It needs no backend dependencies or private data;
its fixture is harmless public text.

The normal service is **online**: IPFS is public content-addressed networking,
not confidential storage. Never add private data expecting the CID to be secret.
Unpublished RPC is not authentication: containers on `backend_network` and Docker
administrators remain trusted. RPC authorization/hardening (#60), the Python
client (#61), automatic uploads and production hosting are separate work.

## Documentation

Long-form documentation lives in the **[QMeshPy/documentations](https://github.com/QMeshPy/documentations)** repository. Start with its [START_HERE](https://github.com/QMeshPy/documentations/blob/main/START_HERE.md) page.

| I want to... | Read |
|---|---|
| Contribute code | [CONTEXT.md](CONTEXT.md) (in this repo), then [ARCHITECTURE](https://github.com/QMeshPy/documentations/blob/main/ARCHITECTURE.md) |
| Understand the system design | [ARCHITECTURE](https://github.com/QMeshPy/documentations/blob/main/ARCHITECTURE.md), [design](https://github.com/QMeshPy/documentations/blob/main/design.md), [requirements](https://github.com/QMeshPy/documentations/blob/main/requirements.md) |
| Work on the frontend | [frontend/DESIGN.md](frontend/DESIGN.md) (in this repo) |
| Deploy it | [DEPLOYMENT-MANUAL.md](DEPLOYMENT-MANUAL.md) (in this repo), [Lightsail guide](https://github.com/QMeshPy/documentations/blob/main/LIGHTSAIL-DEPLOYMENT.md) |
| Read the research | [Paper draft](https://github.com/QMeshPy/documentations/blob/main/research/RESEARCH_PAPER_DRAFT.md), [math appendix](https://github.com/QMeshPy/documentations/blob/main/research/MATHEMATICAL_APPENDIX.md), [scaling strategy](https://github.com/QMeshPy/documentations/blob/main/research/QUANTUM_SCALING_STRATEGY.md) |
| Reproduce the benchmarks | [Implementation notes](https://github.com/QMeshPy/documentations/blob/main/technical/IMPLEMENTATION_NOTES.md), [benchmark results](https://github.com/QMeshPy/documentations/blob/main/technical/BENCHMARK.md), and the scripts in `backend/scripts/` |
| Understand the finance use case | [Financial modeling foundations](https://github.com/QMeshPy/documentations/blob/main/FINANCIAL_MODELING_FOUNDATIONS.md) |
| See where the project is going | [Future roadmap](https://github.com/QMeshPy/documentations/blob/main/FUTURE_ROADMAP.md) |

---

## Contributing

1. Fork the repo and create a feature branch.
2. Read [CONTEXT.md](CONTEXT.md). The Trio/asyncio bridge and event-sourced persistence have constraints that aren't obvious.
3. Run `make lint && make test` in `backend/` and `npm run build` in `frontend/` before opening a PR.
4. Keep changes surgical: match the existing style and don't refactor adjacent code.
