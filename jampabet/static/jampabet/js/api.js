/**
 * JampaBet API Client
 * Módulo para comunicação com o backend Python
 */

const API = {
    // Configuração
    BASE_URL: 'http://localhost:8000/api',

    // Tokens de autenticação
    _accessToken: null,
    _refreshToken: null,

    /**
     * Inicializa o cliente da API
     */
    init() {
        // Carrega tokens do localStorage
        this._accessToken = localStorage.getItem('jampabet_access_token');
        this._refreshToken = localStorage.getItem('jampabet_refresh_token');
    },

    /**
     * Salva tokens no localStorage
     */
    _saveTokens(accessToken, refreshToken) {
        this._accessToken = accessToken;
        this._refreshToken = refreshToken;
        localStorage.setItem('jampabet_access_token', accessToken);
        localStorage.setItem('jampabet_refresh_token', refreshToken);
    },

    /**
     * Limpa tokens
     */
    _clearTokens() {
        this._accessToken = null;
        this._refreshToken = null;
        localStorage.removeItem('jampabet_access_token');
        localStorage.removeItem('jampabet_refresh_token');
    },

    /**
     * Verifica se está autenticado
     */
    isAuthenticated() {
        return !!this._accessToken;
    },

    /**
     * Faz requisição à API
     */
    async _request(endpoint, options = {}) {
        const url = `${this.BASE_URL}${endpoint}`;

        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };

        // Adiciona token de autenticação se disponível
        if (this._accessToken) {
            headers['Authorization'] = `Bearer ${this._accessToken}`;
        }

        try {
            const response = await fetch(url, {
                ...options,
                headers
            });

            // Se token expirou, tenta renovar
            if (response.status === 401 && this._refreshToken) {
                const refreshed = await this._refreshAccessToken();
                if (refreshed) {
                    // Refaz a requisição com novo token
                    headers['Authorization'] = `Bearer ${this._accessToken}`;
                    const retryResponse = await fetch(url, { ...options, headers });
                    return this._handleResponse(retryResponse);
                }
            }

            return this._handleResponse(response);
        } catch (error) {
            console.error('Erro na requisição:', error);
            throw new Error('Erro de conexão com o servidor');
        }
    },

    /**
     * Processa resposta da API
     */
    async _handleResponse(response) {
        if (response.status === 204) {
            return null; // No content
        }

        const data = await response.json().catch(() => null);

        if (!response.ok) {
            const errorMessage = data?.detail || 'Erro desconhecido';
            throw new Error(errorMessage);
        }

        return data;
    },

    /**
     * Renova o access token
     */
    async _refreshAccessToken() {
        try {
            const response = await fetch(`${this.BASE_URL}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: this._refreshToken })
            });

            if (response.ok) {
                const data = await response.json();
                this._saveTokens(data.access_token, data.refresh_token);
                return true;
            }

            // Refresh token inválido, faz logout
            this._clearTokens();
            return false;
        } catch (error) {
            console.error('Erro ao renovar token:', error);
            this._clearTokens();
            return false;
        }
    },

    // ==================== AUTH ====================

    /**
     * Registra um novo usuário
     */
    async register(name, email, password) {
        return this._request('/auth/register', {
            method: 'POST',
            body: JSON.stringify({ name, email, password })
        });
    },

    /**
     * Faz login do usuário
     */
    async login(email, password) {
        const data = await this._request('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password })
        });

        if (data.access_token) {
            this._saveTokens(data.access_token, data.refresh_token);
        }

        return data;
    },

    /**
     * Faz logout do usuário
     */
    async logout() {
        try {
            await this._request('/auth/logout', { method: 'POST' });
        } finally {
            this._clearTokens();
        }
    },

    /**
     * Obtém dados do usuário atual
     */
    async getCurrentUser() {
        return this._request('/auth/me');
    },

    // ==================== USERS ====================

    /**
     * Lista todos os usuários
     */
    async getUsers() {
        return this._request('/users');
    },

    /**
     * Obtém ranking de usuários
     */
    async getRanking(limit = 100) {
        return this._request(`/users/ranking?limit=${limit}`);
    },

    /**
     * Obtém perfil do usuário atual
     */
    async getMyProfile() {
        return this._request('/users/me');
    },

    /**
     * Atualiza perfil do usuário atual
     */
    async updateMyProfile(data) {
        return this._request('/users/me', {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    },

    /**
     * Obtém dados de um usuário específico
     */
    async getUser(userId) {
        return this._request(`/users/${userId}`);
    },

    // ==================== MATCHES ====================

    /**
     * Lista todas as partidas
     */
    async getMatches(status = null, skip = 0, limit = 100) {
        let endpoint = `/matches?skip=${skip}&limit=${limit}`;
        if (status) {
            endpoint += `&status=${status}`;
        }
        return this._request(endpoint);
    },

    /**
     * Obtém próximas partidas
     */
    async getUpcomingMatches(limit = 10) {
        return this._request(`/matches/upcoming?limit=${limit}`);
    },

    /**
     * Obtém a partida de hoje
     */
    async getTodayMatch() {
        return this._request('/matches/today');
    },

    /**
     * Obtém partidas finalizadas
     */
    async getFinishedMatches(limit = 20) {
        return this._request(`/matches/finished?limit=${limit}`);
    },

    /**
     * Obtém uma partida específica
     */
    async getMatch(matchId) {
        return this._request(`/matches/${matchId}`);
    },

    /**
     * Cria uma nova partida (admin)
     */
    async createMatch(matchData) {
        return this._request('/matches', {
            method: 'POST',
            body: JSON.stringify(matchData)
        });
    },

    /**
     * Atualiza uma partida (admin)
     */
    async updateMatch(matchId, matchData) {
        return this._request(`/matches/${matchId}`, {
            method: 'PUT',
            body: JSON.stringify(matchData)
        });
    },

    /**
     * Registra resultado de uma partida (admin)
     */
    async registerResult(matchId, resultBahia, resultOpponent) {
        return this._request(`/matches/${matchId}/result`, {
            method: 'POST',
            body: JSON.stringify({
                result_bahia: resultBahia,
                result_opponent: resultOpponent
            })
        });
    },

    /**
     * Exclui uma partida (admin)
     */
    async deleteMatch(matchId) {
        return this._request(`/matches/${matchId}`, {
            method: 'DELETE'
        });
    },

    // ==================== BETS ====================

    /**
     * Obtém minhas apostas
     */
    async getMyBets() {
        return this._request('/bets');
    },

    /**
     * Obtém minha aposta para uma partida
     */
    async getMyBetForMatch(matchId) {
        try {
            return await this._request(`/bets/match/${matchId}`);
        } catch (error) {
            if (error.message.includes('não encontrada')) {
                return null;
            }
            throw error;
        }
    },

    /**
     * Cria uma nova aposta
     */
    async createBet(matchId, homeWinScore, drawScore) {
        return this._request('/bets', {
            method: 'POST',
            body: JSON.stringify({
                match_id: matchId,
                home_win_score: homeWinScore,
                draw_score: drawScore
            })
        });
    },

    /**
     * Atualiza uma aposta
     */
    async updateBet(betId, homeWinScore, drawScore) {
        return this._request(`/bets/${betId}`, {
            method: 'PUT',
            body: JSON.stringify({
                home_win_score: homeWinScore,
                draw_score: drawScore
            })
        });
    },

    /**
     * Exclui uma aposta
     */
    async deleteBet(betId) {
        return this._request(`/bets/${betId}`, {
            method: 'DELETE'
        });
    },

    // ==================== STANDINGS ====================

    /**
     * Obtém ligas disponíveis
     */
    async getAvailableLeagues() {
        return this._request('/standings/leagues');
    },

    /**
     * Obtém classificação de uma liga
     */
    async getStandings(leagueId, season = null) {
        let endpoint = `/standings/${leagueId}`;
        if (season) {
            endpoint += `?season=${season}`;
        }
        return this._request(endpoint);
    },

    // ==================== ADMIN ====================

    /**
     * Sincroniza partidas da API-Football
     */
    async syncMatches() {
        return this._request('/admin/sync-matches', {
            method: 'POST'
        });
    },

    /**
     * Atualiza partidas ao vivo
     */
    async updateLiveMatches() {
        return this._request('/admin/update-live', {
            method: 'POST'
        });
    },

    // ==================== HEALTH ====================

    /**
     * Verifica se o backend está online
     */
    async healthCheck() {
        try {
            const response = await fetch(`${this.BASE_URL.replace('/api', '')}/health`);
            return response.ok;
        } catch {
            return false;
        }
    }
};

// Inicializa ao carregar
API.init();

// Exporta para uso global
window.API = API;
