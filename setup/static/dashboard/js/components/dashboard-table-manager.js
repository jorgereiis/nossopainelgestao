/**
 * DashboardTableManager - Gerenciador da tabela de clientes do dashboard
 *
 * Responsabilidades:
 * - Gerenciar busca AJAX de clientes
 * - Integrar ordenação da tabela (TableSortable)
 * - Reinicializar dropdowns após atualizações
 * - Mostrar notificações de feedback
 *
 * @example
 * const manager = new DashboardTableManager();
 * manager.init();
 *
 * // Atualizar tabela programaticamente
 * manager.refreshTable();
 */
class DashboardTableManager {
    /**
     * @param {Object} options - Opções de configuração
     * @param {string} options.containerSelector - Seletor do container da tabela
     * @param {string} options.searchInputSelector - Seletor do input de busca
     * @param {string} options.tableSelector - Seletor da tabela
     * @param {number} options.searchDelay - Delay da busca em ms
     * @param {string} options.searchUrl - URL para busca AJAX
     */
    constructor(options = {}) {
        this.options = {
            containerSelector: '#tabela-container',
            searchInputSelector: '#searchInput',
            tableSelector: '#myTable',
            searchDelay: 400,
            searchUrl: '/dashboard/busca/',
            ...options
        };

        this.container = null;
        this.searchInput = null;
        this.sortable = null;
        this.searchTimeout = null;
        this.isInitialized = false;
        this.currentPage = 1; // Rastreia página atual
        this.currentSearchTerm = ''; // Rastreia termo de busca atual
        this.currentPerPage = this.getStoredPerPage(); // Rastreia registros por página
        this.currentSort = this.getStoredSort(); // Rastreia campo de ordenação
        this.currentOrder = this.getStoredOrder(); // Rastreia direção da ordenação
    }

    /**
     * Obtém a preferência de registros por página do localStorage
     * @returns {number} Quantidade de registros por página (padrão: 10)
     */
    getStoredPerPage() {
        const stored = localStorage.getItem('dashboard_per_page');
        return stored ? parseInt(stored, 10) : 10;
    }

    /**
     * Salva a preferência de registros por página no localStorage
     * @param {number} value - Quantidade de registros por página
     */
    setStoredPerPage(value) {
        localStorage.setItem('dashboard_per_page', value.toString());
        this.currentPerPage = value;
    }

    /**
     * Obtém a preferência de campo de ordenação do localStorage
     * @returns {string} Campo de ordenação (padrão: 'dt_vencimento')
     */
    getStoredSort() {
        return localStorage.getItem('dashboard_sort') || 'dt_vencimento';
    }

    /**
     * Salva a preferência de campo de ordenação no localStorage
     * @param {string} value - Campo de ordenação
     */
    setStoredSort(value) {
        localStorage.setItem('dashboard_sort', value);
        this.currentSort = value;
    }

    /**
     * Obtém a preferência de direção da ordenação do localStorage
     * @returns {string} Direção da ordenação (padrão: 'asc')
     */
    getStoredOrder() {
        return localStorage.getItem('dashboard_order') || 'asc';
    }

    /**
     * Salva a preferência de direção da ordenação no localStorage
     * @param {string} value - Direção da ordenação ('asc' ou 'desc')
     */
    setStoredOrder(value) {
        localStorage.setItem('dashboard_order', value);
        this.currentOrder = value;
    }

    /**
     * Inicializa o gerenciador
     * @returns {boolean} True se inicializado com sucesso
     */
    init() {
        // Obtém referências aos elementos
        this.container = document.querySelector(this.options.containerSelector);
        this.searchInput = document.querySelector(this.options.searchInputSelector);

        if (!this.container) {
            console.error(`[DashboardTableManager] Container não encontrado: ${this.options.containerSelector}`);
            return false;
        }

        if (!this.searchInput) {
            console.warn(`[DashboardTableManager] Input de busca não encontrado: ${this.options.searchInputSelector}`);
            // Continua mesmo sem busca
        }

        // Inicializa componentes da tabela
        this.initTable();

        // Anexa listener de busca se input existe
        if (this.searchInput) {
            this.attachSearchListener();
        }

        // Anexa listeners de paginação
        this.attachPaginationListeners();

        // Anexa listener de registros por página
        this.attachPerPageListener();

        // Anexa listener de ordenação server-side
        this.attachSortListeners();

        this.isInitialized = true;
        console.debug('[DashboardTableManager] Inicializado com sucesso');

        return true;
    }

    /**
     * Inicializa os componentes da tabela (dropdowns e tooltips)
     * NOTA: Ordenação client-side (TableSortable) foi desabilitada em favor de ordenação server-side
     * @private
     */
    initTable() {
        // Ordenação server-side: TableSortable desabilitado
        // A ordenação agora é feita pelo backend Django via parâmetros sort/order
        // Ver métodos: sortBy(), attachSortListeners(), updateSortIndicators()

        // Inicializa dropdowns (usa função global existente)
        if (typeof window.initializeTableDropdowns === 'function') {
            console.debug('[DashboardTableManager] Inicializando dropdowns da tabela');
            window.initializeTableDropdowns();
        } else {
            console.warn('[DashboardTableManager] Função initializeTableDropdowns não encontrada');
        }

        // Reinicializa tooltips Bootstrap após AJAX
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.forEach(function (tooltipTriggerEl) {
                // Destrói tooltip existente se houver
                const existingTooltip = bootstrap.Tooltip.getInstance(tooltipTriggerEl);
                if (existingTooltip) {
                    existingTooltip.dispose();
                }
                // Cria novo tooltip
                new bootstrap.Tooltip(tooltipTriggerEl);
            });
            console.debug('[DashboardTableManager] Tooltips reinicializados');
        }
    }

    /**
     * Anexa listener ao input de busca
     * @private
     */
    attachSearchListener() {
        this.searchInput.addEventListener('input', (event) => {
            const searchTerm = event.target.value.trim();

            // Limpa timeout anterior
            if (this.searchTimeout) {
                clearTimeout(this.searchTimeout);
            }

            // Agenda nova busca com delay
            this.searchTimeout = setTimeout(() => {
                this.currentPage = 1; // Reset página ao buscar
                this.performSearch(searchTerm);
            }, this.options.searchDelay);
        });

        console.debug('[DashboardTableManager] Listener de busca anexado');
    }

    /**
     * Anexa listeners aos links de paginação usando event delegation
     * @private
     */
    attachPaginationListeners() {
        // Event delegation no container (funciona mesmo após AJAX)
        this.container.addEventListener('click', (event) => {
            // Verifica se clicou em um link de paginação
            const pageLink = event.target.closest('.pagination .page-link[data-page]');

            if (pageLink) {
                event.preventDefault(); // Impede reload da página

                const page = parseInt(pageLink.dataset.page, 10);

                if (!isNaN(page) && page !== this.currentPage) {
                    this.goToPage(page);
                }
            }
        });

        console.debug('[DashboardTableManager] Listener de paginação anexado (event delegation)');
    }

    /**
     * Anexa listener ao seletor de registros por página usando event delegation
     * @private
     */
    attachPerPageListener() {
        this.container.addEventListener('change', (event) => {
            if (event.target.matches('#per-page-select')) {
                const perPage = parseInt(event.target.value, 10);

                if (!isNaN(perPage)) {
                    this.setStoredPerPage(perPage);
                    this.currentPage = 1; // Reset para primeira página
                    this.performSearch(this.currentSearchTerm, 1);
                }
            }
        });

        console.debug('[DashboardTableManager] Listener de per_page anexado (event delegation)');
    }

    /**
     * Anexa listener de ordenação aos headers da tabela usando event delegation
     * @private
     */
    attachSortListeners() {
        this.container.addEventListener('click', (event) => {
            const header = event.target.closest('th[data-sort-field]');

            if (header) {
                const field = header.dataset.sortField;
                this.sortBy(field);
            }
        });

        console.debug('[DashboardTableManager] Listener de ordenação server-side anexado (event delegation)');
    }

    /**
     * Executa ordenação server-side
     * @param {string} field - Campo para ordenar (ex: 'nome', 'data_adesao')
     * @returns {Promise<void>}
     */
    async sortBy(field) {
        // Toggle ordem se mesmo campo, senão usa 'asc'
        const order = (field === this.currentSort && this.currentOrder === 'asc') ? 'desc' : 'asc';

        console.debug(`[DashboardTableManager] Ordenando por ${field} (${order})`);

        this.setStoredSort(field);
        this.setStoredOrder(order);
        this.currentPage = 1; // Reset para primeira página

        return this.performSearch(this.currentSearchTerm, 1);
    }

    /**
     * Atualiza indicadores visuais de ordenação nos headers
     * @private
     */
    updateSortIndicators() {
        const headers = this.container.querySelectorAll('th[data-sort-field]');

        headers.forEach(header => {
            const field = header.dataset.sortField;

            // Remove classes anteriores
            header.classList.remove('sorted-asc', 'sorted-desc');

            // Adiciona classe se for a coluna ativa
            if (field === this.currentSort) {
                header.classList.add(this.currentOrder === 'asc' ? 'sorted-asc' : 'sorted-desc');
            }
        });

        console.debug('[DashboardTableManager] Indicadores de ordenação atualizados');
    }

    /**
     * Navega para uma página específica
     * @param {number} page - Número da página
     * @returns {Promise<void>}
     */
    async goToPage(page) {
        console.debug(`[DashboardTableManager] Navegando para página ${page}`);

        this.currentPage = page;
        return this.performSearch(this.currentSearchTerm, page);
    }

    /**
     * Executa busca AJAX de clientes
     * @param {string} searchTerm - Termo de busca
     * @param {number} page - Número da página (padrão: 1)
     * @returns {Promise<void>}
     */
    async performSearch(searchTerm, page = 1) {
        try {
            // Atualiza estado
            this.currentSearchTerm = searchTerm;
            this.currentPage = page;

            console.debug(`[DashboardTableManager] Buscando: "${searchTerm}" (página ${page})`);

            // Mostra feedback de carregamento
            this.showToast('Buscando clientes...', 'info');

            // Constrói URL com busca, página, registros por página e ordenação
            const params = new URLSearchParams();
            if (searchTerm) {
                params.append('q', searchTerm);
            }
            if (page > 1) {
                params.append('page', page);
            }
            // Sempre envia per_page para manter preferência do usuário
            params.append('per_page', this.currentPerPage);
            // Sempre envia parâmetros de ordenação server-side
            params.append('sort', this.currentSort);
            params.append('order', this.currentOrder);

            // Adiciona filtros avançados
            const filters = this.getFilters();
            if (filters.data_vencimento) params.append('data_vencimento', filters.data_vencimento);
            if (filters.servidor) params.append('servidor', filters.servidor);
            if (filters.tipo_plano) params.append('tipo_plano', filters.tipo_plano);
            if (filters.plano) params.append('plano', filters.plano);

            const url = `${this.options.searchUrl}?${params.toString()}`;
            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const html = await response.text();

            // Substitui conteúdo da tabela
            this.container.innerHTML = html;

            // Reinicializa componentes (sem ordenação client-side)
            this.initTable();

            // Atualiza indicadores visuais de ordenação
            this.updateSortIndicators();

            // Atualiza URL do navegador (history API)
            this.updateBrowserUrl(searchTerm, page);

            // Scroll suave para o topo da tabela
            this.scrollToTable();

            // Feedback de sucesso
            this.showToast('Tabela atualizada!', 'success');

            console.debug('[DashboardTableManager] Busca concluída com sucesso');

        } catch (error) {
            console.error('[DashboardTableManager] Erro ao buscar clientes:', error);
            this.showToast('Erro ao buscar clientes!', 'error');
        }
    }

    /**
     * Atualiza a tabela mantendo o termo de busca e página atuais
     * @returns {Promise<void>}
     */
    async refreshTable() {
        console.debug(`[DashboardTableManager] Atualizando tabela (termo: "${this.currentSearchTerm}", página: ${this.currentPage})`);

        return this.performSearch(this.currentSearchTerm, this.currentPage);
    }

    /**
     * Coleta valores dos filtros avançados
     * @returns {Object} Objeto com os valores dos filtros
     */
    getFilters() {
        return {
            data_vencimento: document.getElementById('filtroDataVencimento')?.value || '',
            servidor: document.getElementById('filtroServidor')?.value || '',
            tipo_plano: document.getElementById('filtroTipoPlano')?.value || '',
            plano: document.getElementById('filtroPlano')?.value || ''
        };
    }

    /**
     * Executa busca incluindo filtros avançados
     * @returns {Promise<void>}
     */
    async performSearchWithFilters() {
        const searchTerm = this.searchInput?.value?.trim() || '';
        await this.performSearch(searchTerm, 1);
    }

    /**
     * Atualiza URL do navegador sem recarregar a página
     * @private
     * @param {string} searchTerm - Termo de busca
     * @param {number} page - Número da página
     */
    updateBrowserUrl(searchTerm, page) {
        const params = new URLSearchParams();

        if (searchTerm) {
            params.append('q', searchTerm);
        }

        if (page > 1) {
            params.append('page', page);
        }

        // Inclui per_page na URL apenas se diferente do padrão (10)
        if (this.currentPerPage !== 10) {
            params.append('per_page', this.currentPerPage);
        }

        const newUrl = params.toString()
            ? `${window.location.pathname}?${params.toString()}`
            : window.location.pathname;

        // Atualiza URL sem recarregar (History API)
        window.history.pushState({ searchTerm, page, perPage: this.currentPerPage }, '', newUrl);

        console.debug(`[DashboardTableManager] URL atualizada: ${newUrl}`);
    }

    /**
     * Faz scroll suave para o topo da tabela
     * @private
     */
    scrollToTable() {
        if (this.container) {
            this.container.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    }

    /**
     * Mostra notificação toast
     * @private
     * @param {string} message - Mensagem a exibir
     * @param {string} type - Tipo: 'info', 'success' ou 'error'
     */
    showToast(message, type = 'info') {
        // Usa função global do toast-manager.js
        if (typeof window.showToast === 'function') {
            // Nova assinatura: showToast(type, message, options)
            window.showToast(type, message);
        } else {
            // Fallback simples
            console.log(`[Toast ${type.toUpperCase()}] ${message}`);
        }
    }

    /**
     * Limpa o input de busca e atualiza a tabela
     */
    clearSearch() {
        if (this.searchInput) {
            this.searchInput.value = '';
            this.performSearch('');
        }
    }

    /**
     * Limpa ordenação e reseta tabela
     */
    clearSort() {
        if (this.sortable) {
            this.sortable.clearSortState();
            this.refreshTable();
        }
    }

    /**
     * Obtém estado atual de ordenação
     * @returns {Object|null}
     */
    getSortState() {
        return this.sortable ? this.sortable.getSortState() : null;
    }

    /**
     * Verifica se o gerenciador está pronto
     * @returns {boolean}
     */
    isReady() {
        return this.isInitialized && this.container !== null;
    }

    /**
     * Destrói o gerenciador e limpa recursos
     */
    destroy() {
        console.debug('[DashboardTableManager] Destruindo gerenciador');

        // Limpa timeout pendente
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
            this.searchTimeout = null;
        }

        // Destrói sortable
        if (this.sortable) {
            this.sortable.destroy();
            this.sortable = null;
        }

        // Limpa referências
        this.container = null;
        this.searchInput = null;
        this.isInitialized = false;
    }
}

// Exporta para uso global
if (typeof window !== 'undefined') {
    window.DashboardTableManager = DashboardTableManager;
}

// Suporte a módulos ES6
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DashboardTableManager;
}
