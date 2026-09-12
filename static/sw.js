// ============ Service Worker — سوق الحسينية ============
// قاعدة ذهبية: لا تعترض cross-origin requests (Cloudinary، Google Fonts، إلخ)
// الاستراتيجيات:
//   - static assets (نفس الأصل) → cache-first + background update
//   - HTML navigation → stale-while-revalidate
//   - uploads images (نفس الأصل فقط) → cache-first مع LRU
//   - API → network-only
//   - cross-origin → network-only (بدون اعتراض)

const CACHE_VERSION = 15;

const STATIC_CACHE = `husayniyyah-static-v${CACHE_VERSION}`;
const HTML_CACHE   = `husayniyyah-html-v${CACHE_VERSION}`;
const IMAGE_CACHE  = `husayniyyah-images-v${CACHE_VERSION}`;

const MAX_HTML_ENTRIES  = 30;
const MAX_IMAGE_ENTRIES = 100;

const STATIC_ASSETS = [
  '/static/css/variables.css',
  '/static/css/base.css',
  '/static/css/layout.css',
  '/static/css/components.css',
  '/static/css/pages.css',
  '/static/css/cards.css',
  '/static/css/responsive.css',
  '/static/css/themes/dark/dark-mode.css',
  '/static/vendor/bootstrap/css/bootstrap.rtl.min.css',
  '/static/vendor/bootstrap-icons/bootstrap-icons.min.css',
  '/static/vendor/bootstrap/js/bootstrap.bundle.min.js',
  '/static/vendor/fonts/tajawal.css',
  '/static/js/offlineDB.js',
  '/static/js/localStore.js',
  '/static/js/navigation.js',
  '/static/icons/icon-96.png',
  '/static/icons/icon-144.png',
  '/static/icons/icon-192.png',
  '/static/icons/icon-384.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon-maskable.png',
  '/static/icons/apple-touch-icon.png',
  '/static/offline.html',
];

const PRECACHE_PAGES = [
  '/market',
  '/reels',
  '/stores',
  '/offers',
  '/services',
];


// ============ Install ============
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    // 1. cache static assets
    const staticCache = await caches.open(STATIC_CACHE);
    await Promise.allSettled(
      STATIC_ASSETS.map(asset =>
        staticCache.add(asset).catch(() => null)
      )
    );

    // 2. precache key pages (best effort)
    try {
      const htmlCache = await caches.open(HTML_CACHE);
      await Promise.allSettled(
        PRECACHE_PAGES.map(page =>
          fetch(page, { credentials: 'same-origin' })
            .then(res => { if (res.ok) htmlCache.put(page, res); })
            .catch(() => null)
        )
      );
    } catch (_) { /* ignore */ }

    // تفعيل SW الجديد فوراً (لإصلاح سريع)
    await self.skipWaiting();
  })());
});


// ============ Activate ============
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const cacheNames = await caches.keys();
    const validCaches = [STATIC_CACHE, HTML_CACHE, IMAGE_CACHE];
    await Promise.all(
      cacheNames
        .filter(name => !validCaches.includes(name))
        .map(name => caches.delete(name))
    );

    await self.clients.claim();
  })());
});


// ============ Message handler ============
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});


// ============ Helper: trim cache ============
async function trimCache(cacheName, maxEntries) {
  try {
    const cache = await caches.open(cacheName);
    const keys = await cache.keys();
    if (keys.length <= maxEntries) return;
    const toDelete = keys.length - maxEntries;
    for (let i = 0; i < toDelete; i++) {
      await cache.delete(keys[i]);
    }
  } catch (_) { /* ignore */ }
}


// ============ Fetch ============
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // ⚠️ IMPORTANT: cross-origin requests — لا تتدخل أبداً
  // هذا يشمل: Cloudinary, Google Fonts, OSM tiles, إلخ
  if (url.origin !== self.location.origin) {
    return; // اترك المتصفح يعالجها مباشرة
  }

  // نتعامل فقط مع GET (بعد فحص cross-origin)
  if (request.method !== 'GET') return;

  // API — من الشبكة دائماً
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request));
    return;
  }

  // ============ HTML Navigation: Stale-While-Revalidate ============
  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      const cache = await caches.open(HTML_CACHE);
      const cached = await cache.match(request);

      const networkPromise = fetch(request).then(response => {
        if (response.ok && response.type !== 'opaqueredirect') {
          cache.put(request, response.clone());
          trimCache(HTML_CACHE, MAX_HTML_ENTRIES);
        }
        return response;
      }).catch(() => null);

      if (cached) {
        return cached;
      }

      const fresh = await networkPromise;
      if (fresh) return fresh;

      const offline = await caches.match('/static/offline.html');
      if (offline) return offline;

      return new Response('<h1>غير متصل</h1>', {
        status: 503,
        headers: { 'Content-Type': 'text/html; charset=utf-8' }
      });
    })());
    return;
  }

  // ============ Images (نفس الأصل فقط): Cache-first + LRU ============
  if (request.destination === 'image') {
    event.respondWith((async () => {
      const cache = await caches.open(IMAGE_CACHE);
      const cached = await cache.match(request);
      if (cached) return cached;

      try {
        const response = await fetch(request);
        if (response.ok) {
          cache.put(request, response.clone());
          trimCache(IMAGE_CACHE, MAX_IMAGE_ENTRIES);
        }
        return response;
      } catch (_) {
        return new Response('', { status: 404, statusText: 'Offline' });
      }
    })());
    return;
  }

  // ============ Static assets (CSS/JS/Fonts) ============
  if (['style', 'script', 'font'].includes(request.destination)) {
    event.respondWith((async () => {
      const cache = await caches.open(STATIC_CACHE);
      const cached = await cache.match(request);

      if (cached) {
        fetch(request).then(response => {
          if (response.ok) cache.put(request, response);
        }).catch(() => null);
        return cached;
      }

      try {
        const response = await fetch(request);
        if (response.ok) cache.put(request, response.clone());
        return response;
      } catch (_) {
        return new Response('', { status: 404, statusText: 'Offline' });
      }
    })());
    return;
  }

  // ============ Default: network (no respondWith) ============
  // نترك المتصفح يعالجها مباشرة
});


// ============ Push Notifications ============
self.addEventListener('push', event => {
  let data = { title: 'سوق الحسينية', message: 'إشعار جديد', url: '/' };
  if (event.data) {
    try {
      data = event.data.json();
    } catch (_) {
      data = { title: 'سوق الحسينية', message: event.data.text(), url: '/' };
    }
  }

  const options = {
    body: data.message || data.body || '',
    icon: data.icon || '/static/icons/icon-192.png',
    badge: data.badge || '/static/icons/icon-96.png',
    vibrate: [100, 50, 100],
    dir: 'rtl',
    lang: 'ar',
    data: { url: data.url || '/' },
    tag: data.tag || 'husayniyyah-default',
    renotify: true,
    actions: [
      { action: 'open', title: 'فتح' },
      { action: 'close', title: 'إغلاق' },
    ],
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'سوق الحسينية', options)
  );
});


// ============ Notification click ============
self.addEventListener('notificationclick', event => {
  event.notification.close();
  if (event.action === 'close') return;

  const targetUrl = (event.notification.data && event.notification.data.url)
    ? event.notification.data.url
    : '/';

  event.waitUntil((async () => {
    const windowClients = await clients.matchAll({
      type: 'window',
      includeUncontrolled: true,
    });

    for (const client of windowClients) {
      if ('focus' in client) {
        try {
          await client.focus();
          if ('navigate' in client) {
            await client.navigate(targetUrl);
          }
          return;
        } catch (_) { /* continue */ }
      }
    }

    if (clients.openWindow) {
      return clients.openWindow(targetUrl);
    }
  })());
});
