import { ImageResponse } from "next/og";
import { apiGet, brandLogo, portalBrand } from "../brand";

// The portal's favicon: its logo with rounded corners, the way the side panel
// shows it. A browser draws a favicon square, so the corners are cut here.

const SIZE = 64;
const RADIUS = 16;
// What the renderer can draw. A WebP logo is served as it is, square.
const DRAWABLE = new Set(["image/png", "image/jpeg", "image/svg+xml"]);
const CACHE = { "Cache-Control": "public, max-age=300" };

export async function GET(request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const host = request.headers.get("x-forwarded-host") || request.headers.get("host");
  const brand = await portalBrand(slug, host);
  const path = brand && brandLogo(brand);
  const logo = path ? await apiGet(path, host) : null;
  if (!logo?.ok) return new Response(null, { status: 404 });
  const type = (logo.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
  const bytes = Buffer.from(await logo.arrayBuffer());
  if (type === "image/webp") {
    return new Response(bytes, { headers: { "Content-Type": type, "X-Content-Type-Options": "nosniff", ...CACHE } });
  }
  if (!DRAWABLE.has(type)) return new Response(null, { status: 404 });
  const src = `data:${type};base64,${bytes.toString("base64")}`;
  return new ImageResponse(
    (
      <div style={{ width: SIZE, height: SIZE, display: "flex", borderRadius: RADIUS, overflow: "hidden" }}>
        <img src={src} width={SIZE} height={SIZE} alt="" style={{ objectFit: "contain" }} />
      </div>
    ),
    { width: SIZE, height: SIZE, headers: CACHE },
  );
}
