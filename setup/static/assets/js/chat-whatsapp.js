/**
 * Chat WhatsApp - JavaScript
 * Gerencia a interface de chat similar ao WhatsApp Web
 */

(function() {
    'use strict';

    // Estado do chat
    let currentChat = null;
    let currentPhone = null;
    let replyToMessageId = null;
    let lastMessagesHash = null; // Para comparar se houve mudanças
    let isFirstLoad = true; // Flag para saber se é primeiro carregamento
    const DEFAULT_AVATAR = '/static/assets/images/avatar/default-avatar.svg';

    // === SSE (Server-Sent Events) ===
    let eventSource = null;
    let sseReconnectTimeout = null;
    const SSE_RECONNECT_DELAY = 5000;
    let sseConnected = false;

    // Cache de fotos de perfil para evitar requisições repetidas
    const profilePicCache = new Map();

    // Elementos DOM
    const chatList = document.getElementById('chat-list');
    const messagesContainer = document.getElementById('messages-container');
    const noChatSelected = document.getElementById('no-chat-selected');
    const activeChat = document.getElementById('active-chat');
    const chatAvatar = document.getElementById('chat-avatar');
    const chatName = document.getElementById('chat-name');
    const chatStatus = document.getElementById('chat-status');
    const messageInput = document.getElementById('message-input');
    const formSendMessage = document.getElementById('form-send-message');
    const searchInput = document.getElementById('search-contact');
    const fileInput = document.getElementById('file-input');
    const replyPreview = document.getElementById('reply-preview');
    const replyText = document.getElementById('reply-text');
    const chatSidebar = document.getElementById('chat-sidebar');

    // Inicializacao
    document.addEventListener('DOMContentLoaded', init);

    function init() {
        // Verificar se elementos existem (pagina de chat esta carregada)
        if (!chatList) return;

        loadChatList();
        setupEventListeners();
        connectSSE();  // SSE ao inves de polling
        setupVisibilityChange();

        // Solicitar permissao para notificacoes
        if ('Notification' in window && Notification.permission === 'default') {
            Notification.requestPermission();
        }

        // Inicializar icones feather apos carregamento
        if (typeof feather !== 'undefined') {
            feather.replace();
        }
    }

    function setupEventListeners() {
        // Enviar mensagem
        formSendMessage?.addEventListener('submit', handleSendMessage);

        // Auto-resize textarea
        messageInput?.addEventListener('input', autoResizeTextarea);

        // Enter para enviar (Shift+Enter para nova linha)
        messageInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                formSendMessage.dispatchEvent(new Event('submit'));
            }
        });

        // Busca de conversas
        searchInput?.addEventListener('input', filterChats);

        // Anexar arquivos
        document.getElementById('btn-attach-image')?.addEventListener('click', (e) => {
            e.preventDefault();
            fileInput.accept = 'image/*';
            fileInput.dataset.type = 'image';
            fileInput.click();
        });

        document.getElementById('btn-attach-file')?.addEventListener('click', (e) => {
            e.preventDefault();
            fileInput.accept = '*/*';
            fileInput.dataset.type = 'file';
            fileInput.click();
        });

        document.getElementById('btn-attach-audio')?.addEventListener('click', (e) => {
            e.preventDefault();
            fileInput.accept = 'audio/*';
            fileInput.dataset.type = 'audio';
            fileInput.click();
        });

        fileInput?.addEventListener('change', handleFileUpload);

        // Cancelar reply
        document.getElementById('btn-cancel-reply')?.addEventListener('click', cancelReply);

        // Atualizar mensagens manualmente
        document.getElementById('btn-refresh-messages')?.addEventListener('click', () => {
            if (currentPhone) loadMessages(currentPhone);
        });

        // Mobile: mostrar/esconder sidebar
        document.getElementById('btn-show-sidebar')?.addEventListener('click', () => {
            chatSidebar?.classList.remove('hidden');
        });

        document.getElementById('btn-close-sidebar')?.addEventListener('click', () => {
            chatSidebar?.classList.add('hidden');
        });
    }

    // Carrega lista de conversas
    async function loadChatList() {
        try {
            console.log('[Chat] Carregando lista de conversas...');
            const response = await fetch('/api/chat/list/');
            console.log('[Chat] Response status:', response.status);
            const data = await response.json();
            console.log('[Chat] Data received:', data);
            console.log('[Chat] Is array:', Array.isArray(data));

            if (response.ok && Array.isArray(data)) {
                console.log('[Chat] Renderizando', data.length, 'conversas');
                renderChatList(data);
            } else {
                console.log('[Chat] Erro - data.error:', data.error);
                chatList.innerHTML = `<div class="text-center py-5 text-danger">
                    <i data-feather="alert-circle" class="mb-2"></i>
                    <p>${data.error || 'Erro ao carregar conversas'}</p>
                </div>`;
            }
        } catch (error) {
            console.error('[Chat] Erro ao carregar lista de chats:', error);
            chatList.innerHTML = `<div class="text-center py-5 text-danger">
                <i data-feather="wifi-off" class="mb-2"></i>
                <p>Erro de conexao</p>
            </div>`;
        }

        // Atualizar icones
        if (typeof feather !== 'undefined') {
            feather.replace();
        }
    }

    // Extrai o ID do chat (pode ser objeto ou string)
    function getChatId(chat) {
        if (!chat.id) return '';
        // Se id for objeto, usar _serialized ou user
        if (typeof chat.id === 'object') {
            return chat.id._serialized || chat.id.user || '';
        }
        return chat.id;
    }

    function renderChatList(chats) {
        if (!chats.length) {
            chatList.innerHTML = `<div class="text-center py-5 text-muted">
                <i data-feather="inbox" style="width: 48px; height: 48px;" class="mb-2"></i>
                <p>Nenhuma conversa</p>
            </div>`;
            if (typeof feather !== 'undefined') feather.replace();
            return;
        }

        // Ordenar por ultima mensagem (usar t ao inves de timestamp)
        chats.sort((a, b) => (b.t || b.timestamp || 0) - (a.t || a.timestamp || 0));

        // Coletar IDs para carregar fotos
        const phonesToLoadPics = [];

        chatList.innerHTML = chats.map(chat => {
            const chatId = getChatId(chat);
            const name = chat.name || chat.contact?.name || chat.contact?.pushname || formatPhone(chatId);
            const lastMsg = chat.lastMessage?.body || chat.lastMessage || '';
            const unread = chat.unreadCount || 0;

            // Verificar se já temos a foto no cache ou na resposta da API
            let avatarSrc = DEFAULT_AVATAR;
            if (chat.profilePicUrl) {
                avatarSrc = chat.profilePicUrl;
                profilePicCache.set(chatId, chat.profilePicUrl);
            } else if (profilePicCache.has(chatId)) {
                avatarSrc = profilePicCache.get(chatId);
            } else {
                // Adicionar à lista para carregar depois
                phonesToLoadPics.push(chatId);
            }

            return `
                <div class="chat-item p-3 border-bottom ${currentPhone === chatId ? 'active' : ''}"
                     data-phone="${chatId}" data-name="${escapeHtml(name)}">
                    <div class="d-flex align-items-center">
                        <img src="${avatarSrc}"
                             class="rounded-circle chat-avatar me-3"
                             data-avatar-phone="${chatId}"
                             onerror="this.src='${DEFAULT_AVATAR}'"
                             alt="${escapeHtml(name)}">
                        <div class="flex-grow-1 min-width-0">
                            <div class="d-flex justify-content-between align-items-center">
                                <h6 class="mb-0 text-truncate">
                                    ${escapeHtml(name)}
                                </h6>
                                <small class="text-muted ms-2">${formatTime(chat.t || chat.timestamp)}</small>
                            </div>
                            <p class="mb-0 text-muted text-truncate small">
                                ${escapeHtml(truncateText(lastMsg, 40))}
                            </p>
                        </div>
                        ${unread > 0 ? `<span class="badge bg-success rounded-pill ms-2">${unread}</span>` : ''}
                    </div>
                </div>
            `;
        }).join('');

        // Adicionar eventos de clique
        chatList.querySelectorAll('.chat-item').forEach(item => {
            item.addEventListener('click', () => {
                selectChat(item.dataset.phone, item.dataset.name);
                // Mobile: esconder sidebar ao selecionar chat
                chatSidebar?.classList.add('hidden');
            });
        });

        // Atualizar icones
        if (typeof feather !== 'undefined') {
            feather.replace();
        }

        // Carregar fotos de perfil em background (primeiras 20 visíveis)
        if (phonesToLoadPics.length > 0) {
            loadProfilePicturesInBackground(phonesToLoadPics.slice(0, 20));
        }
    }

    // Seleciona uma conversa
    async function selectChat(phone, name) {
        currentPhone = phone;
        currentChat = { phone, name };

        // Resetar flags para novo chat
        isFirstLoad = true;
        lastMessagesHash = null;

        // UI: Mostrar chat ativo
        noChatSelected?.classList.add('d-none');
        activeChat?.classList.remove('d-none');
        activeChat?.classList.add('d-flex');

        // Atualizar header
        chatName.textContent = name || formatPhone(phone);
        chatAvatar.src = DEFAULT_AVATAR;

        // Marcar item como ativo na lista
        chatList.querySelectorAll('.chat-item').forEach(item => {
            item.classList.toggle('active', item.dataset.phone === phone);
        });

        // Carregar foto de perfil
        loadProfilePicture(phone);

        // Carregar mensagens
        await loadMessages(phone);

        // Limpar reply pendente
        cancelReply();

        // Focar no input
        messageInput?.focus();
    }

    async function loadProfilePicture(phone) {
        try {
            // Verificar cache primeiro
            if (profilePicCache.has(phone)) {
                const cachedUrl = profilePicCache.get(phone);
                if (cachedUrl) {
                    chatAvatar.src = cachedUrl;
                    return;
                }
            }

            const response = await fetch(`/api/chat/profile-pic/${encodeURIComponent(phone)}/`);
            const data = await response.json();
            const picUrl = data.profilePicUrl || data.eurl;

            if (picUrl) {
                chatAvatar.src = picUrl;
                profilePicCache.set(phone, picUrl);
            } else {
                // Marcar como sem foto para não tentar novamente
                profilePicCache.set(phone, '');
            }
        } catch (error) {
            console.log('Foto de perfil nao disponivel');
        }
    }

    // Carrega fotos de perfil em background com delay para não sobrecarregar
    async function loadProfilePicturesInBackground(phones) {
        for (let i = 0; i < phones.length; i++) {
            const phone = phones[i];

            // Pular se já está no cache
            if (profilePicCache.has(phone)) continue;

            try {
                const response = await fetch(`/api/chat/profile-pic/${encodeURIComponent(phone)}/`);
                const data = await response.json();
                const picUrl = data.profilePicUrl || data.eurl;

                if (picUrl) {
                    profilePicCache.set(phone, picUrl);
                    // Atualizar imagem no DOM
                    const imgEl = chatList.querySelector(`img[data-avatar-phone="${phone}"]`);
                    if (imgEl) {
                        imgEl.src = picUrl;
                    }
                } else {
                    // Marcar como sem foto
                    profilePicCache.set(phone, '');
                }
            } catch (error) {
                // Erro silencioso - manter avatar padrão
            }

            // Pequeno delay entre requisições para não sobrecarregar
            if (i < phones.length - 1) {
                await new Promise(resolve => setTimeout(resolve, 100));
            }
        }
    }

    async function loadMessages(phone, silent = false) {
        // Só mostrar spinner no primeiro carregamento (não no polling)
        if (!silent && isFirstLoad) {
            messagesContainer.innerHTML = `<div class="chat-loading">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Carregando...</span>
                </div>
            </div>`;
        }

        try {
            console.log('[Chat] Carregando mensagens do chat:', phone, silent ? '(silent)' : '');
            const response = await fetch(`/api/chat/messages/${encodeURIComponent(phone)}/`);
            const data = await response.json();

            if (response.ok && Array.isArray(data)) {
                // Criar hash simples para comparar se houve mudanças
                const newHash = data.length + '-' + (data[data.length - 1]?.id || '');

                // Só renderizar se houver mudanças ou for primeiro carregamento
                if (!silent || newHash !== lastMessagesHash) {
                    console.log('[Chat] Renderizando', data.length, 'mensagens');
                    const wasAtBottom = isScrolledToBottom();
                    renderMessages(data);
                    lastMessagesHash = newHash;

                    // Só rolar para baixo se já estava no final ou é primeiro carregamento
                    if (wasAtBottom || isFirstLoad) {
                        scrollToBottom();
                    }
                }
                isFirstLoad = false;
            } else if (!silent) {
                console.log('[Chat] Messages erro - data.error:', data.error);
                messagesContainer.innerHTML = `<div class="text-center text-danger py-5">
                    ${data.error || 'Erro ao carregar mensagens'}
                </div>`;
            }
        } catch (error) {
            console.error('[Chat] Erro ao carregar mensagens:', error);
            if (!silent) {
                messagesContainer.innerHTML = `<div class="text-center text-danger py-5">
                    Erro ao carregar mensagens
                </div>`;
            }
        }
    }

    // Verifica se o scroll está no final
    function isScrolledToBottom() {
        if (!messagesContainer) return true;
        const threshold = 100; // tolerância de 100px
        return messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight < threshold;
    }

    function renderMessages(messages) {
        if (!messages.length) {
            messagesContainer.innerHTML = `<div class="text-center text-muted py-5">
                <i data-feather="message-square" style="width: 48px; height: 48px;" class="mb-2"></i>
                <p>Nenhuma mensagem</p>
            </div>`;
            if (typeof feather !== 'undefined') feather.replace();
            return;
        }

        // Ordenar por timestamp
        messages.sort((a, b) => a.timestamp - b.timestamp);

        let lastDate = null;
        let html = '';

        messages.forEach(msg => {
            const msgDate = formatDate(msg.timestamp);

            // Separador de data
            if (msgDate !== lastDate) {
                html += `<div class="text-center my-3">
                    <span class="badge bg-light text-muted px-3 py-2">${msgDate}</span>
                </div>`;
                lastDate = msgDate;
            }

            const isSent = msg.fromMe;
            const time = formatTimeShort(msg.timestamp);

            html += `
                <div class="d-flex ${isSent ? 'justify-content-end' : 'justify-content-start'} mb-2">
                    <div class="message-bubble ${isSent ? 'msg-sent' : 'msg-received'} p-2 px-3 shadow-sm"
                         data-message-id="${msg.id}">
                        ${msg.quotedMsg ? renderQuotedMessage(msg.quotedMsg) : ''}
                        ${renderMessageContent(msg)}
                        <div class="d-flex justify-content-end align-items-center mt-1">
                            <small class="text-muted msg-status">${time}</small>
                            ${isSent ? renderMessageStatus(msg.ack) : ''}
                        </div>
                    </div>
                </div>
            `;
        });

        messagesContainer.innerHTML = html;

        // Adicionar eventos de clique para reply
        messagesContainer.querySelectorAll('.message-bubble').forEach(bubble => {
            bubble.addEventListener('dblclick', () => {
                const msgId = bubble.dataset.messageId;
                const msgText = bubble.querySelector('.msg-body')?.textContent || '';
                setReplyTo(msgId, msgText);
            });
        });

        // Adicionar eventos para visualizar imagens
        messagesContainer.querySelectorAll('.msg-image').forEach(img => {
            img.addEventListener('click', () => {
                const modal = document.getElementById('imageViewerModal');
                const modalImg = document.getElementById('image-viewer-img');
                if (modal && modalImg) {
                    modalImg.src = img.src;
                    new bootstrap.Modal(modal).show();
                }
            });
        });

        scrollToBottom();

        // Atualizar icones
        if (typeof feather !== 'undefined') {
            feather.replace();
        }
    }

    function renderQuotedMessage(quoted) {
        if (!quoted) return '';
        return `<div class="bg-light rounded p-2 mb-2 border-start border-3 border-success small">
            <p class="mb-0 text-truncate">${escapeHtml(quoted.body || 'Mensagem')}</p>
        </div>`;
    }

    function renderMessageContent(msg) {
        const type = msg.type || 'chat';
        // Extrair messageId corretamente (pode ser objeto ou string)
        const messageId = typeof msg.id === 'object' ? (msg.id._serialized || msg.id.id) : msg.id;

        if (type === 'image' || msg.mimetype?.startsWith('image/')) {
            // Para imagens, usar o endpoint de download ou preview base64
            // msg.body contém a legenda, NÃO a imagem
            // msg.mediaData?.preview pode ter preview base64
            // NOTA: NÃO usar deprecatedMms3Url - URLs expiram rapidamente e retornam 403
            let imgSrc = '';
            if (msg.mediaData?.preview) {
                // Preview base64 disponível
                imgSrc = `data:${msg.mimetype || 'image/jpeg'};base64,${msg.mediaData.preview}`;
            } else if (messageId) {
                // Usar API de download (sempre funciona)
                imgSrc = `/api/chat/download/${encodeURIComponent(messageId)}/`;
            }

            // A legenda pode estar em msg.body ou msg.caption
            const caption = msg.caption || (type === 'image' ? msg.body : '') || '';

            return `<div class="mb-1">
                ${imgSrc ? `<img src="${imgSrc}" class="img-fluid rounded msg-image" style="max-height: 300px; cursor: pointer;"
                     onerror="this.parentElement.innerHTML='<div class=\\'text-muted small\\'><i data-feather=\\'image\\'></i> Imagem não disponível</div>'">` : '<div class="text-muted small"><i data-feather="image"></i> Imagem</div>'}
                ${caption ? `<p class="mb-0 mt-1 msg-body">${escapeHtml(caption)}</p>` : ''}
            </div>`;
        }

        if (type === 'document' || type === 'application') {
            return `<div class="d-flex align-items-center">
                <i data-feather="file" class="me-2"></i>
                <a href="/api/chat/download/${encodeURIComponent(messageId)}/" class="text-decoration-none" target="_blank">
                    ${escapeHtml(msg.filename || 'Documento')}
                </a>
            </div>`;
        }

        if (type === 'audio' || type === 'ptt') {
            // Áudios precisam ser baixados via API
            const audioSrc = messageId ? `/api/chat/download/${encodeURIComponent(messageId)}/` : '';
            return `<div class="audio-message">
                ${audioSrc ? `<audio controls class="w-100" style="max-width: 250px;">
                    <source src="${audioSrc}" type="${msg.mimetype || 'audio/ogg'}">
                    Seu navegador não suporta áudio.
                </audio>` : '<span class="text-muted small"><i data-feather="mic"></i> Áudio</span>'}
            </div>`;
        }

        if (type === 'video') {
            const videoSrc = messageId ? `/api/chat/download/${encodeURIComponent(messageId)}/` : '';
            return `<div class="video-message">
                ${videoSrc ? `<video controls class="img-fluid rounded" style="max-height: 300px;">
                    <source src="${videoSrc}" type="${msg.mimetype || 'video/mp4'}">
                    Seu navegador não suporta vídeo.
                </video>` : '<span class="text-muted small"><i data-feather="video"></i> Vídeo</span>'}
                ${msg.caption ? `<p class="mb-0 mt-1 msg-body">${escapeHtml(msg.caption)}</p>` : ''}
            </div>`;
        }

        if (type === 'sticker') {
            let stickerSrc = '';
            if (msg.mediaData?.preview) {
                stickerSrc = `data:${msg.mimetype || 'image/webp'};base64,${msg.mediaData.preview}`;
            } else if (messageId) {
                stickerSrc = `/api/chat/download/${encodeURIComponent(messageId)}/`;
            }
            return `${stickerSrc ? `<img src="${stickerSrc}" class="img-fluid" style="max-width: 150px;"
                         onerror="this.style.display='none'">` : '<span class="text-muted">🎨 Sticker</span>'}`;
        }

        if (type === 'location') {
            const lat = msg.lat || 0;
            const lng = msg.lng || 0;
            return `<a href="https://www.google.com/maps?q=${lat},${lng}" target="_blank" class="text-decoration-none">
                <i data-feather="map-pin" class="me-1"></i> Ver localizacao
            </a>`;
        }

        // Mensagem de texto padrao
        return `<p class="mb-0 msg-body">${formatMessageText(msg.body || '')}</p>`;
    }

    function formatMessageText(text) {
        // Escapar HTML
        text = escapeHtml(text);

        // Converter URLs em links
        text = text.replace(
            /(https?:\/\/[^\s]+)/g,
            '<a href="$1" target="_blank" rel="noopener">$1</a>'
        );

        // Converter quebras de linha
        text = text.replace(/\n/g, '<br>');

        // Formatacao WhatsApp basica
        text = text.replace(/\*([^*]+)\*/g, '<strong>$1</strong>'); // *negrito*
        text = text.replace(/_([^_]+)_/g, '<em>$1</em>'); // _italico_
        text = text.replace(/~([^~]+)~/g, '<del>$1</del>'); // ~riscado~

        return text;
    }

    function renderMessageStatus(ack) {
        // 0: pending, 1: sent, 2: received, 3: read
        if (ack === undefined || ack === null) return '';

        const statuses = {
            0: { icon: 'clock', class: 'text-muted' },
            1: { icon: 'check', class: 'text-muted' },
            2: { icon: 'check-check', class: 'text-muted' },
            3: { icon: 'check-check', class: 'read' }
        };

        const status = statuses[ack] || statuses[0];

        if (ack >= 2) {
            return `<span class="ms-1 ${status.class}"><i data-feather="check" style="width: 12px; height: 12px;"></i><i data-feather="check" style="width: 12px; height: 12px; margin-left: -8px;"></i></span>`;
        }

        return `<span class="ms-1 ${status.class}"><i data-feather="check" style="width: 12px; height: 12px;"></i></span>`;
    }

    // Enviar mensagem
    async function handleSendMessage(e) {
        e.preventDefault();

        const message = messageInput.value.trim();
        if (!message || !currentPhone) return;

        const replyTo = replyToMessageId;

        // Limpar input
        messageInput.value = '';
        autoResizeTextarea();
        cancelReply();

        // Adicionar mensagem otimista
        appendOptimisticMessage(message);

        try {
            const response = await fetch('/api/chat/send-message/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({
                    phone: currentPhone,
                    message: message,
                    replyTo: replyTo
                })
            });

            if (!response.ok) {
                const data = await response.json();
                showToast(data.error || 'Erro ao enviar mensagem', 'danger');
            }
        } catch (error) {
            console.error('Erro ao enviar mensagem:', error);
            showToast('Erro de conexao', 'danger');
        }
    }

    function appendOptimisticMessage(text) {
        const now = new Date();
        const time = now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

        const html = `
            <div class="d-flex justify-content-end mb-2 optimistic-msg">
                <div class="message-bubble msg-sent p-2 px-3 shadow-sm">
                    <p class="mb-0 msg-body">${formatMessageText(text)}</p>
                    <div class="d-flex justify-content-end align-items-center mt-1">
                        <small class="text-muted msg-status">${time}</small>
                        <span class="ms-1 text-muted"><i data-feather="clock" style="width: 12px; height: 12px;"></i></span>
                    </div>
                </div>
            </div>
        `;
        messagesContainer.insertAdjacentHTML('beforeend', html);
        scrollToBottom();

        if (typeof feather !== 'undefined') {
            feather.replace();
        }
    }

    // Upload de arquivo
    async function handleFileUpload() {
        const file = fileInput.files[0];
        if (!file || !currentPhone) return;

        const fileType = fileInput.dataset.type || 'file';

        // Mostrar indicador de upload
        showToast('Enviando arquivo...', 'info');

        const formData = new FormData();
        formData.append('phone', currentPhone);
        formData.append('file', file);
        formData.append('type', fileType);

        try {
            const response = await fetch('/api/chat/send-file/', {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() },
                body: formData
            });

            if (response.ok) {
                showToast('Arquivo enviado!', 'success');
                // Recarregar mensagens
                loadMessages(currentPhone);
            } else {
                const data = await response.json();
                showToast(data.error || 'Erro ao enviar arquivo', 'danger');
            }
        } catch (error) {
            console.error('Erro ao enviar arquivo:', error);
            showToast('Erro de conexao', 'danger');
        }

        fileInput.value = '';
    }

    // Reply
    function setReplyTo(messageId, messageText) {
        replyToMessageId = messageId;
        replyText.textContent = truncateText(messageText, 50);
        replyPreview?.classList.remove('d-none');
        messageInput?.focus();
    }

    function cancelReply() {
        replyToMessageId = null;
        replyPreview?.classList.add('d-none');
    }

    // === SSE (Server-Sent Events) ===
    function connectSSE() {
        // Fechar conexao existente
        if (eventSource) {
            eventSource.close();
        }

        // Limpar timeout de reconexao
        if (sseReconnectTimeout) {
            clearTimeout(sseReconnectTimeout);
            sseReconnectTimeout = null;
        }

        console.log('[SSE] Conectando...');
        eventSource = new EventSource('/api/chat/sse/');

        eventSource.onopen = () => {
            console.log('[SSE] Conectado!');
            sseConnected = true;
        };

        eventSource.onmessage = (e) => {
            try {
                const event = JSON.parse(e.data);
                handleSSEEvent(event);
            } catch (err) {
                console.error('[SSE] Erro ao parsear evento:', err);
            }
        };

        eventSource.onerror = (e) => {
            console.warn('[SSE] Erro na conexao:', e);
            sseConnected = false;
            eventSource.close();

            // Reconectar apos delay (se pagina visivel)
            if (document.visibilityState === 'visible') {
                console.log(`[SSE] Reconectando em ${SSE_RECONNECT_DELAY}ms...`);
                sseReconnectTimeout = setTimeout(connectSSE, SSE_RECONNECT_DELAY);
            }
        };
    }

    function disconnectSSE() {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
        if (sseReconnectTimeout) {
            clearTimeout(sseReconnectTimeout);
            sseReconnectTimeout = null;
        }
        sseConnected = false;
        console.log('[SSE] Desconectado');
    }

    function handleSSEEvent(event) {
        console.log('[SSE] Evento recebido:', event.type, event.data);

        switch (event.type) {
            case 'connected':
                console.log('[SSE] Confirmacao de conexao:', event.data);
                break;

            case 'new_message':
                handleNewMessage(event.data);
                break;

            case 'message_ack':
                handleMessageAck(event.data);
                break;

            case 'message_sent':
                handleMessageSent(event.data);
                break;

            case 'chat_update':
                // Atualizar lista de chats
                loadChatList();
                break;

            default:
                console.log('[SSE] Evento desconhecido:', event.type);
        }
    }

    function handleNewMessage(data) {
        const chatId = data.chatId;
        const message = data.message;

        console.log('[SSE] Nova mensagem de:', chatId);

        // Se e o chat atual, adicionar mensagem
        if (currentPhone && chatId && chatId.includes(formatPhone(currentPhone))) {
            appendNewMessage(message);
        }

        // Atualizar lista de chats (nova mensagem pode mudar ordem)
        loadChatList();

        // Mostrar notificacao se nao for o chat atual ou aba nao visivel
        if (!currentPhone || !chatId.includes(formatPhone(currentPhone)) || document.visibilityState !== 'visible') {
            showNotification(message);
        }
    }

    function handleMessageAck(data) {
        const messageId = data.messageId;
        const ack = data.ack;

        // Atualizar status da mensagem no DOM
        const msgBubble = messagesContainer?.querySelector(`[data-message-id="${messageId}"]`);
        if (msgBubble) {
            const statusEl = msgBubble.querySelector('.msg-status')?.parentElement;
            if (statusEl) {
                // Remover icone antigo e adicionar novo
                const checkIcons = statusEl.querySelectorAll('[data-feather="check"], [data-feather="clock"]');
                checkIcons.forEach(icon => icon.parentElement?.remove());

                // Adicionar novo status
                const newStatus = renderMessageStatus(ack);
                if (newStatus) {
                    statusEl.insertAdjacentHTML('beforeend', newStatus);
                    if (typeof feather !== 'undefined') feather.replace();
                }
            }
        }
    }

    function handleMessageSent(data) {
        const chatId = data.chatId;
        const message = data.message;

        console.log('[SSE] Mensagem enviada confirmada para:', chatId);

        // Remover mensagem otimista e adicionar a real
        const optimisticMsgs = messagesContainer?.querySelectorAll('.optimistic-msg');
        if (optimisticMsgs?.length > 0) {
            optimisticMsgs[0].remove();
        }

        // Se e o chat atual, adicionar mensagem confirmada
        if (currentPhone && chatId && chatId.includes(formatPhone(currentPhone))) {
            appendNewMessage(message);
        }
    }

    function appendNewMessage(msg) {
        if (!messagesContainer) return;

        // Verificar se mensagem ja existe
        const msgId = typeof msg.id === 'object' ? (msg.id._serialized || msg.id.id) : msg.id;
        if (messagesContainer.querySelector(`[data-message-id="${msgId}"]`)) {
            return; // Mensagem ja renderizada
        }

        const isSent = msg.fromMe;
        const time = formatTimeShort(msg.timestamp);

        const html = `
            <div class="d-flex ${isSent ? 'justify-content-end' : 'justify-content-start'} mb-2">
                <div class="message-bubble ${isSent ? 'msg-sent' : 'msg-received'} p-2 px-3 shadow-sm"
                     data-message-id="${msgId}">
                    ${msg.quotedMsg ? renderQuotedMessage(msg.quotedMsg) : ''}
                    ${renderMessageContent(msg)}
                    <div class="d-flex justify-content-end align-items-center mt-1">
                        <small class="text-muted msg-status">${time}</small>
                        ${isSent ? renderMessageStatus(msg.ack) : ''}
                    </div>
                </div>
            </div>
        `;

        // Verificar se estava no final antes de adicionar
        const wasAtBottom = isScrolledToBottom();

        messagesContainer.insertAdjacentHTML('beforeend', html);

        // Adicionar evento de reply na nova mensagem
        const newBubble = messagesContainer.lastElementChild?.querySelector('.message-bubble');
        if (newBubble) {
            newBubble.addEventListener('dblclick', () => {
                const msgText = newBubble.querySelector('.msg-body')?.textContent || '';
                setReplyTo(msgId, msgText);
            });
        }

        // Se for imagem, adicionar evento de clique
        const newImg = messagesContainer.lastElementChild?.querySelector('.msg-image');
        if (newImg) {
            newImg.addEventListener('click', () => {
                const modal = document.getElementById('imageViewerModal');
                const modalImg = document.getElementById('image-viewer-img');
                if (modal && modalImg) {
                    modalImg.src = newImg.src;
                    new bootstrap.Modal(modal).show();
                }
            });
        }

        // Scroll para baixo se estava no final
        if (wasAtBottom) {
            scrollToBottom();
        }

        if (typeof feather !== 'undefined') feather.replace();
    }

    function showNotification(msg) {
        // Verificar se notificacoes estao permitidas
        if (!('Notification' in window) || Notification.permission !== 'granted') {
            return;
        }

        // Extrair informacoes da mensagem
        const body = msg.body || msg.caption || 'Nova mensagem';
        const from = msg.notifyName || msg.pushname || formatPhone(msg.from || '');

        try {
            const notification = new Notification(from, {
                body: truncateText(body, 100),
                icon: '/static/assets/images/logo/whatsapp-icon.png',
                tag: 'whatsapp-chat',
                renotify: true
            });

            notification.onclick = () => {
                window.focus();
                notification.close();
            };

            // Auto-fechar apos 5 segundos
            setTimeout(() => notification.close(), 5000);
        } catch (err) {
            console.log('[Notification] Erro ao mostrar notificacao:', err);
        }
    }

    function setupVisibilityChange() {
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                // Reconectar SSE se desconectado
                if (!sseConnected && !sseReconnectTimeout) {
                    connectSSE();
                }
                // Carregar dados atualizados ao voltar para a aba
                if (currentPhone) loadMessages(currentPhone, true);
                loadChatList();
            } else {
                // Desconectar SSE quando aba fica oculta (economizar recursos)
                // Opcional: manter conectado para receber notificacoes
                // disconnectSSE();
            }
        });
    }

    // Carrega lista de conversas silenciosamente (para atualizacao manual)
    async function loadChatListSilent() {
        try {
            const response = await fetch('/api/chat/list/');
            const data = await response.json();

            if (response.ok && Array.isArray(data)) {
                renderChatList(data);
            }
        } catch (error) {
            console.log('[Chat] Erro ao atualizar chats:', error.message);
        }
    }

    // Busca/filtro de conversas
    function filterChats() {
        const query = searchInput.value.toLowerCase();
        chatList.querySelectorAll('.chat-item').forEach(item => {
            const name = (item.dataset.name || '').toLowerCase();
            const phone = (item.dataset.phone || '').toLowerCase();
            item.style.display = (name.includes(query) || phone.includes(query)) ? '' : 'none';
        });
    }

    // Utilidades
    function scrollToBottom() {
        if (messagesContainer) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    function autoResizeTextarea() {
        if (messageInput) {
            messageInput.style.height = 'auto';
            messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
        }
    }

    function formatPhone(phone) {
        if (!phone) return '';
        // Se for objeto, extrair _serialized ou user
        if (typeof phone === 'object') {
            phone = phone._serialized || phone.user || '';
        }
        if (typeof phone !== 'string') return '';
        // Remover @c.us ou @g.us
        return phone.replace(/@[cg]\.us$/, '');
    }

    function formatTime(timestamp) {
        if (!timestamp) return '';
        const date = new Date(timestamp * 1000);
        const now = new Date();
        const diff = now - date;

        if (diff < 86400000 && date.getDate() === now.getDate()) {
            return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
        }
        if (diff < 604800000) {
            return date.toLocaleDateString('pt-BR', { weekday: 'short' });
        }
        return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
    }

    function formatTimeShort(timestamp) {
        if (!timestamp) return '';
        const date = new Date(timestamp * 1000);
        return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    }

    function formatDate(timestamp) {
        if (!timestamp) return '';
        const date = new Date(timestamp * 1000);
        const now = new Date();

        if (date.toDateString() === now.toDateString()) {
            return 'Hoje';
        }

        const yesterday = new Date(now);
        yesterday.setDate(yesterday.getDate() - 1);
        if (date.toDateString() === yesterday.toDateString()) {
            return 'Ontem';
        }

        return date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric' });
    }

    function truncateText(text, maxLength) {
        if (!text) return '';
        return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
               document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
    }

    function showToast(message, type = 'info') {
        // Criar toast simples
        const toastHtml = `
            <div class="toast align-items-center text-white bg-${type} border-0 position-fixed bottom-0 end-0 m-3"
                 role="alert" style="z-index: 9999;">
                <div class="d-flex">
                    <div class="toast-body">${escapeHtml(message)}</div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto"
                            data-bs-dismiss="toast"></button>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', toastHtml);
        const toastEl = document.body.lastElementChild;

        if (typeof bootstrap !== 'undefined') {
            const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
            toast.show();
            toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
        } else {
            // Fallback sem bootstrap
            setTimeout(() => toastEl.remove(), 3000);
        }
    }

})();
