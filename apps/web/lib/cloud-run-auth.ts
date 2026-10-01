/** Return a service identity token when running on Cloud Run. */
export async function getCloudRunIdentityToken(audience: string): Promise<string | null> {
  if (!process.env.K_SERVICE) return null;

  const metadataUrl =
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity" +
    `?audience=${encodeURIComponent(audience)}`;
  try {
    const response = await fetch(metadataUrl, {
      headers: { "Metadata-Flavor": "Google" },
      cache: "no-store",
      signal: AbortSignal.timeout(2_000),
    });
    if (!response.ok) return null;
    return (await response.text()).trim() || null;
  } catch {
    return null;
  }
}

export async function cloudRunAuthorizationHeaders(audience: string): Promise<Record<string, string>> {
  const token = await getCloudRunIdentityToken(audience);
  return token ? { Authorization: `Bearer ${token}` } : {};
}
