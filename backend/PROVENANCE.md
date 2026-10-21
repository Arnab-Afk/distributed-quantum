# Provenance commitments (v1)

This is the first slice of issue #4: backward-compatible evidence models,
deterministic commitments and Merkle inclusion proofs. Job persistence, the
verification service/API and run-detail badge are follow-up slices. No storage
upload, chain transaction or automatically generated job evidence is added here.

Provenance establishes integrity of recorded evidence, **not** scientific
correctness, honest execution or execution on quantum hardware.

## Evidence models and compatibility

`ProvenanceBundle` retains its existing fields and adds optional `input_hash`,
`plan_id`, `fragment_result_hashes`, `oracle_refs`, `storage` and `anchors`.
Null/empty defaults let historical bundles load without inventing commitments.
Oracle, storage and anchor submodels reject unknown fields and are frozen.
Oracle decimal values are explicit strings, not binary floats.

An anchor records a chain identifier (use CAIP-2), transaction hash, root,
zero-based leaf index, original batch size, sibling hashes, hash profile and
optional public explorer URL. Storage references record backend, CID and optional
public URL/expiry. These are metadata, not successful verification results.
No chain adapters are selected here and no secrets belong in references.

## Canonical JSON

`provenance.hashing.canonical_json` accepts JSON primitives: null, booleans,
integers, finite floats, strings, lists and dictionaries with string keys. It
sorts keys by Unicode code point, preserves array order and Unicode text, uses
UTF-8, emits no insignificant whitespace, and uses Python's `json.dumps` escaping
and number rendering. Unicode is not normalized; lone surrogates are rejected.

This is a **Python JSON profile, not RFC 8785/JCS**. `1`, `1.0` and `-0.0`
retain their distinct representations; exponents may differ from JavaScript.
NaN/infinity are rejected. `Decimal` is rejected: producers must explicitly use
a documented decimal string. Summary/event payloads are checked before Pydantic
can silently convert non-finite floats to null or coerce keys/decimal values.
Other runtimes must reproduce these bytes, not just sort keys and use default JSON.

`hash_json(value)` returns lowercase SHA-256 hex of canonical bytes: 64 characters,
without a `0x` prefix. `bundle_hash(bundle)` hashes a versioned envelope:

```json
{"profile":"qmesh-provenance-sha256-v1","bundle":{}}
```

Replace the empty object with the Pydantic JSON-mode dump of the frozen v1 fields,
including defaults: `bundle_id`, `workflow_run_id`, `workflow_definition_id`,
`owner_user_id`, `events`, `artifact_refs`, `peer_log_refs`, `summary`,
`is_publishable`, `created_at`, `input_hash`, `plan_id`, `fragment_result_hashes`
and `oracle_refs`. Storage and anchors are excluded.

Nested typed fields are frozen too. Events include `event_id`, `workflow_run_id`,
`kind`, `actor_peer_id`, `actor_user_id`, `payload`, `occurred_at`; oracle references
include `provider`, `feed`, `round_id`, `value`, `observed_at`. All free-form summary
and event payload contents remain committed. Future optional typed model defaults
must not silently redefine v1. Format changes need a new profile and compatible
verification of old profiles.

Timestamps use Pydantic's JSON representation. Producers should consistently use
aware UTC timestamps: equivalent timezone representations are not normalized.
Freeze the snapshot before batching; changing a committed field (including the
publication flag) requires a new hash.

Storage and anchors can be attached after hashing without changing the commitment.
Including the root/proof in its own leaf would be self-referential. Consequently,
these attachments are NOT authenticated by the bundle hash and require separate
retrieval/transaction checks. Do not add a self-hash to the committed payload.

## Ordered Merkle tree

`MerkleTree` accepts a non-empty, ordered sequence of bundle digests. Preserve
order and batch size; do not sort or deduplicate.

- Leaf: `SHA256(0x00 || raw_32_byte_bundle_digest)`.
- Parent: `SHA256(0x01 || raw_left_hash || raw_right_hash)`.
- An odd final node at each level is promoted unchanged, without hashing it again.
- A singleton root is its framed leaf, not the input bundle digest.
- Empty batches are rejected.

Prefixes prevent ambiguity between leaves and internal nodes. `tree.proof(index)`
returns the index, original leaf count and bottom-up real siblings. Promoted levels
add no synthetic sibling. Index and level width determine left/right order and
when to consume a sibling. `verify_proof` checks the position-dependent path length
before hashing any untrusted siblings; extra or missing siblings are rejected.

This uses the non-empty tree shape and audit paths from
[RFC 6962 sections 2.1–2.1.1](https://www.rfc-editor.org/rfc/rfc6962#section-2.1),
not the full Certificate Transparency protocol (and empty batches remain invalid).
Promotion was chosen during pre-merge v1 review, replacing duplicate-last before
the profile is frozen for #21. It removes the duplicate-padding ambiguity where
`[A,B,C]` and `[A,B,C,C]` have the same root. It does not deduplicate batches or
prove that recorded results are honest. Preserve ordered batch metadata and size.
An individual inclusion proof cannot authenticate the supplied size independently:
opaque siblings conceal their subtree sizes. #21 must authenticate batch metadata
alongside the root if exact cardinality is claimed.

Roots/proofs from the earlier, unmerged duplicate-last draft are not interchangeable
with this construction. Regenerate draft fixtures/batches; do not reinterpret old
anchored roots. Any change after this profile is released requires a new profile.

## Ethereum handoff (#21)

Ethereum can record a SHA-256 root as `bytes32`. This tree is **not OpenZeppelin
MerkleProof-compatible** (Keccak, sorted pairs). If on-chain verification is needed,
agree on an explicitly versioned compatible profile or implement this exact
positional SHA-256 verifier. Do not reinterpret v1 roots as OpenZeppelin roots.

Chain choice, transaction submission and scheduled batching belong to #21 and
its #2 registry dependency. This slice does not implement those operations.
A valid local proof alone does not establish that any transaction exists.

## Tests

From `backend/`, without MongoDB, wallets or external services:

```bash
uv run pytest tests/unit/test_provenance.py tests/unit/test_provenance_flow.py -q
```

Coverage includes golden JSON bytes/hashes, independent Node-crypto bundle/tree
vectors, old-bundle round trips, unsupported values, frozen v1 fields, every leaf
at sizes 1–33 and randomized batches through 513 leaves, and tampered proofs.
A real Qiskit/BSON round trip checks serialization with multiple anchor fixtures;
those fixtures are not actual transactions or storage uploads.
