import "server-only";

import type Stripe from "stripe";
import { BACKEND, BILLING, ROUTES, UI } from "@/constants";
import { backendAssertion } from "@/features/auth/server/backend-assertion";
import { getSession } from "@/features/auth/server/session";
import {
  creditPackSessionFromEvent,
  creditsForLineItems,
  parseCreditPacks,
  type CreditPack,
} from "../lib/credit-packs";
import type { VerifiedEvent } from "../lib/webhook";
import type { CreditOffer, CreditsOverview } from "../types";
import { getStripeClient, getStripeConfig } from "./stripe";

interface CreditsConfig {
  stripe: Stripe;
  packs: CreditPack[];
  billingSecret: string;
}

interface BillingUser {
  id: string;
  email: string;
  stripeCustomerId?: string | null;
}

interface BackendBalance {
  balance: { available: string; held: string };
  circuit_job_cost: string;
}

/**
 * Credit packs are enabled only when Stripe billing is configured, at least
 * one pack is defined and the backend's billing secret is shared.
 */
export function getCreditsConfig(): CreditsConfig | null {
  const stripeConfig = getStripeConfig();
  const billingSecret = process.env.BILLING_INTERNAL_SECRET;
  const packs = parseCreditPacks(process.env.STRIPE_CREDIT_PACKS);
  if (
    !stripeConfig ||
    !billingSecret ||
    billingSecret.length < BILLING.MIN_BILLING_SECRET_LENGTH ||
    packs.length === 0
  ) {
    return null;
  }
  return { stripe: getStripeClient(stripeConfig.secretKey), packs, billingSecret };
}

let _offers: Promise<CreditOffer[]> | undefined;

/** Pack prices as Stripe shows them. Prices are immutable, so this is cached per process. */
function listOffers(config: CreditsConfig): Promise<CreditOffer[]> {
  _offers ??= Promise.all(
    config.packs.map(async (pack) => {
      const price = await config.stripe.prices.retrieve(pack.priceId);
      const amount = (price.unit_amount ?? 0) / 100;
      const formatted = new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: price.currency.toUpperCase(),
      }).format(amount);
      return { priceId: pack.priceId, credits: pack.credits, price: formatted };
    }),
  ).catch((error: unknown) => {
    _offers = undefined;
    throw error;
  });
  return _offers;
}

async function fetchBalance(user: BillingUser): Promise<BackendBalance> {
  const assertion = backendAssertion(user);
  if (!assertion) throw new Error("AGENT_AUTH_BRIDGE_SECRET is not configured");
  const res = await fetch(BACKEND.CREDITS.BALANCE, {
    headers: { Authorization: assertion },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Credit balance request failed: ${res.status}`);
  return res.json() as Promise<BackendBalance>;
}

export async function getCreditsOverview(user: BillingUser): Promise<CreditsOverview> {
  const config = getCreditsConfig();
  const [backend, offers] = await Promise.all([
    fetchBalance(user),
    config ? listOffers(config) : Promise.resolve([]),
  ]);
  return {
    available: backend.balance.available,
    held: backend.balance.held,
    circuitJobCost: backend.circuit_job_cost,
    offers,
  };
}

/** Starts a one-off Checkout Session for a configured pack and returns its URL. */
export async function createCreditCheckout(
  user: BillingUser,
  priceId: string,
  origin: string,
): Promise<string | null> {
  const config = getCreditsConfig();
  if (!config || !config.packs.some((pack) => pack.priceId === priceId)) return null;

  const returnUrl = (result: string) => {
    const url = new URL(ROUTES.SETTINGS, origin);
    url.searchParams.set(BILLING.CREDITS_RESULT_PARAM, result);
    return url.toString();
  };
  const session = await config.stripe.checkout.sessions.create({
    mode: "payment",
    line_items: [{ price: priceId, quantity: 1 }],
    client_reference_id: user.id,
    ...(user.stripeCustomerId
      ? { customer: user.stripeCustomerId }
      : { customer_email: user.email }),
    metadata: { kind: BILLING.CREDIT_PACK_KIND, userId: user.id },
    success_url: returnUrl(BILLING.CHECKOUT_SUCCESS),
    cancel_url: returnUrl(BILLING.CHECKOUT_CANCELLED),
  });
  return session.url;
}

/**
 * Credits a paid credit-pack session. Returns false for every other event so
 * it reaches the subscription handler. Throws so Stripe retries on failure.
 */
export async function handleCreditPackEvent(event: VerifiedEvent): Promise<boolean> {
  const session = creditPackSessionFromEvent(event);
  if (!session) return false;
  // Delayed payment methods complete unpaid; async_payment_succeeded follows.
  if (!session.paid) return true;

  const config = getCreditsConfig();
  if (!config)
    throw new Error("Received a credit-pack payment but credit packs are not configured");

  // The amount comes from Stripe's record of what was bought, never the client.
  const lineItems = await config.stripe.checkout.sessions.listLineItems(session.sessionId, {
    limit: 100,
  });
  const items = lineItems.data.map((item) => ({
    priceId: item.price?.id ?? "",
    quantity: item.quantity ?? 0,
  }));
  const credits = creditsForLineItems(items, config.packs);

  const res = await fetch(BACKEND.CREDITS.PURCHASES, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      [BILLING.BILLING_SECRET_HEADER]: config.billingSecret,
    },
    body: JSON.stringify({
      checkout_session_id: session.sessionId,
      account_id: session.accountId,
      credits,
      stripe_event_id: event.id,
      price_id: items[0]?.priceId ?? null,
    }),
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`Backend rejected credit purchase ${session.sessionId}: ${res.status}`);
  }
  return true;
}

// ---------------------------------------------------------------------------
// Route handlers' service layer
// ---------------------------------------------------------------------------

export async function creditsOverviewResponse(): Promise<Response> {
  const session = await getSession();
  if (!session?.user) return Response.json({ error: UI.CREDITS.ERROR }, { status: 401 });
  try {
    return Response.json(await getCreditsOverview(session.user));
  } catch {
    return Response.json({ error: UI.CREDITS.ERROR }, { status: 502 });
  }
}

export async function creditCheckoutResponse(request: Request): Promise<Response> {
  const session = await getSession();
  if (!session?.user) return Response.json({ error: UI.CREDITS.ERROR }, { status: 401 });
  const body: unknown = await request.json().catch(() => null);
  const priceId =
    typeof body === "object" && body !== null && "priceId" in body ? body.priceId : null;
  if (typeof priceId !== "string") {
    return Response.json({ error: UI.CREDITS.UNAVAILABLE }, { status: 400 });
  }
  const url = await createCreditCheckout(session.user, priceId, new URL(request.url).origin);
  if (!url) return Response.json({ error: UI.CREDITS.UNAVAILABLE }, { status: 400 });
  return Response.json({ url });
}
