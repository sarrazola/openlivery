// Pages whose open section (a tab, an account, a conversation) lives in the
// address. The route serving each is an optional catch-all, so a reload lands
// on the same section; the section itself is React state, and the address is
// written with history.replaceState and no state object, which Next.js folds
// into its router: usePathname follows, nothing is fetched, nothing re-mounts.

/** The segments after `base` in the current address, decoded. */
export function currentSections(base: string): string[] {
  if (typeof window === "undefined") return [];
  const path = window.location.pathname.replace(/\/+$/, "");
  if (path !== base && !path.startsWith(`${base}/`)) return [];
  return path.slice(base.length).split("/").filter(Boolean).map(decodeURIComponent);
}

/** Put `sections` after `base` in the address; empty ones are left out. The
 * query is dropped unless `search` carries one. A no-op when nothing moves. */
export function showSections(base: string, sections: (string | null | undefined)[], search = "") {
  if (typeof window === "undefined") return;
  const path = base + sections.filter((item): item is string => Boolean(item)).map((item) => `/${encodeURIComponent(item)}`).join("") || "/";
  if (window.location.pathname === path && window.location.search === search) return;
  window.history.replaceState(null, "", path + search + window.location.hash);
}
