/**
 * Push Notifications Manager
 *
 * Gerencia a subscription de Web Push Notifications no navegador.
 * Solicita permissão ao usuário e registra/remove subscriptions no servidor.
 */

const PushManager = {
    vapidPublicKey: null,
    swRegistration: null,
    isSubscribed: false,

    /**
     * Inicializa o gerenciador de push notifications
     */
    async init() {
        // Verificar suporte a push notifications
        if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
            console.log('[Push] Push notifications não suportado neste navegador');
            return;
        }

        try {
            // Obter chave VAPID do servidor
            const vapidResponse = await fetch('/api/push/vapid-key/');
            const vapidData = await vapidResponse.json();

            if (!vapidData.success) {
                console.log('[Push] VAPID não configurado no servidor');
                return;
            }

            this.vapidPublicKey = vapidData.vapid_public_key;

            // Registrar service worker
            this.swRegistration = await navigator.serviceWorker.register('/sw.js');
            console.log('[Push] Service Worker registrado');

            // Verificar se já está inscrito
            const subscription = await this.swRegistration.pushManager.getSubscription();
            this.isSubscribed = !(subscription === null);

            console.log('[Push] Usuário está inscrito:', this.isSubscribed);

            // Atualizar UI se necessário
            this.updateUI();

            console.log('[Push] Notification.permission:', Notification.permission);

            // Se já tiver permissão concedida e não estiver inscrito, inscrever automaticamente
            if (Notification.permission === 'granted' && !this.isSubscribed) {
                console.log('[Push] Permissão já concedida, inscrevendo...');
                await this.subscribe();
            }
            // Se nunca foi perguntado, solicitar permissão automaticamente
            else if (Notification.permission === 'default') {
                console.log('[Push] Permissão default, solicitando...');
                await this.subscribe();
            }
            // Se foi negado
            else if (Notification.permission === 'denied') {
                console.log('[Push] Permissão negada pelo usuário');
            }

        } catch (error) {
            console.error('[Push] Erro na inicialização:', error);
        }
    },

    /**
     * Solicita permissão e inscreve para receber push notifications
     */
    async subscribe() {
        try {
            // Verificar/solicitar permissão
            const permission = await Notification.requestPermission();

            if (permission !== 'granted') {
                console.log('[Push] Permissão negada');
                return false;
            }

            // Criar subscription
            const subscription = await this.swRegistration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this.urlBase64ToUint8Array(this.vapidPublicKey)
            });

            console.log('[Push] Subscription criada:', subscription);

            // Enviar para o servidor
            const response = await fetch('/api/push/subscribe/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCsrfToken()
                },
                body: JSON.stringify(subscription)
            });

            const data = await response.json();

            if (data.success) {
                this.isSubscribed = true;
                console.log('[Push] Inscrito com sucesso');
                this.updateUI();
                return true;
            } else {
                console.error('[Push] Erro ao salvar subscription:', data.error);
                return false;
            }

        } catch (error) {
            console.error('[Push] Erro ao inscrever:', error);
            return false;
        }
    },

    /**
     * Remove a subscription de push notifications
     */
    async unsubscribe() {
        try {
            const subscription = await this.swRegistration.pushManager.getSubscription();

            if (subscription) {
                // Remover do servidor
                await fetch('/api/push/unsubscribe/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCsrfToken()
                    },
                    body: JSON.stringify({ endpoint: subscription.endpoint })
                });

                // Remover localmente
                await subscription.unsubscribe();
            }

            this.isSubscribed = false;
            console.log('[Push] Desinscrito com sucesso');
            this.updateUI();
            return true;

        } catch (error) {
            console.error('[Push] Erro ao desinscrever:', error);
            return false;
        }
    },

    /**
     * Atualiza a UI baseado no estado da subscription
     */
    updateUI() {
        const subscribeBtn = document.getElementById('push-subscribe-btn');
        const unsubscribeBtn = document.getElementById('push-unsubscribe-btn');
        const statusSpan = document.getElementById('push-status');

        if (subscribeBtn) {
            subscribeBtn.style.display = this.isSubscribed ? 'none' : 'inline-block';
        }
        if (unsubscribeBtn) {
            unsubscribeBtn.style.display = this.isSubscribed ? 'inline-block' : 'none';
        }
        if (statusSpan) {
            statusSpan.textContent = this.isSubscribed ? 'Ativo' : 'Inativo';
            statusSpan.className = this.isSubscribed ? 'badge bg-success' : 'badge bg-secondary';
        }
    },

    /**
     * Converte chave VAPID de base64 para Uint8Array
     */
    urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding)
            .replace(/-/g, '+')
            .replace(/_/g, '/');

        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);

        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    },

    /**
     * Obtém o CSRF token do cookie
     */
    getCsrfToken() {
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
};

// Inicializar quando o DOM estiver pronto
document.addEventListener('DOMContentLoaded', () => {
    PushManager.init();
});

// Expor globalmente para uso em botões
window.PushManager = PushManager;
