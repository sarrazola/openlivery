import type { Metadata } from "next";
import { headers } from "next/headers";
import { brandLogo, portalBrand } from "./brand";

// The portal is the client's space under the agency's brand, so its tab and a
// shared link carry the client's name and logo (the agency's while the client
// has none, as in the side panel), never the product's. Resolved on the server
// so the first paint and a link preview already show them.

// The agency's initial on a neutral tile, like the login page shows when there
// is no logo.
function initialIcon(name: string): string {
  const letter = (name.trim().charAt(0) || "?").toUpperCase().replace(/[<>&"']/g, "");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="16" fill="#f1f2f5"/><text x="32" y="44" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="36" font-weight="700" fill="#102a43">${letter}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const incoming = await headers();
  const brand = await portalBrand(slug, incoming.get("x-forwarded-host") || incoming.get("host"));
  // Unknown portal or the API out of reach: a neutral tab rather than the
  // product's name and icon.
  if (!brand) return { title: { absolute: "" }, description: null, icons: [] };
  const logo = brandLogo(brand);
  return {
    title: { absolute: brand.client_name },
    description: null,
    // The tab gets the logo with its corners rounded (./brand-icon); a phone's
    // home screen rounds the icon itself, so it gets the logo as uploaded.
    icons: logo
      ? { icon: `/portal/${encodeURIComponent(slug)}/brand-icon`, apple: logo }
      : { icon: initialIcon(brand.agency_name) },
  };
}

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return children;
}
