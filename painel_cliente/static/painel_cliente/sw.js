/**
 * Service Worker - Painel do Cliente
 *
 * Estrategias de cache:
 * - Cache First: Assets estaticos (CSS, JS, imagens)
 * - Network First: APIs e dados dinamicos
 * - Stale While Revalidate: Conteudo que pode ser atualizado em background
 */

'use strict';

const CACHE_VERSION = 'v1.2.0';
const STATIC_CACHE = `painel-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `painel-dynamic-${CACHE_VERSION}`;
const API_CACHE = `painel-api-${CACHE_VERSION}`;

// Assets to cache immediately on install
const STATIC_ASSETS = [
  // CSS
  '/static/painel_cliente/css/variables.css',
  '/static/painel_cliente/css/base.css',
  '/static/painel_cliente/css/components.css',
  '/static/painel_cliente/css/utilities.css',
  '/static/painel_cliente/css/animations.css',
  '/static/painel_cliente/css/dark-mode.css',
  // JS
  '/static/painel_cliente/js/app.js',
  '/static/painel_cliente/js/toast.js',
  // Icons
  '/static/painel_cliente/icons/icon-192.png',
  '/static/painel_cliente/icons/icon-512.png',
  // Fonts (Google Fonts are cached dynamically)
];

// Pages to cache for offline access
const OFFLINE_PAGES = [
  '/painel/',
  '/painel/offline/',
];

// URLs to always fetch from network
const NETWORK_ONLY = [
  '/painel/api/',
  '/painel/webhook/',
  '/admin/',
];

// URLs to cache with network-first strategy
const NETWORK_FIRST_URLS = [
  '/painel/dashboard/',
  '/painel/pagamento/',
  '/painel/perfil/',
  '/painel/historico/',
];

/**
 * Install event - cache static assets
 */
self.addEventListener('install', (event) => {
  console.log('[SW] Installing Service Worker...');

  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('[SW] Caching static assets...');
        // Don't fail install if some assets fail to cache
        return Promise.allSettled(
          STATIC_ASSETS.map(url =>
            cache.add(url).catch(err => console.warn(`[SW] Failed to cache: ${url}`, err))
          )
        );
      })
      .then(() => {
        console.log('[SW] Static assets cached');
        // Force immediate activation
        return self.skipWaiting();
      })
      .catch((error) => {
        console.error('[SW] Install failed:', error);
      })
  );
});

/**
 * Activate event - clean up old caches
 */
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating Service Worker...');

  event.waitUntil(
    Promise.all([
      // Clean old caches
      caches.keys().then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((cacheName) => {
              return cacheName.startsWith('painel-') &&
                     cacheName !== STATIC_CACHE &&
                     cacheName !== DYNAMIC_CACHE &&
                     cacheName !== API_CACHE;
            })
            .map((cacheName) => {
              console.log('[SW] Deleting old cache:', cacheName);
              return caches.delete(cacheName);
            })
        );
      }),
      // Take control of all pages immediately
      self.clients.claim()
    ]).then(() => {
      console.log('[SW] Service Worker activated');
    })
  );
});

/**
 * Fetch event - handle requests
 */
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip cross-origin requests (except fonts)
  if (!url.origin.includes(self.location.origin) &&
      !url.origin.includes('fonts.googleapis.com') &&
      !url.origin.includes('fonts.gstatic.com')) {
    return;
  }

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Network only for specific URLs
  if (NETWORK_ONLY.some(path => url.pathname.startsWith(path))) {
    event.respondWith(fetch(request));
    return;
  }

  // Static assets - Cache First
  if (isStaticAsset(url)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // Google Fonts - Cache First with dynamic cache
  if (url.origin.includes('fonts.googleapis.com') ||
      url.origin.includes('fonts.gstatic.com')) {
    event.respondWith(cacheFirst(request, DYNAMIC_CACHE));
    return;
  }

  // HTML pages - Network First with offline fallback
  if (request.headers.get('Accept')?.includes('text/html')) {
    event.respondWith(networkFirstWithOffline(request));
    return;
  }

  // Default - Stale While Revalidate
  event.respondWith(staleWhileRevalidate(request, DYNAMIC_CACHE));
});

/**
 * Check if URL is a static asset
 */
function isStaticAsset(url) {
  const staticExtensions = ['.css', '.js', '.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp', '.woff', '.woff2'];
  return staticExtensions.some(ext => url.pathname.endsWith(ext)) ||
         url.pathname.includes('/static/');
}

/**
 * Cache First strategy
 */
async function cacheFirst(request, cacheName) {
  const cachedResponse = await caches.match(request);

  if (cachedResponse) {
    return cachedResponse;
  }

  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, networkResponse.clone());
    }

    return networkResponse;
  } catch (error) {
    console.error('[SW] Cache first failed:', error);
    throw error;
  }
}

/**
 * Network First with offline fallback
 */
async function networkFirstWithOffline(request) {
  try {
    const networkResponse = await fetch(request);

    // Cache successful responses
    if (networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, networkResponse.clone());
    }

    return networkResponse;
  } catch (error) {
    console.log('[SW] Network failed, trying cache...');

    // Try cache
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    // Return offline page
    const offlinePage = await caches.match('/painel/offline/');
    if (offlinePage) {
      return offlinePage;
    }

    // Fallback offline response
    return new Response(
      `<!DOCTYPE html>
      <html lang="pt-BR">
      <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sem conexao</title>
        <style>
          * { margin: 0; padding: 0; box-sizing: border-box; }
          body {
            font-family: system-ui, -apple-system, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 20px;
            background: linear-gradient(135deg, #F5F3FF 0%, #EDE9FE 100%);
            color: #1E1B4B;
            text-align: center;
          }
          .icon {
            width: 80px;
            height: 80px;
            margin-bottom: 24px;
            color: #8B5CF6;
          }
          h1 { font-size: 24px; margin-bottom: 12px; }
          p { color: #64748B; margin-bottom: 24px; }
          button {
            padding: 12px 32px;
            font-size: 16px;
            font-weight: 600;
            color: white;
            background: linear-gradient(135deg, #8B5CF6, #EC4899);
            border: none;
            border-radius: 12px;
            cursor: pointer;
          }
        </style>
      </head>
      <body>
        <svg class="icon" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3m8.293 8.293l1.414 1.414" />
        </svg>
        <h1>Sem conexao</h1>
        <p>Verifique sua internet e tente novamente.</p>
        <button onclick="location.reload()">Tentar novamente</button>
      </body>
      </html>`,
      {
        status: 503,
        headers: { 'Content-Type': 'text/html; charset=utf-8' }
      }
    );
  }
}

/**
 * Stale While Revalidate strategy
 */
async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cachedResponse = await cache.match(request);

  const fetchPromise = fetch(request)
    .then((networkResponse) => {
      if (networkResponse.ok) {
        cache.put(request, networkResponse.clone());
      }
      return networkResponse;
    })
    .catch(() => null);

  return cachedResponse || await fetchPromise;
}

/**
 * Handle messages from clients
 */
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }

  if (event.data && event.data.type === 'CLEAR_CACHE') {
    event.waitUntil(
      caches.keys().then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((cacheName) => cacheName.startsWith('painel-'))
            .map((cacheName) => caches.delete(cacheName))
        );
      })
    );
  }
});

/**
 * Background sync for offline actions
 */
self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync:', event.tag);

  if (event.tag === 'sync-payment-status') {
    event.waitUntil(syncPaymentStatus());
  }
});

/**
 * Sync payment status when back online
 */
async function syncPaymentStatus() {
  // Get pending payment checks from IndexedDB
  // and sync with server
  console.log('[SW] Syncing payment status...');
}

/**
 * Push notifications
 */
self.addEventListener('push', (event) => {
  console.log('[SW] Push received:', event);

  let data = {
    title: 'Painel de Pagamentos',
    body: 'Voce tem uma nova notificacao',
    icon: '/static/painel_cliente/icons/icon-192.png',
    badge: '/static/painel_cliente/icons/icon-72.png',
    data: {}
  };

  if (event.data) {
    try {
      data = { ...data, ...event.data.json() };
    } catch (e) {
      data.body = event.data.text();
    }
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: data.icon,
      badge: data.badge,
      data: data.data,
      vibrate: [100, 50, 100],
      actions: [
        { action: 'open', title: 'Abrir' },
        { action: 'close', title: 'Fechar' }
      ]
    })
  );
});

/**
 * Notification click handler
 */
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification clicked:', event.action);

  event.notification.close();

  if (event.action === 'close') {
    return;
  }

  const urlToOpen = event.notification.data?.url || '/painel/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Check if there's already a window open
        for (const client of clientList) {
          if (client.url.includes('/painel/') && 'focus' in client) {
            client.navigate(urlToOpen);
            return client.focus();
          }
        }
        // Open new window
        if (clients.openWindow) {
          return clients.openWindow(urlToOpen);
        }
      })
  );
});

console.log('[SW] Service Worker loaded');
