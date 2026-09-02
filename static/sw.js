/* Service worker — La Cantina Fragapane
   Rend le site installable (PWA) et la carte consultable hors-ligne. */
const CACHE = 'cantina-v1';
const ESSENTIAL = ['/static/offline.html'];
const BEST_EFFORT = ['/', '/menu', '/static/css/style.css', '/static/js/main.js', '/static/favicon.svg', '/static/icon-192.png'];

self.addEventListener('install', (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(CACHE);
    await c.addAll(ESSENTIAL);                 // indispensable
    await Promise.allSettled(BEST_EFFORT.map((u) => c.add(u))); // best-effort (n'échoue pas l'install)
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;         // Google Fonts, Facebook… : non gérés
  if (url.pathname.startsWith('/admin')) return;           // jamais l'admin hors-ligne
  if (url.pathname === '/sw.js' || url.pathname === '/healthz') return;

  // Pages (navigation) : réseau d'abord, cache en secours, page hors-ligne en dernier recours
  if (req.mode === 'navigate') {
    e.respondWith((async () => {
      try {
        const res = await fetch(req);
        const c = await caches.open(CACHE); c.put(req, res.clone());
        return res;
      } catch (err) {
        return (await caches.match(req)) || (await caches.match('/static/offline.html'));
      }
    })());
    return;
  }

  // Ressources statiques : cache d'abord + mise à jour en tâche de fond
  e.respondWith((async () => {
    const cached = await caches.match(req);
    const network = fetch(req).then((res) => {
      if (res && res.status === 200) caches.open(CACHE).then((c) => c.put(req, res.clone()));
      return res;
    }).catch(() => null);
    return cached || (await network) || caches.match('/static/offline.html');
  })());
});
