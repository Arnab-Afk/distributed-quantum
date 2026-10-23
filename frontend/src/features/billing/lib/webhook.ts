/**
 * Records which Stripe event ids have been handled so a redelivered event is
 * acknowledged without being processed twice.
 */
export interface ProcessedEventStore {
  /** Returns false when the event id was already claimed. */
  claim(eventId: string): Promise<boolean>;
  /** Forgets a claim so Stripe's retry of a failed event is processed. */
  release(eventId: string): Promise<void>;
}

export interface VerifiedEvent {
  id: string;
  type: string;
  data: { object: unknown };
}

export interface StripeWebhookDeps {
  /** Verifies the Stripe signature and returns the parsed event; throws if invalid. */
  verify(payload: string, signature: string): Promise<VerifiedEvent>;
  store: ProcessedEventStore;
  /**
   * Handles events this app owns (credit packs). Returns true when the event
   * was fully handled and must not be forwarded; throws to have Stripe retry.
   */
  handle?(event: VerifiedEvent): Promise<boolean>;
  /** Hands the verified request to the subscription handler. */
  forward(request: Request): Promise<Response>;
}

export async function handleStripeWebhook(
  request: Request,
  deps: StripeWebhookDeps,
): Promise<Response> {
  const signature = request.headers.get("stripe-signature");
  if (!signature) {
    return Response.json({ error: "Missing Stripe signature" }, { status: 400 });
  }

  const payload = await request.text();

  let event: VerifiedEvent;
  try {
    event = await deps.verify(payload, signature);
  } catch {
    return Response.json({ error: "Invalid Stripe signature" }, { status: 400 });
  }
  const eventId = event.id;

  if (!(await deps.store.claim(eventId))) {
    return Response.json({ received: true, duplicate: true });
  }

  if (deps.handle) {
    try {
      if (await deps.handle(event)) return Response.json({ received: true });
    } catch (error) {
      await deps.store.release(eventId);
      throw error;
    }
  }

  // The body stream was consumed above, so rebuild the request for the handler.
  const forwarded = new Request(request.url, {
    method: request.method,
    headers: request.headers,
    body: payload,
  });

  try {
    const response = await deps.forward(forwarded);
    if (!response.ok) await deps.store.release(eventId);
    return response;
  } catch (error) {
    await deps.store.release(eventId);
    throw error;
  }
}
