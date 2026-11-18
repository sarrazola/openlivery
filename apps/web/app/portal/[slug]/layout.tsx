import type { Metadata } from "next";
import { headers } from "next/headers";

// The portal is the client's space under the agency's brand, so its tab and a
// shared link carry the client's name and logo (the agency's while the client
// has none, as in the side panel), never the product's. Resolved on the server
// so the first paint and a link preview already show them.

const BACKEND_URL = process.env.BACKEND_INTERNAL_URL || "http://api:8000";

type PortalBrand = {
  client_name: string;
  agency_name: string;
  agency_logo_url: string | null;
  client_logo_url: string | null;
};

async function portalBrand(slug: string): Promise<PortalBrand | null> {
  // The API sees the host the browser asked for, as it would on the browser's
  // own request: behind a gateway it may answer by host.
  const incoming = await headers();
  const host = incoming.get("x-forwarded-host") || incoming.get("host");
  try {
    const res = await fetch(`${BACKEND_URL}/api/portal/${encodeURIComponent(slug)}`, {
      headers: { accept: "application/json", ...(host ? { "x-forwarded-host": host } : {}) },
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    return res.ok ? ((await res.json()) as PortalBrand) : null;
  } catch {
    return null;
  }
}

// The agency's initial on a neutral tile, like the login page shows when there
// is no logo.
function initialIcon(name: string): string {
  const letter = (name.trim().charAt(0) || "?").toUpperCase().replace(/[<>&"']/g, "");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#f1f2f5"/><text x="32" y="44" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="36" font-weight="700" fill="#102a43">${letter}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const brand = await portalBrand(slug);
  // Unknown portal or the API out of reach: a neutral tab rather than the
  // product's name and icon.
  if (!brand) return { title: { absolute: "" }, description: null, icons: [] };
  const logo = brand.client_logo_url || brand.agency_logo_url;
  return {
    title: { absolute: brand.client_name },
    description: null,
    icons: logo ? { icon: logo, apple: logo } : { icon: initialIcon(brand.agency_name) },
  };
}

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return children;
}
