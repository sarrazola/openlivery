import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Maps a client's custom domain to its portal. When a request arrives on a
// verified custom domain, it is rewritten to that client's /portal/[slug] route
// so the browser URL stays on the client's own domain. Requests on the primary
// domain resolve to nothing and pass through untouched.

const BACKEND_URL = process.env.BACKEND_INTERNAL_URL || "http://api:8000";
const CACHE_TTL_MS = 60_000;

type Resolution = { slug: string | null; expires: number };
const cache = new Map<string, Resolution>();

async function resolveSlug(host: string): Promise<string | null> {
  const cached = cache.get(host);
  if (cached && cached.expires > Date.now()) return cached.slug;
  let slug: string | null = null;
  try {
    const res = await fetch(`${BACKEND_URL}/api/public/portal-domain?domain=${encodeURIComponent(host)}`, {
      headers: { accept: "application/json" },
    });
    if (res.ok) slug = ((await res.json()) as { portal_slug?: string }).portal_slug ?? null;
  } catch {
    slug = null;
  }
  cache.set(host, { slug, expires: Date.now() + CACHE_TTL_MS });
  return slug;
}

export async function proxy(request: NextRequest) {
  const rawHost = request.headers.get("x-forwarded-host") || request.headers.get("host") || "";
  const host = rawHost.split(":")[0].trim().toLowerCase();
  if (!host || host === "localhost" || host === "127.0.0.1") return NextResponse.next();

  const { pathname } = request.nextUrl;
  // Already inside a portal route (e.g. reached via the primary domain).
  if (pathname.startsWith("/portal/")) return NextResponse.next();

  const slug = await resolveSlug(host);
  if (!slug) return NextResponse.next();

  // The section (`/reports`, `/inbox/<conversation>`) follows the slug.
  const url = request.nextUrl.clone();
  url.pathname = `/portal/${slug}${pathname === "/" ? "" : pathname}`;
  return NextResponse.rewrite(url);
}

export const config = {
  // Run on page requests only; skip API, Next internals, the widget script and assets.
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|widget.js|.*\\.[^/]+$).*)"],
};
