// The portal's brand, read on the server for its tab and icon.

const BACKEND_URL = process.env.BACKEND_INTERNAL_URL || "http://api:8000";

export type PortalBrand = {
  client_name: string;
  agency_name: string;
  agency_logo_url: string | null;
  client_logo_url: string | null;
};

/** A GET to the API as the browser would make it: with the host it asked for,
 * since behind a gateway the API may answer by host. Null when out of reach. */
export async function apiGet(path: string, host: string | null): Promise<Response | null> {
  try {
    return await fetch(`${BACKEND_URL}${path}`, {
      headers: host ? { "x-forwarded-host": host } : {},
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
  } catch {
    return null;
  }
}

export async function portalBrand(slug: string, host: string | null): Promise<PortalBrand | null> {
  const res = await apiGet(`/api/portal/${encodeURIComponent(slug)}`, host);
  if (!res?.ok) return null;
  try {
    return (await res.json()) as PortalBrand;
  } catch {
    return null;
  }
}

/** The logo the portal shows: the client's, or the agency's while it has none. */
export function brandLogo(brand: PortalBrand): string | null {
  return brand.client_logo_url || brand.agency_logo_url;
}
