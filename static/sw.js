const CACHE_NAME = 'husayniyyah-cache-v10';
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
  '/static/icons/icon-96.png',
  '/static/icons/icon-144.png',
  '/static/icons/icon-192.png',
  '/static/icons/icon-384.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon-maskable.png',
  '/static/icons/apple-touch-icon.png',
  '/static/offline.html'
];

const PUBLIC_PATHS = [
  '/',
  '/market',
  '/stores',
  '/offers',
  '/search',
  '/product/',
  '/store/',
  '/reels',
  '/services',
  '/about',
  '/contact'
];

const PROTECTED_PATHS = [
  '/admin',
  '/my_stores',
  '/store',
  '/delivery'
];

const CACHEABLE_PATHS = [...PUBLIC_PATHS, ...PROTECTED_PATHS];

const API_CACHE_PATTERNS = [
  /^\/api\/products/,
  /^\/api\/stores/,
  /^\/api\/offers/,
  /^\/api\/categories/,
  /^\/api\/search/
];

const PAGES_TO_CACHE = [
  '/',
  '/market',
  '/stores',
  '/offers',
  '/reels',
  '/services',
  '/about',
  '/contact',
  '/offline.html'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return Promise.allSettled(
          STATIC_ASSETS.map(asset => cache.add(asset))
        ).then(() => {
          return Promise.allSettled(
            PAGES_TO_CACHE.map(page =>
              fetch(page, {cache: 'no-store'})
                .then(response => {
                  if (response.ok) cache.put(page, response);
                })
                .catch(() => {})
            )
          );
        });
      })
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames
          .filter(name => name !== CACHE_NAME)
          .map(name => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const { request } = event;

  if (request.method !== 'GET') return;

  if (request.mode === 'navigate') {
    const url = new URL(request.url);
    const isCacheable = CACHEABLE_PATHS.some(path => {
      if (path === '/') return url.pathname === '/';
      if (path.endsWith('/')) return url.pathname.startsWith(path);
      return url.pathname === path || url.pathname.startsWith(path);
    });

    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok && isCacheable) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => {
          return caches.match(request).then(cached => {
            if (cached) return cached;
            return caches.match('/static/offline.html');
          });
        })
    );
    return;
  }

  if (request.url.includes('/api/')) {
    const shouldCache = API_CACHE_PATTERNS.some(pattern => pattern.test(new URL(request.url).pathname));
    if (shouldCache) {
      event.respondWith(
        fetch(request)
          .then(response => {
            if (response && response.status === 200) {
              const copy = response.clone();
              caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
            }
            return response;
          })
          .catch(() => {
            return caches.match(request).then(cached => {
              if (cached) return cached;
              return new Response(JSON.stringify({ error: 'offline' }), {
                headers: { 'Content-Type': 'application/json' }
              });
            });
          })
      );
      return;
    }
  }

  if (request.destination === 'image' && request.url.includes('/static/uploads/')) {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  if (
    request.destination === 'style' ||
    request.destination === 'script' ||
    request.destination === 'image' ||
    request.destination === 'font'
  ) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) {
          fetch(request).then(response => {
            if (response.ok) {
              const clone = response.clone();
              caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
            }
          }).catch(() => {});
          return cached;
        }
        return fetch(request).then(response => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
          }
          return response;
        });
      })
    );
    return;
  }

  event.respondWith(fetch(request));
});

self.addEventListener('push', event => {
  console.log('Push received', event);
  let data = { title: 'سوق الحسينية', message: 'إشعار جديد', url: '/' };

  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data = { title: 'سوق الحسينية', message: event.data.text(), url: '/' };
    }
  }

  const options = {
    body: data.message || data.body,
    icon: data.icon || '/static/icons/icon-192.png',
    badge: data.badge || '/static/icons/icon-96.png',
    data: { url: data.url || '/' }
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'سوق الحسينية', options)
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification.data && event.notification.data.url ? event.notification.data.url : '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
      for (let client of windowClients) {
        if (client.url === url && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});
