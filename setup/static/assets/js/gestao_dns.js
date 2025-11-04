/**
 * Gestão de Domínios DNS - Frontend Controller
 *
 * Gerencia todo o fluxo de automação de migração DNS:
 * 1. Seleção de aplicativo
 * 2. Verificação de conta reseller
 * 3. Login manual (se necessário)
 * 4. Configuração da migração
 * 5. Execução e monitoramento em tempo real
 *
 * @author Claude Code
 * @version 1.0.0
 */

// ==================== ESTADO GLOBAL ====================

const GestaoDNS = {
    aplicativoSelecionado: null,
    tarefaAtualId: null,
    pollingInterval: null,
    pollingIntervalMs: 3000, // 3 segundos
    filtroAtivo: 'all', // Filtro atual ativo (tabela de progresso em tempo real)
    filtroDispositivosDetalhes: 'all', // Filtro de detalhes históricos
    tarefaIdAtual: null, // ID da tarefa de detalhes sendo visualizada

    /**
     * Filtra a tabela de dispositivos por status
     * @param {string} status - 'all', 'sucesso', 'erro', 'pulado'
     */
    filtrarPorStatus(status) {
        // Atualiza filtro ativo
        this.filtroAtivo = status;

        // Remove classe active de todos os cards
        document.querySelectorAll('.card-filter-clickable').forEach(card => {
            card.classList.remove('card-filter-active');
        });

        // Adiciona classe active no card clicado
        const cardAtivo = document.querySelector(`.card-filter-clickable[data-filter="${status}"]`);
        if (cardAtivo) {
            cardAtivo.classList.add('card-filter-active');
        }

        // Filtra linhas da tabela
        const tbody = document.getElementById('devices-tbody');
        if (!tbody) return;

        const rows = tbody.querySelectorAll('tr');
        rows.forEach(row => {
            if (status === 'all') {
                row.style.display = '';
            } else {
                // Pega o status da linha (busca no badge)
                const statusBadge = row.querySelector('.badge.status-badge');
                if (statusBadge) {
                    const rowStatus = statusBadge.textContent.toLowerCase().trim();
                    // Mapeia textos para valores de filtro
                    const statusMap = {
                        'sucesso': 'sucesso',
                        'erro': 'erro',
                        'pulado': 'pulado',
                        'pendente': 'pendente',
                        'processando': 'processando'
                    };

                    const normalizedStatus = Object.keys(statusMap).find(key =>
                        rowStatus.includes(key)
                    );

                    if (normalizedStatus === status) {
                        row.style.display = '';
                    } else {
                        row.style.display = 'none';
                    }
                } else {
                    row.style.display = 'none';
                }
            }
        });
    },

    /**
     * Filtra a tabela de dispositivos de detalhes por status (COM PAGINAÇÃO AJAX)
     * @param {string} status - 'all', 'sucesso', 'erro', 'pulado'
     */
    filtrarDispositivosDetalhes(status) {
        // Remove classe active de todos os cards
        document.querySelectorAll('.card-filter-clickable-detalhes').forEach(card => {
            card.classList.remove('card-filter-active');
        });

        // Adiciona classe active no card clicado
        const cardAtivo = document.querySelector(`.card-filter-clickable-detalhes[data-filter="${status}"]`);
        if (cardAtivo) {
            cardAtivo.classList.add('card-filter-active');
        }

        // Recarrega dispositivos com o novo filtro (página 1)
        this.carregarDispositivosPaginados(1, status);
    },

    /**
     * Carrega dispositivos via AJAX com paginação
     * @param {number} page - Número da página
     * @param {string} statusFilter - Filtro de status ('all', 'sucesso', 'erro', 'pulado')
     */
    carregarDispositivosPaginados(page = 1, statusFilter = null) {
        // Usa filtro armazenado se não foi passado explicitamente
        const filtro = statusFilter !== null ? statusFilter : this.filtroDispositivosDetalhes;

        // Atualiza filtro armazenado
        this.filtroDispositivosDetalhes = filtro;

        // Mostra loading na tabela
        const tbody = document.getElementById('dispositivos-detalhes-tbody');
        if (!tbody) return;

        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center py-4">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Carregando...</span>
                    </div>
                    <p class="mt-2 text-muted">Carregando dispositivos...</p>
                </td>
            </tr>
        `;

        // Desabilita controles de paginação durante o carregamento
        document.querySelectorAll('.pagination .page-link').forEach(link => {
            link.style.pointerEvents = 'none';
            link.style.opacity = '0.6';
        });

        // Faz requisição AJAX
        const url = new URL('/api/gestao-dns/dispositivos-paginados/', window.location.origin);
        url.searchParams.append('tarefa_id', this.tarefaIdAtual);
        url.searchParams.append('page', page);
        url.searchParams.append('status_filter', filtro);

        fetch(url, {
            method: 'GET',
            headers: {
                'X-CSRFToken': getCsrfToken()
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Atualiza tabela
                this.renderizarTabelaDispositivos(data.dispositivos);

                // Atualiza controles de paginação
                this.renderizarPaginacao(data.pagination);
            } else {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="6" class="text-center py-4 text-danger">
                            <i class="bi bi-exclamation-triangle me-2"></i>
                            ${data.error || 'Erro ao carregar dispositivos'}
                        </td>
                    </tr>
                `;
                showToast('error', data.error || 'Erro ao carregar dispositivos');
            }
        })
        .catch(error => {
            console.error('Erro ao carregar dispositivos:', error);
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center py-4 text-danger">
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        Erro de conexão. Tente novamente.
                    </td>
                </tr>
            `;
            showToast('error', 'Erro de conexão ao carregar dispositivos');
        })
        .finally(() => {
            // Reabilita controles de paginação
            document.querySelectorAll('.pagination .page-link').forEach(link => {
                link.style.pointerEvents = '';
                link.style.opacity = '';
            });
        });
    },

    /**
     * Renderiza linhas da tabela de dispositivos
     * @param {Array} dispositivos - Lista de dispositivos
     */
    renderizarTabelaDispositivos(dispositivos) {
        const tbody = document.getElementById('dispositivos-detalhes-tbody');
        if (!tbody) return;

        if (dispositivos.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center py-4 text-muted">
                        <i class="bi bi-info-circle me-2"></i>
                        Nenhum dispositivo encontrado para este filtro.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = '';

        dispositivos.forEach(dispositivo => {
            const row = document.createElement('tr');

            // Determina badge de status
            let badgeClass = 'secondary';
            let badgeIcon = '';
            let badgeText = dispositivo.status;

            switch (dispositivo.status) {
                case 'sucesso':
                    badgeClass = 'success';
                    badgeIcon = '<i class="bi bi-check-circle-fill"></i>';
                    badgeText = 'sucesso';
                    break;
                case 'erro':
                    badgeClass = 'danger';
                    badgeIcon = '<i class="bi bi-x-circle-fill"></i>';
                    badgeText = 'erro';
                    break;
                case 'pulado':
                    badgeClass = 'warning text-dark';
                    badgeIcon = '<i class="bi bi-skip-forward-fill"></i>';
                    badgeText = 'pulado';
                    break;
                case 'processando':
                    badgeClass = 'info';
                    badgeIcon = '<i class="bi bi-arrow-repeat"></i>';
                    badgeText = 'processando';
                    break;
            }

            row.innerHTML = `
                <td class="text-center"><code>${dispositivo.device_id}</code></td>
                <td class="text-center">${dispositivo.nome_dispositivo}</td>
                <td class="text-center">
                    <span class="badge bg-${badgeClass}">
                        ${badgeIcon} ${badgeText}
                    </span>
                </td>
                <td class="text-center"><small class="text-muted">${dispositivo.dns_encontrado}</small></td>
                <td class="text-center"><small class="text-success">${dispositivo.dns_atualizado}</small></td>
                <td class="text-center">
                    ${dispositivo.mensagem_erro ?
                        `<small class="text-danger">${dispositivo.mensagem_erro}</small>` :
                        '<small class="text-muted">-</small>'}
                </td>
            `;

            tbody.appendChild(row);
        });
    },

    /**
     * Renderiza controles de paginação
     * @param {Object} pagination - Dados de paginação
     */
    renderizarPaginacao(pagination) {
        const paginationContainer = document.querySelector('#dispositivos-detalhes-paginacao');
        if (!paginationContainer) return;

        if (pagination.total_pages <= 1) {
            paginationContainer.innerHTML = '';
            return;
        }

        let html = '<ul class="pagination justify-content-center">';

        // Botão "Anterior"
        if (pagination.has_previous) {
            html += `
                <li class="page-item">
                    <a class="page-link" href="#" data-page="${pagination.previous_page}" aria-label="Anterior">
                        <span aria-hidden="true">&laquo;</span>
                    </a>
                </li>
            `;
        } else {
            html += `
                <li class="page-item disabled">
                    <span class="page-link">&laquo;</span>
                </li>
            `;
        }

        // Números de página (mostra apenas páginas próximas)
        const currentPage = pagination.current_page;
        const totalPages = pagination.total_pages;

        for (let i = 1; i <= totalPages; i++) {
            // Mostra apenas páginas próximas (+/- 2 da atual)
            if (i === currentPage) {
                html += `<li class="page-item active"><span class="page-link">${i}</span></li>`;
            } else if (i >= currentPage - 2 && i <= currentPage + 2) {
                html += `
                    <li class="page-item">
                        <a class="page-link" href="#" data-page="${i}">${i}</a>
                    </li>
                `;
            }
        }

        // Botão "Próximo"
        if (pagination.has_next) {
            html += `
                <li class="page-item">
                    <a class="page-link" href="#" data-page="${pagination.next_page}" aria-label="Próximo">
                        <span aria-hidden="true">&raquo;</span>
                    </a>
                </li>
            `;
        } else {
            html += `
                <li class="page-item disabled">
                    <span class="page-link">&raquo;</span>
                </li>
            `;
        }

        html += '</ul>';
        paginationContainer.innerHTML = html;

        // Adiciona event listeners aos links de paginação
        paginationContainer.querySelectorAll('a.page-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = parseInt(e.currentTarget.getAttribute('data-page'));
                GestaoDNS.carregarDispositivosPaginados(page);

                // Scroll suave até a tabela
                document.getElementById('dispositivos-detalhes-tbody')?.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            });
        });
    }
};

// ==================== CSRF TOKEN ====================

function getCsrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]').value;
}

// ==================== HELPERS ====================

function showStep(stepId) {
    // Esconde todos os steps
    document.querySelectorAll('[id^="step-"]').forEach(step => {
        step.classList.add('hidden');
    });

    // Mostra o step solicitado
    const step = document.getElementById(stepId);
    if (step) {
        step.classList.remove('hidden');
    }
}

function formatDate(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString('pt-BR');
}

// ==================== ETAPA 1: SELEÇÃO DE APLICATIVO ====================

function initAppSelection() {
    const appCards = document.querySelectorAll('.app-card');

    appCards.forEach(card => {
        card.addEventListener('click', function() {
            const appId = this.dataset.appId;
            const appName = this.dataset.appName;
            const temAutomacao = this.dataset.temAutomacao === 'true';

            // Bloqueia clique se não tem automação
            if (!temAutomacao) {
                showToast('warning', `Automação ainda não implementada para ${appName}`);
                return;
            }

            // Marca como selecionado
            appCards.forEach(c => c.classList.remove('selected'));
            this.classList.add('selected');

            GestaoDNS.aplicativoSelecionado = {
                id: appId,
                nome: appName
            };

            // Avança para verificação de conta
            verificarConta(appId);
        });
    });
}

// ==================== ETAPA 2: VERIFICAÇÃO DE CONTA ====================

function verificarConta(appId) {
    showStep('step-account-status');

    // Mostra loading
    document.getElementById('account-status-content').innerHTML = `
        <div class="text-center py-4">
            <div class="spinner-border text-primary" role="status">
                <span class="visually-hidden">Verificando...</span>
            </div>
            <p class="mt-3 text-muted">Verificando status da conta...</p>
        </div>
    `;

    // Faz requisição para verificar conta
    fetch('/api/gestao-dns/verificar-conta/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': getCsrfToken()
        },
        body: `aplicativo_id=${appId}`
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'nao_implementado') {
            // Aplicativo sem automação
            document.getElementById('account-status-content').innerHTML = `
                <div class="alert alert-warning">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i>
                    ${data.mensagem}
                </div>
            `;
        } else if (data.status === 'sem_conta') {
            // Precisa fazer login
            document.getElementById('account-status-content').innerHTML = `
                <div class="alert alert-info">
                    <i class="bi bi-info-circle-fill me-2"></i>
                    ${data.mensagem}
                </div>
                <button class="btn btn-primary btn-lg w-100" onclick="mostrarFormularioLogin()">
                    <i class="bi bi-box-arrow-in-right me-2"></i>Fazer Login Manual
                </button>
            `;
        } else if (data.status === 'sessao_expirada') {
            // Sessão expirou
            document.getElementById('account-status-content').innerHTML = `
                <div class="alert alert-warning">
                    <i class="bi bi-exclamation-triangle-fill me-2"></i>
                    <strong>Sessão Expirada</strong><br>
                    Último acesso: ${formatDate(data.ultimo_login)}
                </div>
                <button class="btn btn-warning btn-lg w-100" onclick="mostrarFormularioLogin()">
                    <i class="bi bi-arrow-repeat me-2"></i>Renovar Login
                </button>
            `;
        } else if (data.status === 'ok') {
            // Conta válida! Vai direto para configuração
            document.getElementById('account-status-content').innerHTML = `
                <div class="alert alert-success">
                    <i class="bi bi-check-circle-fill me-2"></i>
                    <strong>Conta Autenticada</strong><br>
                    Email: ${data.email}<br>
                    Último acesso: ${formatDate(data.ultimo_login)}
                </div>
            `;

            // Aguarda 1 segundo e avança
            setTimeout(() => {
                mostrarConfiguracaoMigracao();
            }, 1000);
        }
    })
    .catch(error => {
        console.error('Erro ao verificar conta:', error);
        showToast('error', 'Erro ao verificar conta. Tente novamente.');
    });
}

// ==================== ETAPA 3: LOGIN MANUAL ====================

function mostrarFormularioLogin() {
    showStep('step-login-manual');

    // Preenche aplicativo_id
    document.getElementById('login-aplicativo-id').value = GestaoDNS.aplicativoSelecionado.id;
}

function initLoginForm() {
    const form = document.getElementById('form-login-manual');

    form.addEventListener('submit', function(e) {
        e.preventDefault();

        const submitBtn = form.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;

        // Desabilita botão
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Abrindo navegador...';

        // Envia requisição
        const formData = new FormData(form);

        fetch('/api/gestao-dns/login-manual/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken()
            },
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'login_iniciado') {
                showToast('info', data.mensagem);

                // Aguarda login ser completado (polling)
                verificarLoginCompletado();
            } else {
                showToast('error', data.error || 'Erro ao iniciar login');
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }
        })
        .catch(error => {
            console.error('Erro ao iniciar login:', error);
            showToast('error', 'Erro ao iniciar login. Tente novamente.');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        });
    });
}

function verificarLoginCompletado() {
    // Polling para verificar se login foi completado
    const checkInterval = setInterval(() => {
        verificarConta(GestaoDNS.aplicativoSelecionado.id);

        // Para de verificar após 5 minutos (timeout)
        setTimeout(() => clearInterval(checkInterval), 300000);
    }, 5000); // Verifica a cada 5 segundos
}

// ==================== ETAPA 4: CONFIGURAÇÃO DA MIGRAÇÃO ====================

function mostrarConfiguracaoMigracao() {
    showStep('step-migracao-config');

    // Preenche aplicativo_id
    document.getElementById('migracao-aplicativo-id').value = GestaoDNS.aplicativoSelecionado.id;
}

function initMigracaoForm() {
    const form = document.getElementById('form-migracao');
    const tipoTodos = document.getElementById('tipo-todos');
    const tipoEspecifico = document.getElementById('tipo-especifico');
    const divMacEspecifico = document.getElementById('div-mac-especifico');
    const macInput = document.getElementById('mac-alvo');

    // Toggle MAC input baseado no tipo de migração
    tipoTodos.addEventListener('change', function() {
        divMacEspecifico.classList.add('hidden');
        macInput.required = false;
    });

    tipoEspecifico.addEventListener('change', function() {
        divMacEspecifico.classList.remove('hidden');
        macInput.required = true;
    });

    // Submit do formulário
    form.addEventListener('submit', function(e) {
        e.preventDefault();

        const submitBtn = form.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;

        // Desabilita botão
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Iniciando...';

        // Envia requisição
        const formData = new FormData(form);

        fetch('/api/gestao-dns/iniciar-migracao/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken()
            },
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'iniciado') {
                GestaoDNS.tarefaAtualId = data.tarefa_id;

                showToast('success', data.mensagem);

                // Avança para tela de progresso
                mostrarProgresso();
            } else {
                showToast('error', data.error || 'Erro ao iniciar migração');
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalText;
            }
        })
        .catch(error => {
            console.error('Erro ao iniciar migração:', error);
            showToast('error', 'Erro ao iniciar migração. Tente novamente.');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        });
    });

    // Botão voltar
    document.getElementById('btn-voltar').addEventListener('click', function() {
        showStep('step-select-app');
    });
}

// ==================== ETAPA 5: PROGRESSO ====================

function mostrarProgresso() {
    showStep('step-progresso');

    // Inicia polling
    iniciarPolling();
}

function iniciarPolling() {
    if (GestaoDNS.pollingInterval) {
        clearInterval(GestaoDNS.pollingInterval);
    }

    // Primeira chamada imediata
    consultarProgresso();

    // Polling a cada 3 segundos
    GestaoDNS.pollingInterval = setInterval(() => {
        consultarProgresso();
    }, GestaoDNS.pollingIntervalMs);
}

function consultarProgresso() {
    fetch(`/api/gestao-dns/progresso/${GestaoDNS.tarefaAtualId}/`, {
        method: 'GET',
        headers: {
            'X-CSRFToken': getCsrfToken()
        }
    })
    .then(response => response.json())
    .then(data => {
        atualizarProgresso(data);

        // Se concluído, para polling
        if (data.concluida) {
            clearInterval(GestaoDNS.pollingInterval);
            mostrarResumo(data);
        }
    })
    .catch(error => {
        console.error('Erro ao consultar progresso:', error);
    });
}

function atualizarProgresso(data) {
    // ===== 1. MENSAGEM DINÂMICA DE PROGRESSO =====
    const progressMessageElement = document.getElementById('progress-message-text');
    const progressMessageDiv = document.getElementById('progress-message');

    if (progressMessageElement && data.mensagem_progresso) {
        progressMessageElement.textContent = data.mensagem_progresso;

        // Muda cor do alert baseado na etapa
        const etapa = data.etapa_atual || 'iniciando';
        progressMessageDiv.className = 'alert mb-3 text-center';

        if (etapa === 'concluida') {
            progressMessageDiv.classList.add('alert-success');
        } else if (etapa === 'cancelada') {
            progressMessageDiv.classList.add('alert-danger');
        } else if (etapa === 'analisando') {
            progressMessageDiv.classList.add('alert-info');
        } else if (etapa === 'processando') {
            progressMessageDiv.classList.add('alert-warning');
        } else {
            progressMessageDiv.classList.add('alert-info');
        }
    }

    // ===== 2. BARRA DE PROGRESSO =====
    const percentual = data.progresso_percentual || 0;
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');

    progressBar.style.width = `${percentual}%`;
    progressText.textContent = `${percentual}%`;

    // Remove classes antigas de cor
    progressBar.classList.remove('bg-primary', 'bg-success', 'bg-danger', 'bg-warning');

    // Define cor baseado no status final
    if (data.concluida) {
        // Remove animação quando concluído
        progressBar.classList.remove('progress-bar-animated');

        const etapa = data.etapa_atual || 'concluida';

        if (etapa === 'concluida') {
            // Verde se teve sucesso (total ou parcial)
            if (data.sucessos > 0 && data.falhas === 0) {
                progressBar.classList.add('bg-success');
            } else if (data.sucessos > 0 && data.falhas > 0) {
                // Amarelo se teve sucessos E falhas
                progressBar.classList.add('bg-warning');
            } else if (data.sucessos === 0 && data.pulados > 0) {
                // Amarelo se todos foram pulados
                progressBar.classList.add('bg-warning');
            } else {
                // Vermelho se todos falharam
                progressBar.classList.add('bg-danger');
            }
        } else if (etapa === 'cancelada') {
            // Vermelho se cancelado
            progressBar.classList.add('bg-danger');
        } else {
            // Padrão
            progressBar.classList.add('bg-primary');
        }
    } else {
        // Durante processamento: azul primário
        progressBar.classList.add('bg-primary');
    }

    // ===== 3. ESTATÍSTICAS =====
    document.getElementById('stat-total').textContent = data.total_dispositivos;
    document.getElementById('stat-processados').textContent = data.processados;
    document.getElementById('stat-sucessos').textContent = data.sucessos;
    document.getElementById('stat-pulados').textContent = data.pulados || 0;
    document.getElementById('stat-falhas').textContent = data.falhas;

    // ===== 4. LOADING INDICATOR =====
    const loadingIndicator = document.getElementById('loading-indicator');
    // Esconde loading se: já carregou dispositivos OU tarefa já concluiu
    if (data.total_dispositivos > 0 || data.concluida === true) {
        loadingIndicator?.classList.add('hidden');
    } else {
        // Mostra loading apenas se ainda em andamento E sem dispositivos
        loadingIndicator?.classList.remove('hidden');
    }

    // ===== 5. TABELA DE DISPOSITIVOS =====
    const tbody = document.getElementById('devices-tbody');
    tbody.innerHTML = '';

    data.dispositivos.forEach(device => {
        const statusIcon = {
            'pendente': '⏳',
            'processando': '🔄',
            'sucesso': '✅',
            'erro': '❌',
            'pulado': '⏭️'
        }[device.status] || '❓';

        const statusClass = {
            'pendente': 'secondary',
            'processando': 'warning',
            'sucesso': 'success',
            'erro': 'danger',
            'pulado': 'info'
        }[device.status] || 'secondary';

        const row = document.createElement('tr');
        row.innerHTML = `
            <td><code>${device.device_id}</code></td>
            <td>${device.nome_dispositivo || '-'}</td>
            <td>
                <span class="badge bg-${statusClass} status-badge">
                    <span style="font-size: 1.2em;">${statusIcon}</span> ${device.status}
                </span>
            </td>
            <td><small>${device.dns_encontrado || '-'}</small></td>
            <td><small>${device.dns_atualizado || '-'}</small></td>
            <td><small class="text-danger">${device.mensagem_erro || '-'}</small></td>
        `;
        tbody.appendChild(row);
    });
}

function mostrarResumo(data) {
    const resumoDiv = document.getElementById('resumo-final');
    const resumoTexto = document.getElementById('resumo-texto');
    const resumoAlert = resumoDiv.querySelector('.alert');
    const resumoHeading = resumoDiv.querySelector('.alert-heading');

    const taxaSucesso = data.total_dispositivos > 0
        ? ((data.sucessos / data.total_dispositivos) * 100).toFixed(1)
        : 0;

    // Determinar tipo de resultado
    let mensagemPrincipal, tipologClass, icone;

    if (data.total_dispositivos === 0) {
        // Nenhum dispositivo encontrado
        mensagemPrincipal = 'Nenhum dispositivo encontrado!';
        tipologClass = 'alert-warning';
        icone = 'bi-exclamation-triangle-fill';
    } else if (data.sucessos === 0 && data.falhas === 0) {
        // Todos pulados
        mensagemPrincipal = 'Migração concluída - Todos os dispositivos foram pulados';
        tipologClass = 'alert-info';
        icone = 'bi-info-circle-fill';
    } else if (data.sucessos === 0 && data.falhas > 0) {
        // Todos falharam
        mensagemPrincipal = 'Migração concluída com erros';
        tipologClass = 'alert-danger';
        icone = 'bi-x-circle-fill';
    } else if (data.falhas > 0) {
        // Sucesso parcial
        mensagemPrincipal = 'Migração concluída com ressalvas';
        tipologClass = 'alert-warning';
        icone = 'bi-exclamation-triangle-fill';
    } else {
        // 100% sucesso
        mensagemPrincipal = 'Migração concluída com sucesso!';
        tipologClass = 'alert-success';
        icone = 'bi-check-circle-fill';
    }

    // Atualizar classes do alert
    resumoAlert.className = `alert ${tipologClass}`;

    // Atualizar heading
    resumoHeading.innerHTML = `<i class="bi ${icone} me-2"></i>${mensagemPrincipal}`;

    // Atualizar texto do resumo
    resumoTexto.innerHTML = `
        Total de dispositivos: ${data.total_dispositivos}<br>
        Sucessos: ${data.sucessos} (${taxaSucesso}%)<br>
        Pulados: ${data.pulados || 0}<br>
        Falhas: ${data.falhas}
    `;

    resumoDiv.classList.remove('hidden');

    // Botão nova migração
    document.getElementById('btn-nova-migracao').addEventListener('click', function() {
        location.reload();
    });
}

// ==================== MODO DEBUG HEADLESS (Apenas Admin) ====================

async function loadDebugStatus() {
    try {
        const response = await fetch('/api/debug-status/');
        const data = await response.json();

        console.log('Debug Status:', {
            is_admin: data.is_admin,
            debug_mode: data.debug_mode,
            success: data.success
        });

        if (data.is_admin && document.getElementById('btnToggleDebug')) {
            updateDebugButton(data.debug_mode);
        } else if (!data.is_admin) {
            console.warn('Usuário não é admin - botão debug não será inicializado');
        }
    } catch (error) {
        console.error('Erro ao carregar status de debug:', error);
    }
}

async function toggleDebugMode() {
    const btnToggleDebug = document.getElementById('btnToggleDebug');
    if (!btnToggleDebug) return;

    try {
        btnToggleDebug.disabled = true;

        // Debug: verificar CSRF token
        const csrfToken = getCsrfToken();
        console.log('CSRF Token:', csrfToken ? 'OK' : 'AUSENTE');

        const response = await fetch('/api/toggle-debug-headless/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            }
        });

        // Verificar se resposta é JSON ou HTML
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            console.error('Resposta não-JSON recebida:', text.substring(0, 500));

            if (response.status === 403) {
                showToast('error', 'Permissão negada. Apenas administradores podem alterar o modo debug.');
            } else {
                showToast('error', `Erro HTTP ${response.status}: Resposta inválida do servidor`);
            }
            return;
        }

        const data = await response.json();

        if (data.success) {
            updateDebugButton(data.debug_mode);
            showToast('success', data.mensagem);
        } else {
            showToast('error', data.erro || 'Erro ao alternar modo debug');
        }
    } catch (error) {
        console.error('Erro ao toggle debug:', error);
        showToast('error', 'Erro ao alternar modo debug');
    } finally {
        btnToggleDebug.disabled = false;
    }
}

function updateDebugButton(isActive) {
    const btnToggleDebug = document.getElementById('btnToggleDebug');
    const debugStatusText = document.getElementById('debugStatusText');

    if (!btnToggleDebug || !debugStatusText) return;

    if (isActive) {
        btnToggleDebug.classList.add('active');
        debugStatusText.textContent = 'Debug: ON';
        btnToggleDebug.title = 'Modo Debug ATIVO - Navegador será exibido durante automação';
    } else {
        btnToggleDebug.classList.remove('active');
        debugStatusText.textContent = 'Debug: OFF';
        btnToggleDebug.title = 'Modo Debug DESATIVADO - Navegador oculto (headless)';
    }
}

function getCookie(name) {
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

// ==================== INICIALIZAÇÃO ====================

document.addEventListener('DOMContentLoaded', function() {
    console.log('Gestão DNS - Inicializando...');

    initAppSelection();
    initLoginForm();
    initMigracaoForm();

    // Inicializar botão de debug (se admin)
    const btnToggleDebug = document.getElementById('btnToggleDebug');
    if (btnToggleDebug) {
        loadDebugStatus();
        btnToggleDebug.addEventListener('click', toggleDebugMode);
    }

    console.log('Gestão DNS - Pronto!');
});
