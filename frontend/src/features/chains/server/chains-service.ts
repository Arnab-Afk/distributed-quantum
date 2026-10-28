import "server-only";
import { BACKEND } from "@/constants";

/** Forwards the backend's public chain list; null when the backend is unreachable. */
export async function fetchChains(): Promise<Response | null> {
  try {
    return await fetch(BACKEND.CHAINS, { next: { revalidate: 300 } });
  } catch {
    return null;
  }
}
