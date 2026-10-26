import { BILLING } from "@/constants";

/** A purchasable pack: a Stripe Price and the credits it grants. */
export interface CreditPack {
  priceId: string;
  /** Decimal string with up to 6 places, e.g. "10" or "2.5". */
  credits: string;
}

/** A paid (or awaiting payment) credit-pack Checkout Session from a webhook event. */
export interface CreditPackSession {
  sessionId: string;
  accountId: string;
  paid: boolean;
}

/** How a credit pack is paid: by card (and Stripe's other dynamic methods) or in stablecoins. */
export type CreditPaymentMethod = "card" | "crypto";

export interface LineItem {
  priceId: string;
  quantity: number;
}

const CREDITS_PATTERN = /^\d+(\.\d{1,6})?$/;
const PRICE_PATTERN = /^price_[A-Za-z0-9]+$/;
const MICRO = BigInt(1_000_000);
const ZERO = BigInt(0);

/**
 * Parses `STRIPE_CREDIT_PACKS`, e.g. "price_abc:10,price_def:50".
 * Throws on malformed entries so a misconfiguration fails loudly.
 */
export function parseCreditPacks(raw: string | undefined): CreditPack[] {
  if (!raw?.trim()) return [];
  return raw.split(",").map((entry) => {
    const [priceId, credits, ...rest] = entry.trim().split(":");
    if (rest.length || !PRICE_PATTERN.test(priceId ?? "") || !CREDITS_PATTERN.test(credits ?? "")) {
      throw new Error(`Invalid STRIPE_CREDIT_PACKS entry: "${entry.trim()}"`);
    }
    if (toMicro(credits) === ZERO) throw new Error(`Credit pack ${priceId} grants no credits`);
    return { priceId, credits };
  });
}

/** `STRIPE_STABLECOIN_PAYMENTS` turns stablecoin checkout on; anything but "true" leaves it off. */
export function stablecoinPaymentsEnabled(raw: string | undefined): boolean {
  return raw?.trim().toLowerCase() === "true";
}

/**
 * Payment methods for a credit-pack Checkout Session. Stripe shows stablecoins
 * on every Checkout once they are enabled in the Dashboard, so the card session
 * always excludes them; only an explicit stablecoin session offers them.
 */
export function checkoutPaymentMethods(method: CreditPaymentMethod):
  | { payment_method_types: string[] }
  | { excluded_payment_method_types: string[] } {
  return method === "crypto"
    ? { payment_method_types: [BILLING.STABLECOIN_PAYMENT_METHOD] }
    : { excluded_payment_method_types: [BILLING.STABLECOIN_PAYMENT_METHOD] };
}

/** Returns the credit-pack session an event completes, or null for any other event. */
export function creditPackSessionFromEvent(event: {
  type: string;
  data: { object: unknown };
}): CreditPackSession | null {
  if (!BILLING.CREDIT_PACK_EVENTS.includes(event.type)) return null;
  const session = event.data.object;
  if (field(session, "mode") !== "payment") return null;
  if (field(field(session, "metadata"), "kind") !== BILLING.CREDIT_PACK_KIND) return null;
  const sessionId = field(session, "id");
  const accountId = field(session, "client_reference_id");
  if (typeof sessionId !== "string" || typeof accountId !== "string") return null;
  return { sessionId, accountId, paid: field(session, "payment_status") === "paid" };
}

/**
 * The method that paid a session, from a Checkout Session retrieved with
 * `payment_intent.payment_method` expanded. Only stablecoins get their own
 * rail; cards and Stripe's other dynamic methods stay on the card rail.
 */
export function paymentMethodOfSession(session: unknown): CreditPaymentMethod {
  const type = field(field(field(session, "payment_intent"), "payment_method"), "type");
  return type === BILLING.STABLECOIN_PAYMENT_METHOD ? "crypto" : "card";
}

function field(value: unknown, key: string): unknown {
  return typeof value === "object" && value !== null && key in value
    ? Object.getOwnPropertyDescriptor(value, key)?.value
    : undefined;
}

/**
 * Credits granted by a session's line items. Prices come from Stripe, never
 * the client. Throws on a price that is not a configured pack.
 */
export function creditsForLineItems(
  items: readonly LineItem[],
  packs: readonly CreditPack[],
): string {
  const byPrice = new Map(packs.map((pack) => [pack.priceId, toMicro(pack.credits)]));
  let total = ZERO;
  for (const item of items) {
    const credits = byPrice.get(item.priceId);
    if (credits === undefined) throw new Error(`Price ${item.priceId} is not a credit pack`);
    total += credits * BigInt(item.quantity);
  }
  if (total === ZERO) throw new Error("Checkout Session grants no credits");
  return fromMicro(total);
}

function toMicro(credits: string): bigint {
  const [whole, fraction = ""] = credits.split(".");
  return BigInt(whole) * MICRO + BigInt(fraction.padEnd(6, "0"));
}

function fromMicro(micro: bigint): string {
  const whole = micro / MICRO;
  const fraction = (micro % MICRO).toString().padStart(6, "0").replace(/0+$/, "");
  return fraction ? `${whole}.${fraction}` : `${whole}`;
}
