/** A credit pack as offered in the UI. */
export interface CreditOffer {
  priceId: string;
  credits: string;
  /** Formatted pack price, e.g. "$10.00". */
  price: string;
  /** True when the pack can also be paid in stablecoins (flag on, USD price). */
  stablecoin: boolean;
}

export interface CreditsOverview {
  /** Decimal strings, so credit amounts never pass through floats. */
  available: string;
  held: string;
  /** "0" when circuit runs do not use credits. */
  circuitJobCost: string;
  offers: CreditOffer[];
}
