import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import {
  buildCircuitRecord,
  countGatesFromQasm,
  countQubitsFromQasm,
  parseTagsInput,
} from "../src/features/ipfs/lib/circuit-record.ts";
import { circuitIpfsRecordSchema } from "../src/features/ipfs/schemas/vault-record.schema.ts";

const BELL = `OPENQASM 2.0;
include "qelib1.inc";

qreg q[2];
creg c[2];

h q[0];
cx q[0],q[1];
measure q -> c;
`;

describe("circuit-record builders", () => {
  test("counts qubits from qreg", () => {
    expect(countQubitsFromQasm(BELL)).toBe(2);
    expect(countQubitsFromQasm("qreg qubits[5];")).toBe(5);
    expect(countQubitsFromQasm("// no regs")).toBe(0);
  });

  test("counts gate lines excluding headers and measures", () => {
    expect(countGatesFromQasm(BELL)).toBe(2); // h + cx
  });

  test("parseTagsInput splits and trims", () => {
    expect(parseTagsInput(" bell,  entanglement , ")).toEqual([
      "bell",
      "entanglement",
    ]);
  });

  test("buildCircuitRecord fills required vault fields", () => {
    const record = buildCircuitRecord({
      name: "Bell",
      description: "Demo",
      qasm: BELL,
      author: "tester",
      tags: ["bell"],
      publishedAt: "2026-01-01T00:00:00.000Z",
    });

    expect(record.name).toBe("Bell");
    expect(record.description).toBe("Demo");
    expect(record.qasm).toContain("OPENQASM");
    expect(record.qubitCount).toBe(2);
    expect(record.gateCount).toBe(2);
    expect(record.author).toBe("tester");
    expect(record.publishedAt).toBe("2026-01-01T00:00:00.000Z");
    expect(record.tags).toEqual(["bell"]);

    const parsed = circuitIpfsRecordSchema.safeParse(record);
    expect(parsed.success).toBe(true);
  });

  test("buildCircuitRecord rejects empty name / short qasm", () => {
    expect(() =>
      buildCircuitRecord({ name: "  ", qasm: BELL, author: "a" }),
    ).toThrow("name");
    expect(() =>
      buildCircuitRecord({ name: "x", qasm: "short", author: "a" }),
    ).toThrow("QASM");
  });
});

describe("ShareCircuitToVaultButton SSR isolation", () => {
  test("public wrapper does not statically import Helia", () => {
    const src = readFileSync(
      join(
        import.meta.dir,
        "../src/features/ipfs/components/share-circuit-to-vault-button.tsx",
      ),
      "utf8",
    );
    expect(src).toContain('ssr: false');
    expect(src).toContain("next/dynamic");
    expect(src).not.toMatch(/from ["']helia["']/);
    expect(src).not.toMatch(/from ["']@helia\//);
  });

  test("new-run form wires the publish button", () => {
    const src = readFileSync(
      join(
        import.meta.dir,
        "../src/features/runs/components/run-create-form.tsx",
      ),
      "utf8",
    );
    expect(src).toContain("ShareCircuitToVaultButton");
    expect(src).toContain('qasm={circuit}');
  });
});
