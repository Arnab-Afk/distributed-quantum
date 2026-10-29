export function formatStrk(units: string | number | undefined, decimals = 18): string {
  if (units == null || units === "") return "—";
  let raw: bigint;
  try {
    raw = BigInt(units);
  } catch {
    return "—";
  }
  const scale = 10n ** BigInt(decimals);
  const whole = raw / scale;
  const fraction = (raw % scale).toString().padStart(decimals, "0").replace(/0+$/, "");
  return fraction ? `${whole}.${fraction} STRK` : `${whole} STRK`;
}
