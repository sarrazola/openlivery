// The portal's service worker: it only shows push notifications and opens the
// conversation they point at. No fetch handling, no caching; the page keeps
// loading exactly as it does without it.
//
// The server (apps/api/app/services/webpush.py) sends {title, body, data}
// with data.conversation_id and data.portal_slug. When a portal window is
// visible the page is told instead, so the person sees it in the inbox they
// are looking at rather than as a system notification over it.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

function portalPath(data) {
  const slug = data && data.portal_slug ? encodeURIComponent(data.portal_slug) : "";
  const conversation = data && data.conversation_id ? encodeURIComponent(data.conversation_id) : "";
  if (!slug) return "/";
  return conversation ? `/portal/${slug}/inbox/${conversation}` : `/portal/${slug}`;
}

self.addEventListener("push", (event) => {
  let payload = { title: "", body: "", data: {} };
  try {
    payload = event.data ? event.data.json() : payload;
  } catch {
    payload = { title: "", body: event.data ? event.data.text() : "", data: {} };
  }
  const data = payload.data || {};
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const visible = windows.filter((client) => client.visibilityState === "visible");
      if (visible.length) {
        for (const client of visible) client.postMessage({ type: "push", payload });
        return undefined;
      }
      return self.registration.showNotification(payload.title || "New message", {
        body: payload.body || "",
        icon: "/icon.png",
        // One notification per conversation: a second message replaces the first.
        tag: data.conversation_id ? `conversation-${data.conversation_id}` : undefined,
        renotify: Boolean(data.conversation_id),
        data,
      });
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  const path = portalPath(data);
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      // An open portal window takes the click: it navigates itself without
      // reloading, which keeps whatever the person was doing.
      const client = windows.find((candidate) => candidate.url.includes("/portal/")) || windows[0];
      if (client) {
        client.postMessage({ type: "open", data });
        return client.focus();
      }
      return self.clients.openWindow(path);
    }),
  );
});
