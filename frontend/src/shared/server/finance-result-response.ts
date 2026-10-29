export async function financeResultResponse(
  response: Response,
  download: boolean,
) {
  const data = await response.json();
  const headers = { "Cache-Control": "private, no-store" };
  if (!download || !response.ok) {
    return Response.json(data, { status: response.status, headers });
  }
  const provenance = data.result?.provenance;
  if (!provenance) {
    return Response.json(
      { detail: "Recorded price evidence is not available for this job." },
      { status: 404, headers },
    );
  }
  return new Response(JSON.stringify(provenance, null, 2), {
    headers: {
      ...headers,
      "Content-Type": "application/json; charset=utf-8",
      "Content-Disposition": 'attachment; filename="price-provenance.json"',
      "X-Content-Type-Options": "nosniff",
    },
  });
}
