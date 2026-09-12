// ============ Service Worker — سوق الحسينية ============
// استراتيجيات:
//   - static assets → cache-first + background update
//   - HTML navigation → stale-while-revalidate (يعمل offline لآخر صفحة)
//   - uploads images → cache-first مع حد أقصى 100 صورة (LRU)
//   - API → network-only
//   - Cloudinary → network-only (حجم كبير)

const CACHE_VERSION = 14;

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

// صفحات تُحاول precache أثناء التثبيت (قد تفشل لو لم يسجّل دخوله — نتجاهلها)
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

    // 2. precache key pages (best effort — يمكن أن تفشل إن لم يسجّل دخوله)
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

    // لا نستدعي skipWaiting تلقائياً — ننتظر تأكيد المستخدم
  })());
});


// ============ Activate ============
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    // احذف كل cache قديم
    const cacheNames = await caches.keys();
    const validCaches = [STATIC_CACHE, HTML_CACHE, IMAGE_CACHE];
    await Promise.all(
      cacheNames
        .filter(name => !validCaches.includes(name))
        .map(name => caches.delete(name))
    );

    // استلم السيطرة فوراً
    await self.clients.claim();
  })());
});


// ============ Message handler (للـ skipWaiting من side) ============
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});


// ============ Helper: trim cache (LRU تقريبية) ============
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

  // نتعامل فقط مع GET
  if (request.method !== 'GET') return;

  // Cloudinary — من الشبكة دائماً
  if (url.hostname.includes('cloudinary.com')) {
    event.respondWith(fetch(request));
    return;
  }

  // API — من الشبكة دائماً
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request));
    return;
  }

  // ============ HTML Navigation: Stale-While-Revalidate ============
  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      const cache = await caches.open(HTML_CACHE);
      const cached = await cache.match(request, { ignoreSearch: false });

      const networkPromise = fetch(request).then(response => {
        if (response.ok && response.type !== 'opaqueredirect') {
          cache.put(request, response.clone());
          trimCache(HTML_CACHE, MAX_HTML_ENTRIES);
        }
        return response;
      }).catch(() => null);

      if (cached) {
        // أعطِ المستخدم النسخة المحفوظة فوراً، وحدّث في الخلفية
        return cached;
      }

      // لا يوجد cache — انتظر الشبكة
      const fresh = await networkPromise;
      if (fresh) return fresh;

      // fallback → offline.html
      const offline = await caches.match('/static/offline.html');
      if (offline) return offline;

      return new Response('<h1>غير متصل</h1>', {
        status: 503,
        headers: { 'Content-Type': 'text/html; charset=utf-8' }
      });
    })());
    return;
  }

  // ============ Images: Cache-first + LRU ============
  if (request.destination === 'image') {
    event.respondWith((async () => {
      const cache = await caches.open(IMAGE_CACHE);
      const cached = await cache.match(request);
      if (cached) return cached;

      try {
        const response = await fetch(request);
        if (response.ok && url.pathname.startsWith('/static/uploads/')) {
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

  // ============ Static assets (CSS/JS/Fonts): Cache-first + background update ============
  if (['style', 'script', 'font'].includes(request.destination)) {
    event.respondWith((async () => {
      const cache = await caches.open(STATIC_CACHE);
      const cached = await cache.match(request);

      if (cached) {
        // حدّث في الخلفية بصمت
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

  // ============ Default: network ============
  event.respondWith(fetch(request));
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

    // إن كان التطبيق مفتوحاً — ركّز عليه وانتقل
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

    // افتح نافذة جديدة
    if (clients.openWindow) {
      return clients.openWindow(targetUrl);
    }
  })());
});


// ============ Notification close (تحليلات اختيارية) ============
self.addEventListener('notificationclose', event => {
  // يمكن لاحقاً إرسال event.notification.tag إلى السيرفر
});
