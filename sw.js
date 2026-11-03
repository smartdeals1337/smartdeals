// Phone alerts for smartdealsclub.com (push_alerts.py on the server sends them).
// Shows the alert, and a tap opens the deal on the page (never Amazon directly).
// No offline cache: the page must always show live prices.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (_) { d = { body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.title || "SmartDeals Club", {
    body: d.body || "",
    icon: "/icon-192.png",
    badge: "/badge.png",
    image: d.image || undefined,
    tag: d.tag || undefined,
    renotify: !!d.tag,
    data: { url: d.url || "/" },
  }));
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = new URL(e.notification.data && e.notification.data.url || "/", self.location.origin);
  url.searchParams.set("from", "alert");   // the page counts alert opens (GoatCounter)
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const w of wins) {
      if (new URL(w.url).origin === url.origin && "navigate" in w) {
        await w.focus();
        return w.navigate(url.href);
      }
    }
    return self.clients.openWindow(url.href);
  })());
});
