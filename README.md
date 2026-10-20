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
