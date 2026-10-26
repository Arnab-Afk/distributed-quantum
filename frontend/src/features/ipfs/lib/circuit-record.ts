import type { CircuitIPFSRecord } from "../types";

export type BuildCircuitRecordInput = {
  name: string;
  description?: string;
  qasm: string;
  author: string;
  tags?: string[];
  publishedAt?: string;
};

/** Count qubits from the first `qreg q[N]` (or any qreg) declaration. */
export function countQubitsFromQasm(qasm: string): number {
  const match = qasm.match(/\bqreg\s+\w+\s*\[\s*(\d+)\s*\]/i);
  if (!match?.[1]) return 0;
  return Number.parseInt(match[1], 10) || 0;
}

/**
 * Count gate-like statements (excludes headers, registers, measures, blanks, comments).
 * Matches the heuristic used on the new-run form stats bar.
 */
export function countGatesFromQasm(qasm: string): number {
  return qasm.split("\n").filter((line) => {
    const l = line.trim();
    if (!l || l.startsWith("//")) return false;
    const lower = l.toLowerCase();
    if (lower.startsWith("openqasm")) return false;
    if (lower.startsWith("include")) return false;
    if (lower.startsWith("qreg")) return false;
    if (lower.startsWith("creg")) return false;
    if (lower.startsWith("measure")) return false;
    return true;
  }).length;
}

export function parseTagsInput(raw: string): string[] {
  return raw
    .split(/[,]+/)
    .map((t) => t.trim())
    .filter(Boolean);
}

/** Build a vault circuit record for Helia JSON upload. */
export function buildCircuitRecord(
  input: BuildCircuitRecordInput,
): CircuitIPFSRecord {
  const name = input.name.trim();
  const qasm = input.qasm.trim();
  if (!name) throw new Error("Circuit name is required");
  if (qasm.length < 10) throw new Error("Circuit QASM is too short");

  return {
    cid: "",
    name,
    description: (input.description ?? "").trim(),
    qasm,
    qubitCount: countQubitsFromQasm(qasm),
    gateCount: countGatesFromQasm(qasm),
    author: input.author.trim() || "anonymous",
    publishedAt: input.publishedAt ?? new Date().toISOString(),
    tags: input.tags ?? [],
  };
}
