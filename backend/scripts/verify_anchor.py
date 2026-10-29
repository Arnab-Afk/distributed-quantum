"""Independently verify a provenance bundle's chain anchors (#21). No key is needed.

Usage, from backend/:
    uv run --frozen python scripts/verify_anchor.py BUNDLE.json --sender 0xANCHOR_ACCOUNT

BUNDLE.json is the bundle JSON (or the `{"bundle": ..., "bundle_hash": ...}` download).
For each anchor it recomputes the bundle commitment and Merkle proof locally, then
checks the transaction through the chain registry's RPC (overridable with the
network's env var, e.g. QB2_ETHEREUM_SEPOLIA_RPC_URL). Exits 0 only if all pass.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from requests import Session
from web3 import Web3

from quantum_backend_v2.chains.anchor import AnchorPayload, EvmAnchorAdapter
from quantum_backend_v2.chains.loader import load_chain_registry
from quantum_backend_v2.chains.rpc import resolve_rpc_url
from quantum_backend_v2.provenance.hashing import bundle_hash
from quantum_backend_v2.provenance.merkle import MerkleProof, verify_proof
from quantum_backend_v2.provenance.models import ProvenanceBundle


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--sender", required=True, help="published anchor account address")
    args = parser.parse_args()

    document = json.loads(args.bundle.read_text())
    bundle = ProvenanceBundle.model_validate(document.get("bundle", document))
    digest = bundle_hash(bundle)
    claimed = document.get("bundle_hash")
    if claimed is not None and claimed != digest:
        print(f"FAIL commitment: recomputed {digest}, bundle claims {claimed}")
        return 1
    print(f"commitment {digest}")
    if not bundle.anchors:
        print("FAIL no anchors recorded")
        return 1

    registry = load_chain_registry()
    ok = True
    for anchor in bundle.anchors:
        label = f"{anchor.chain} {anchor.tx_hash}"
        proof = MerkleProof(anchor.leaf_index, anchor.leaf_count, anchor.proof)
        if not verify_proof(digest, proof, anchor.merkle_root):
            print(f"FAIL {label}: Merkle proof does not reach root {anchor.merkle_root}")
            ok = False
            continue
        chain = registry.resolve(anchor.chain)
        with Session() as session:
            web3 = Web3(
                Web3.HTTPProvider(
                    resolve_rpc_url(chain, os.environ),
                    session=session,
                    request_kwargs={"timeout": 30},
                )
            )
            payload = AnchorPayload(anchor.merkle_root, anchor.leaf_count, anchor.hash_profile)
            check = EvmAnchorAdapter(chain, web3).check_anchor(anchor.tx_hash, payload, args.sender)
        passed = check.status == "confirmed"
        ok &= passed
        position = f"leaf {anchor.leaf_index + 1} of {anchor.leaf_count}"
        print(f"{'PASS' if passed else 'FAIL'} {label}: {check.status}, {position}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
