export async function readApiError(
  response: Response,
  fallback: string,
): Promise<string> {
  const body: unknown = await response.json().catch(() => null);
  if (!body || typeof body !== "object" || !("detail" in body)) return fallback;
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) {
    const messages = body.detail.flatMap((error: unknown) =>
      error &&
      typeof error === "object" &&
      "msg" in error &&
      typeof error.msg === "string"
        ? [error.msg]
        : [],
    );
    if (messages.length) return messages.join("; ");
  }
  return fallback;
}
