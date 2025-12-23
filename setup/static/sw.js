/**
 * Service Worker para NossoPainel
 *
 * Gerencia push notifications e pode ser expandido para cache offline.
 */

const CACHE_NAME = 'nossopainel-v1';

// Instalação do service worker
self.addEventListener('install', (event) => {
    console.log('[SW] Service Worker instalado');
    self.skipWaiting();
});

// Ativação do service worker
self.addEventListener('activate', (event) => {
    console.log('[SW] Service Worker ativado');
    event.waitUntil(clients.claim());
});

// Receber push notifications
self.addEventListener('push', (event) => {
    console.log('[SW] Push recebido');

    let data = {
        title: 'NossoPainel',
        body: 'Você tem uma nova notificação',
        icon: '/static/assets/images/favicon/favicon.ico',
        badge: '/static/assets/images/favicon/favicon.ico',
        data: {}
    };

    if (event.data) {
        try {
            const payload = event.data.json();
            data = {
                title: payload.title || data.title,
                body: payload.body || data.body,
                icon: payload.icon || data.icon,
                badge: payload.badge || data.badge,
                data: payload.data || {}
            };
        } catch (e) {
            console.error('[SW] Erro ao parsear push data:', e);
        }
    }

    const options = {
        body: data.body,
        icon: data.icon,
        badge: data.badge,
        vibrate: [100, 50, 100],
        data: data.data,
        actions: [
            { action: 'open', title: 'Abrir' },
            { action: 'close', title: 'Fechar' }
        ],
        requireInteraction: true,
        tag: 'nossopainel-notification'
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

// Clique na notificação
self.addEventListener('notificationclick', (event) => {
    console.log('[SW] Notificação clicada:', event.action);

    event.notification.close();

    if (event.action === 'close') {
        return;
    }

    // Abrir URL especificada nos dados ou página principal
    const urlToOpen = event.notification.data?.url || '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then((clientList) => {
                // Se já existe uma aba aberta, focar nela
                for (const client of clientList) {
                    if (client.url.includes(self.location.origin) && 'focus' in client) {
                        client.navigate(urlToOpen);
                        return client.focus();
                    }
                }
                // Caso contrário, abrir nova aba
                if (clients.openWindow) {
                    return clients.openWindow(urlToOpen);
                }
            })
    );
});

// Fechar notificação
self.addEventListener('notificationclose', (event) => {
    console.log('[SW] Notificação fechada');
});
