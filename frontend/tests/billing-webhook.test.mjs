import { describe, expect, test } from "bun:test";

import { handleStripeWebhook } from "../src/features/billing/lib/webhook.ts";
import { customerIdFromEvent, isEntitled } from "../src/features/billing/lib/subscription.ts";
import {
  checkoutPaymentMethods,
  creditPackSessionFromEvent,
  creditsForLineItems,
  parseCreditPacks,
  paymentMethodOfSession,
  stablecoinPaymentsEnabled,
} from "../src/features/billing/lib/credit-packs.ts";

const WEBHOOK_URL = "http://localhost:3000/api/auth/stripe/webhook";

function memoryStore() {
  const claimed = new Set();
  return {
    claimed,
    async claim(id) {
      if (claimed.has(id)) return false;
      claimed.add(id);
      return true;
    },
    async release(id) {
      claimed.delete(id);
    },
  };
}

function delivery(eventId, signature = "t=1,v1=valid") {
  return new Request(WEBHOOK_URL, {
    method: "POST",
    headers: signature ? { "stripe-signature": signature } : {},
    body: JSON.stringify({ id: eventId }),
  });
}

function deps({ store = memoryStore(), status = 200, handle } = {}) {
  const forwarded = [];
  return {
    forwarded,
    store,
    handle,
    verify: async (payload, signature) => {
      if (signature !== "t=1,v1=valid") throw new Error("bad signature");
      return JSON.parse(payload);
    },
    forward: async (request) => {
      forwarded.push(await request.text());
      return new Response(null, { status });
    },
  };
}

describe("Stripe webhook", () => {
  test("rejects a delivery without a signature", async () => {
    const d = deps();
    const response = await handleStripeWebhook(delivery("evt_1", null), d);

    expect(response.status).toBe(400);
    expect(d.forwarded).toHaveLength(0);
  });

  test("rejects a delivery with an invalid signature", async () => {
    const d = deps();
    const response = await handleStripeWebhook(delivery("evt_1", "t=1,v1=forged"), d);

    expect(response.status).toBe(400);
    expect(d.forwarded).toHaveLength(0);
  });

  test("processes a replayed event exactly once", async () => {
    const d = deps();

    const first = await handleStripeWebhook(delivery("evt_1"), d);
    const replay = await handleStripeWebhook(delivery("evt_1"), d);

    expect(first.status).toBe(200);
    expect(replay.status).toBe(200);
    expect(await replay.json()).toEqual({ received: true, duplicate: true });
    expect(d.forwarded).toEqual([JSON.stringify({ id: "evt_1" })]);
  });

  test("lets Stripe retry an event whose processing failed", async () => {
    const store = memoryStore();

    const failed = await handleStripeWebhook(delivery("evt_2"), deps({ store, status: 400 }));
    expect(failed.status).toBe(400);
    expect(store.claimed.has("evt_2")).toBe(false);

    const retry = deps({ store });
    const retried = await handleStripeWebhook(delivery("evt_2"), retry);
    expect(retried.status).toBe(200);
    expect(retry.forwarded).toHaveLength(1);
  });
});

describe("credit-pack events", () => {
  function packEvent(eventId, { paid = true, type = "checkout.session.completed" } = {}) {
    return {
      id: eventId,
      type,
      data: {
        object: {
          id: "cs_test_1",
          mode: "payment",
          client_reference_id: "user-1",
          payment_status: paid ? "paid" : "unpaid",
          metadata: { kind: "credit_pack" },
        },
      },
    };
  }

  function packDelivery(event) {
    return new Request(WEBHOOK_URL, {
      method: "POST",
      headers: { "stripe-signature": "t=1,v1=valid" },
      body: JSON.stringify(event),
    });
  }

  function crediting(credited) {
    return async (event) => {
      const session = creditPackSessionFromEvent(event);
      if (!session) return false;
      if (session.paid) credited.push(session.sessionId);
      return true;
    };
  }

  test("a credit-pack event is handled once and never forwarded", async () => {
    const credited = [];
    const d = deps({ handle: crediting(credited) });

    const first = await handleStripeWebhook(packDelivery(packEvent("evt_pack")), d);
    const replay = await handleStripeWebhook(packDelivery(packEvent("evt_pack")), d);

    expect(first.status).toBe(200);
    expect(await replay.json()).toEqual({ received: true, duplicate: true });
    expect(credited).toEqual(["cs_test_1"]);
    expect(d.forwarded).toHaveLength(0);
  });

  test("an unpaid session is acknowledged without crediting", async () => {
    const credited = [];
    const d = deps({ handle: crediting(credited) });

    const response = await handleStripeWebhook(
      packDelivery(packEvent("evt_unpaid", { paid: false })),
      d,
    );

    expect(response.status).toBe(200);
    expect(credited).toEqual([]);
    expect(d.forwarded).toHaveLength(0);
  });

  test("subscription events still reach the subscription handler", async () => {
    const credited = [];
    const d = deps({ handle: crediting(credited) });

    await handleStripeWebhook(delivery("evt_sub"), d);

    expect(d.forwarded).toHaveLength(1);
    expect(credited).toEqual([]);
  });

  test("a replayed stablecoin payment is credited once", async () => {
    const credited = [];
    const d = deps({ handle: crediting(credited) });
    const event = packEvent("evt_usdc");
    event.data.object.payment_intent = { payment_method: { type: "crypto" } };

    await handleStripeWebhook(packDelivery(event), d);
    const replay = await handleStripeWebhook(packDelivery(event), d);

    expect(await replay.json()).toEqual({ received: true, duplicate: true });
    expect(credited).toEqual(["cs_test_1"]);
    expect(d.forwarded).toHaveLength(0);
  });

  test("a failed credit releases the claim so Stripe retries", async () => {
    const store = memoryStore();
    const failing = deps({
      store,
      handle: async () => {
        throw new Error("backend down");
      },
    });

    await expect(handleStripeWebhook(packDelivery(packEvent("evt_retry")), failing)).rejects.toThrow(
      "backend down",
    );
    expect(store.claimed.has("evt_retry")).toBe(false);

    const credited = [];
    const retry = await handleStripeWebhook(
      packDelivery(packEvent("evt_retry")),
      deps({ store, handle: crediting(credited) }),
    );
    expect(retry.status).toBe(200);
    expect(credited).toEqual(["cs_test_1"]);
  });
});

describe("credit packs", () => {
  test("parses configured packs", () => {
    expect(parseCreditPacks("price_abc:10, price_def:2.5")).toEqual([
      { priceId: "price_abc", credits: "10" },
      { priceId: "price_def", credits: "2.5" },
    ]);
    expect(parseCreditPacks(undefined)).toEqual([]);
    expect(parseCreditPacks("  ")).toEqual([]);
  });

  test("rejects malformed pack configuration", () => {
    for (const raw of ["price_abc", "abc:10", "price_abc:ten", "price_abc:0", "price_abc:1:2", "price_abc:1.1234567"]) {
      expect(() => parseCreditPacks(raw)).toThrow();
    }
  });

  test("credits come from Stripe's line items, not the client", () => {
    const packs = parseCreditPacks("price_abc:10,price_def:0.1");

    expect(creditsForLineItems([{ priceId: "price_abc", quantity: 1 }], packs)).toBe("10");
    expect(
      creditsForLineItems(
        [
          { priceId: "price_def", quantity: 3 },
          { priceId: "price_abc", quantity: 2 },
        ],
        packs,
      ),
    ).toBe("20.3");
    expect(() => creditsForLineItems([{ priceId: "price_evil", quantity: 1 }], packs)).toThrow();
    expect(() => creditsForLineItems([], packs)).toThrow();
  });

  test("recognises only paid-mode credit-pack sessions", () => {
    const session = {
      id: "cs_test_1",
      mode: "payment",
      client_reference_id: "user-1",
      payment_status: "paid",
      metadata: { kind: "credit_pack" },
    };
    const event = (type, object) => ({ type, data: { object } });

    expect(creditPackSessionFromEvent(event("checkout.session.completed", session))).toEqual({
      sessionId: "cs_test_1",
      accountId: "user-1",
      paid: true,
    });
    expect(
      creditPackSessionFromEvent(event("checkout.session.async_payment_succeeded", session))?.paid,
    ).toBe(true);
    expect(
      creditPackSessionFromEvent(event("checkout.session.completed", { ...session, mode: "subscription" })),
    ).toBeNull();
    expect(
      creditPackSessionFromEvent(event("checkout.session.completed", { ...session, metadata: {} })),
    ).toBeNull();
    expect(creditPackSessionFromEvent(event("invoice.paid", session))).toBeNull();
    expect(
      creditPackSessionFromEvent(
        event("checkout.session.completed", { ...session, client_reference_id: null }),
      ),
    ).toBeNull();
  });
});

describe("stablecoin payments", () => {
  test("are off unless the flag is exactly true", () => {
    expect(stablecoinPaymentsEnabled("true")).toBe(true);
    expect(stablecoinPaymentsEnabled(" TRUE ")).toBe(true);
    for (const raw of [undefined, "", "false", "1", "yes"]) {
      expect(stablecoinPaymentsEnabled(raw)).toBe(false);
    }
  });

  test("card checkout hides stablecoins; stablecoin checkout offers only them", () => {
    expect(checkoutPaymentMethods("card")).toEqual({ excluded_payment_method_types: ["crypto"] });
    expect(checkoutPaymentMethods("crypto")).toEqual({ payment_method_types: ["crypto"] });
  });

  test("the paying method is read from Stripe's PaymentIntent", () => {
    const paidWith = (type) => ({ payment_intent: { payment_method: { type } } });

    expect(paymentMethodOfSession(paidWith("crypto"))).toBe("crypto");
    expect(paymentMethodOfSession(paidWith("card"))).toBe("card");
    expect(paymentMethodOfSession(paidWith("link"))).toBe("card");
    // An unexpanded PaymentIntent id or a missing one falls back to card.
    expect(paymentMethodOfSession({ payment_intent: "pi_123" })).toBe("card");
    expect(paymentMethodOfSession({})).toBe("card");
  });
});

describe("subscription state", () => {
  test("active and trialing subscriptions unlock the platform", () => {
    expect(isEntitled(["active"])).toBe(true);
    expect(isEntitled(["canceled", "trialing"])).toBe(true);
    expect(isEntitled(["canceled", "past_due", "incomplete"])).toBe(false);
    expect(isEntitled([])).toBe(false);
  });

  test("reads the customer from subscription events only", () => {
    const object = { customer: "cus_123" };

    expect(customerIdFromEvent({ type: "customer.subscription.updated", data: { object } })).toBe("cus_123");
    expect(
      customerIdFromEvent({
        type: "checkout.session.completed",
        data: { object: { customer: { id: "cus_456" } } },
      }),
    ).toBe("cus_456");
    expect(customerIdFromEvent({ type: "invoice.paid", data: { object } })).toBeNull();
    expect(
      customerIdFromEvent({ type: "customer.subscription.deleted", data: { object: {} } }),
    ).toBeNull();
  });
});
