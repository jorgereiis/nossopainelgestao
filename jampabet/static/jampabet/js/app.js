// JampaBet - Sistema de Apostas entre Amigos
// Esporte Clube Bahia - Django Version

// ==================== CONFIGURAÇÕES ====================
const CONFIG = {
    BAHIA_TEAM_NAME: 'Bahia',
    BET_LOCK_MINUTES: 10
};

// ==================== ESCUDOS DOS TIMES ====================
const TEAM_BADGES = {
    'Bahia': 'https://logodetimes.com/times/bahia/logo-bahia-256.png',
    'Corinthians': 'https://logodetimes.com/times/corinthians/logo-corinthians-256.png',
    'Santos': 'https://logodetimes.com/times/santos/logo-santos-256.png',
    'Palmeiras': 'https://logodetimes.com/times/palmeiras/logo-palmeiras-256.png',
    'Botafogo': 'https://logodetimes.com/times/botafogo/logo-botafogo-256.png',
    'Flamengo': 'https://logodetimes.com/times/flamengo/logo-flamengo-256.png',
    'Grêmio': 'https://logodetimes.com/times/gremio/logo-gremio-256.png',
    'São Paulo': 'https://logodetimes.com/times/sao-paulo/logo-sao-paulo-256.png',
    'Bragantino': 'https://logodetimes.com/times/red-bull-bragantino/logo-red-bull-bragantino-256.png',
    'Fluminense': 'https://logodetimes.com/times/fluminense/logo-fluminense-256.png',
    'Internacional': 'https://logodetimes.com/times/internacional/logo-internacional-256.png',
    'Atlético-MG': 'https://logodetimes.com/times/atletico-mineiro/logo-atletico-mineiro-256.png',
    'Cruzeiro': 'https://logodetimes.com/times/cruzeiro/logo-cruzeiro-256.png',
    'Vasco': 'https://logodetimes.com/times/vasco-da-gama/logo-vasco-da-gama-256.png',
    'Fortaleza': 'https://logodetimes.com/times/fortaleza/logo-fortaleza-256.png',
    'Ceará': 'https://logodetimes.com/times/ceara/logo-ceara-256.png',
    'Sport': 'https://logodetimes.com/times/sport/logo-sport-256.png',
    'Athletico-PR': 'https://logodetimes.com/times/atletico-paranaense/logo-atletico-paranaense-256.png',
    'Coritiba': 'https://logodetimes.com/times/coritiba/logo-coritiba-256.png',
    'Goiás': 'https://logodetimes.com/times/goias/logo-goias-256.png',
    'Cuiabá': 'https://logodetimes.com/times/cuiaba/logo-cuiaba-256.png',
    'Juventude': 'https://logodetimes.com/times/juventude/logo-juventude-256.png',
    'Vitória': 'https://images.uncyc.org/pt/f/f5/Escudo_do_Vit%C3%B3ria_2024.png',
};

const DEFAULT_BADGE = 'data:image/svg+xml,' + encodeURIComponent(`
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="45" fill="#e5e7eb" stroke="#9ca3af" stroke-width="2"/>
  <text x="50" y="68" text-anchor="middle" fill="#6b7280" font-family="Arial" font-size="50" font-weight="bold">?</text>
</svg>
`);

// ==================== HELPER FUNCTIONS ====================
function getTeamBadge(teamName) {
    return TEAM_BADGES[teamName] || DEFAULT_BADGE;
}

function formatDate(dateStr) {
    const date = new Date(dateStr);
    const options = { weekday: 'short', day: '2-digit', month: 'short' };
    return date.toLocaleDateString('pt-BR', options).toUpperCase();
}

function formatTime(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

/**
 * Formata o status de uma partida ao vivo com base no periodo e tempo decorrido.
 * @param {string} period - Codigo do periodo (1H, HT, 2H, ET, P, etc.)
 * @param {number} elapsed - Tempo decorrido em minutos
 * @returns {string} Status formatado para exibicao
 */
function formatLiveStatus(period, elapsed) {
    if (!period && !elapsed) return 'Em andamento';

    const periodLabels = {
        '1H': '1º Tempo',
        'HT': 'Intervalo',
        '2H': '2º Tempo',
        'ET': 'Prorrogação',
        'BT': 'Intervalo Prorrogação',
        'P': 'Pênaltis',
        'SUSP': 'Suspenso',
        'INT': 'Interrompido',
        'LIVE': 'Ao Vivo'
    };

    // Se tem periodo especifico
    if (period) {
        const label = periodLabels[period] || period;

        // Intervalo nao precisa de tempo
        if (period === 'HT' || period === 'BT') {
            return label;
        }

        // Penaltis nao precisa de tempo
        if (period === 'P') {
            return label;
        }

        // Outros periodos mostram tempo
        if (elapsed) {
            return `${label} ${elapsed}'`;
        }

        return label;
    }

    // Fallback: so tem tempo
    if (elapsed) {
        return `${elapsed}'`;
    }

    return 'Em andamento';
}

function showToast(message, type = 'success') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i>
        <span>${message}</span>
    `;
    document.body.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 100);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ==================== SPLASH SCREEN ====================
function hideSplash() {
    const splash = document.getElementById('splash-screen');
    const app = document.getElementById('app');

    if (splash && app) {
        setTimeout(() => {
            splash.classList.add('fade-out');
            app.classList.remove('hidden');
        }, 1500);
    }
}

// ==================== CARD PRINCIPAL - PROXIMA PARTIDA ====================
let heroMatchData = null;
let countdownInterval = null;
let livePollingInterval = null;
let livePollingActive = false;

// Configuracoes de polling
const POLLING_CONFIG = {
    LIVE_INTERVAL: 20000,      // 20 segundos quando ao vivo
    UPCOMING_INTERVAL: 60000,  // 60 segundos quando aguardando inicio
    FINISHED_CHECK: 120000     // 2 minutos para verificar proxima partida apos encerramento
};

/**
 * Sistema inteligente de polling para partidas ao vivo.
 * - Detecta quando uma partida inicia (upcoming -> live)
 * - Atualiza frequentemente durante a partida
 * - Para apos encerramento (com uma atualizacao final)
 * - Retoma verificacao periodica para proxima partida
 */
function initLiveMatchPolling() {
    // Inicia verificacao com base no estado atual
    scheduleNextPoll();
}

function scheduleNextPoll() {
    // Limpa intervalo anterior se existir
    if (livePollingInterval) {
        clearTimeout(livePollingInterval);
        livePollingInterval = null;
    }

    if (!heroMatchData) {
        // Sem partida - verifica a cada 2 minutos
        livePollingInterval = setTimeout(async () => {
            await loadNextBahiaMatch();
            scheduleNextPoll();
        }, POLLING_CONFIG.FINISHED_CHECK);
        return;
    }

    const status = heroMatchData.status;
    const previousStatus = heroMatchData._previousStatus;

    // Partida ao vivo - polling frequente
    if (status === 'live') {
        livePollingActive = true;
        livePollingInterval = setTimeout(async () => {
            heroMatchData._previousStatus = status;
            await loadNextBahiaMatch();
            scheduleNextPoll();
        }, POLLING_CONFIG.LIVE_INTERVAL);
    }
    // Partida encerrada
    else if (status === 'finished') {
        // Se acabou de encerrar (transicao live -> finished), faz uma ultima atualizacao
        if (previousStatus === 'live' && livePollingActive) {
            console.log('[Polling] Partida encerrada - ultima atualizacao');
            livePollingActive = false;
            // Agenda verificacao para proxima partida
            livePollingInterval = setTimeout(async () => {
                await loadNextBahiaMatch();
                scheduleNextPoll();
            }, POLLING_CONFIG.FINISHED_CHECK);
        } else {
            // Partida ja estava encerrada - verifica periodicamente por nova partida
            livePollingInterval = setTimeout(async () => {
                await loadNextBahiaMatch();
                scheduleNextPoll();
            }, POLLING_CONFIG.FINISHED_CHECK);
        }
    }
    // Partida agendada (upcoming) - verifica se vai comecar
    else if (status === 'upcoming') {
        // Calcula tempo ate o inicio
        const matchDate = new Date(heroMatchData.date);
        const now = new Date();
        const timeUntilStart = matchDate - now;

        // Se falta menos de 5 minutos, verifica com mais frequencia
        if (timeUntilStart > 0 && timeUntilStart < 5 * 60 * 1000) {
            livePollingInterval = setTimeout(async () => {
                heroMatchData._previousStatus = status;
                await loadNextBahiaMatch();
                scheduleNextPoll();
            }, 15000); // 15 segundos quando perto de comecar
        }
        // Se ja passou do horario de inicio, verifica frequentemente (pode ter comecado)
        else if (timeUntilStart <= 0) {
            livePollingInterval = setTimeout(async () => {
                heroMatchData._previousStatus = status;
                await loadNextBahiaMatch();
                scheduleNextPoll();
            }, POLLING_CONFIG.LIVE_INTERVAL);
        }
        // Ainda falta tempo - verifica menos frequentemente
        else {
            livePollingInterval = setTimeout(async () => {
                heroMatchData._previousStatus = status;
                await loadNextBahiaMatch();
                scheduleNextPoll();
            }, POLLING_CONFIG.UPCOMING_INTERVAL);
        }
    }
    // Outros status (cancelled, postponed) - verifica periodicamente
    else {
        livePollingInterval = setTimeout(async () => {
            await loadNextBahiaMatch();
            scheduleNextPoll();
        }, POLLING_CONFIG.FINISHED_CHECK);
    }
}

async function loadNextBahiaMatch() {
    try {
        const response = await fetch('/app/bahia/api/matches/next/', {
            credentials: 'same-origin'
        });
        const data = await response.json();

        if (data.match) {
            heroMatchData = data.match;
            updateHeroCard(data.match);
            startCountdown(data.match);
        } else {
            showNoMatchState();
        }
    } catch (error) {
        console.error('Erro ao carregar proxima partida:', error);
        showNoMatchState();
    }
}

function updateHeroCard(match) {
    const card = document.getElementById('next-match-hero');
    if (!card) return;

    card.dataset.matchId = match.id;

    // Times
    const homeLogo = document.querySelector('#hero-home-logo img');
    const awayLogo = document.querySelector('#hero-away-logo img');
    if (homeLogo) homeLogo.src = match.home_team_logo || getTeamBadge(match.home_team);
    if (awayLogo) awayLogo.src = match.away_team_logo || getTeamBadge(match.away_team);

    document.getElementById('hero-home-name').textContent = match.home_team;
    document.getElementById('hero-away-name').textContent = match.away_team;

    // Competicao
    document.getElementById('hero-match-competition').textContent = match.competition;

    // Local da partida
    const venueEl = document.getElementById('hero-venue');
    const venueTextEl = document.getElementById('hero-venue-text');
    if (venueEl && venueTextEl) {
        if (match.venue) {
            venueTextEl.textContent = match.venue;
            venueEl.classList.remove('hidden');
        } else {
            venueEl.classList.add('hidden');
        }
    }

    // Elementos do card
    const badge = document.getElementById('hero-match-badge');
    const matchDetails = document.getElementById('hero-match-details');
    const timeContainer = document.getElementById('hero-time-container');
    const scoreContainer = document.getElementById('hero-score-container');
    const countdownEl = document.getElementById('hero-bet-countdown');
    const actionEl = document.getElementById('hero-action');
    const userBetEl = document.getElementById('hero-user-bet');

    // Remove classes de status anteriores
    card.classList.remove('status-live', 'status-finished', 'status-upcoming');
    badge.classList.remove('live', 'finished');

    if (match.status === 'live') {
        // ========== AO VIVO ==========
        card.classList.add('status-live');
        badge.innerHTML = '<i class="fas fa-circle pulse"></i> <span>AO VIVO</span>';
        badge.classList.add('live');

        // Esconde bloco de detalhes (competicao, horario, data)
        if (matchDetails) matchDetails.classList.add('hidden');

        // Mostra placar no centro
        scoreContainer.classList.remove('hidden');
        const homeGoals = match.result_bahia ?? 0;
        const awayGoals = match.result_opponent ?? 0;
        if (match.location === 'home') {
            document.getElementById('hero-match-score').textContent = `${homeGoals} x ${awayGoals}`;
        } else {
            document.getElementById('hero-match-score').textContent = `${awayGoals} x ${homeGoals}`;
        }
        document.getElementById('hero-status-text').textContent = formatLiveStatus(match.live_period, match.elapsed_time);

        // Esconde countdown e botao
        countdownEl.classList.add('hidden');
        actionEl.innerHTML = '<div class="match-live-info"><i class="fas fa-tv"></i> Partida em andamento</div>';

    } else if (match.status === 'finished') {
        // ========== ENCERRADO ==========
        card.classList.add('status-finished');
        badge.innerHTML = '<i class="fas fa-flag-checkered"></i> <span>ENCERRADO</span>';
        badge.classList.add('finished');

        // Esconde bloco de detalhes (competicao, horario, data)
        if (matchDetails) matchDetails.classList.add('hidden');

        // Mostra placar final no centro
        scoreContainer.classList.remove('hidden');
        const homeGoals = match.result_bahia ?? '-';
        const awayGoals = match.result_opponent ?? '-';
        if (match.location === 'home') {
            document.getElementById('hero-match-score').textContent = `${homeGoals} x ${awayGoals}`;
        } else {
            document.getElementById('hero-match-score').textContent = `${awayGoals} x ${homeGoals}`;
        }
        document.getElementById('hero-status-text').textContent = 'Final';

        // Esconde countdown e action
        countdownEl.classList.add('hidden');
        actionEl.innerHTML = '';

    } else {
        // ========== AGENDADO (upcoming) ==========
        card.classList.add('status-upcoming');
        badge.innerHTML = '<i class="fas fa-fire"></i> <span>PROXIMO JOGO</span>';

        // Mostra bloco de detalhes (competicao, horario, data, local)
        if (matchDetails) matchDetails.classList.remove('hidden');
        scoreContainer.classList.add('hidden');

        // Preenche horario e data
        document.getElementById('hero-match-time').textContent = formatTime(match.date);
        document.getElementById('hero-match-date').textContent = formatDate(match.date);

        // Countdown e botao de palpite
        if (match.can_bet) {
            countdownEl.classList.remove('hidden');
            actionEl.innerHTML = `
                <button class="btn btn-glow" id="hero-bet-btn" onclick="openBetModal(${match.id}, heroMatchData)">
                    <i class="fas fa-bolt"></i> ${match.user_bet ? 'ALTERAR PALPITE' : 'FAZER PALPITE'}
                </button>
            `;
        } else {
            countdownEl.classList.add('hidden');
            actionEl.innerHTML = '<div class="bet-locked-info"><i class="fas fa-lock"></i> Palpites encerrados</div>';
        }
    }

    // Mostra palpite do usuario se existir
    if (match.user_bet) {
        userBetEl.classList.remove('hidden');
        document.getElementById('hero-bet-vitoria').textContent =
            `Triunfo: ${match.user_bet.home_win_bahia} x ${match.user_bet.home_win_opponent}`;
        document.getElementById('hero-bet-empate').textContent =
            `Empate: ${match.user_bet.draw_bahia} x ${match.user_bet.draw_opponent}`;

        // Aplica cor e icone baseado no resultado
        const betIcon = document.getElementById('hero-bet-icon');
        userBetEl.classList.remove('bet-result-win', 'bet-result-loss');
        if (match.status === 'finished' && match.bet_result) {
            if (match.bet_result === 'hit') {
                userBetEl.classList.add('bet-result-win');
                betIcon.className = 'fas fa-check-circle';
            } else if (match.bet_result === 'miss') {
                userBetEl.classList.add('bet-result-loss');
                betIcon.className = 'fas fa-times-circle';
            }
        } else {
            // Partida nao finalizada - icone padrao
            betIcon.className = 'fas fa-check-circle';
        }
    } else {
        userBetEl.classList.add('hidden');
    }
}

function startCountdown(match) {
    if (countdownInterval) clearInterval(countdownInterval);

    const countdownTimer = document.getElementById('hero-countdown-timer');
    const countdownEl = document.getElementById('hero-bet-countdown');
    if (!countdownTimer || !match.can_bet) return;

    const matchDate = new Date(match.date);
    const lockTime = new Date(matchDate.getTime() - CONFIG.BET_LOCK_MINUTES * 60 * 1000);

    function updateCountdown() {
        const now = new Date();
        const diff = lockTime - now;

        if (diff <= 0) {
            countdownTimer.textContent = 'Encerrado';
            countdownEl.classList.add('expired');
            clearInterval(countdownInterval);
            // Recarrega para atualizar o card
            setTimeout(() => loadNextBahiaMatch(), 2000);
            return;
        }

        const days = Math.floor(diff / (1000 * 60 * 60 * 24));
        const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((diff % (1000 * 60)) / 1000);

        if (days > 0) {
            countdownTimer.textContent = `${days}d ${hours}h ${minutes}min`;
        } else if (hours > 0) {
            countdownTimer.textContent = `${hours}h ${minutes}min ${seconds}s`;
        } else if (minutes > 0) {
            countdownTimer.textContent = `${minutes}min ${seconds}s`;
        } else {
            countdownTimer.textContent = `${seconds}s`;
            countdownEl.classList.add('urgent');
        }
    }

    updateCountdown();
    countdownInterval = setInterval(updateCountdown, 1000);
}

function showNoMatchState() {
    const card = document.getElementById('next-match-hero');
    if (!card) return;

    card.innerHTML = `
        <div class="no-match-state">
            <i class="fas fa-calendar-times"></i>
            <p>Nenhuma partida proxima</p>
            <small>Aguarde a definicao dos proximos jogos</small>
        </div>
    `;
}

// ==================== AREA DE PALPITES ====================
async function loadBetsHistory() {
    const container = document.getElementById('palpites-container');
    if (!container) return;

    try {
        const response = await fetch('/app/bahia/api/bets/history/', {
            credentials: 'same-origin'
        });

        if (response.status === 401) {
            container.innerHTML = '<div class="empty-state"><i class="fas fa-lock"></i><p>Faca login para ver seus palpites</p></div>';
            return;
        }

        const data = await response.json();
        renderBetsHistory(data);
    } catch (error) {
        console.error('Erro ao carregar historico:', error);
        container.innerHTML = '<div class="empty-state"><i class="fas fa-exclamation-triangle"></i><p>Erro ao carregar palpites</p></div>';
    }
}

function renderBetsHistory(data) {
    const container = document.getElementById('palpites-container');
    if (!container) return;

    let html = '';

    // Partidas recentes (sempre visiveis)
    if (data.recent && data.recent.length > 0) {
        html += '<div class="palpites-section"><h3><i class="fas fa-history"></i> Ultimas Partidas</h3>';
        data.recent.forEach(match => {
            html += renderPalpiteCard(match, true);
        });
        html += '</div>';
    }

    // Partidas antigas (colapsavel)
    if (data.older && data.older.length > 0) {
        html += `
            <div class="palpites-anteriores">
                <button class="btn-ver-anteriores" id="btn-ver-anteriores">
                    <i class="fas fa-history"></i>
                    <span>Ver palpites anteriores (${data.older.length})</span>
                    <i class="fas fa-chevron-down arrow-icon"></i>
                </button>
                <div class="palpites-anteriores-lista" id="palpites-anteriores-lista">
                    ${data.older.map(match => renderPalpiteCard(match, true)).join('')}
                </div>
            </div>
        `;
    }

    // Estado vazio
    if (!data.recent?.length && !data.older?.length) {
        html = `
            <div class="empty-state">
                <i class="fas fa-ticket-alt"></i>
                <p>Voce ainda nao fez nenhum palpite</p>
                <small>Clique em "Fazer Palpite" no proximo jogo!</small>
            </div>
        `;
    }

    container.innerHTML = html;

    // Adiciona evento ao botao de ver anteriores
    const btnAnteriores = document.getElementById('btn-ver-anteriores');
    if (btnAnteriores) {
        btnAnteriores.addEventListener('click', togglePalpitesAnteriores);
    }
}

function renderPalpiteCard(match, isFinished) {
    // Determina classe de resultado
    let resultClass = '';
    if (match.bet_result === 'hit') resultClass = 'result-hit';
    else if (match.bet_result === 'miss') resultClass = 'result-miss';
    else if (match.bet_result === 'none') resultClass = 'result-none';

    const date = new Date(match.date);
    const dateStr = date.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit' });
    const timeStr = date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

    // Placar final (se encerrado)
    let scoreHtml = '';
    if (isFinished && match.result_bahia !== null) {
        const homeGoals = match.location === 'home' ? match.result_bahia : match.result_opponent;
        const awayGoals = match.location === 'home' ? match.result_opponent : match.result_bahia;
        scoreHtml = `
            <div class="palpite-result-placar">
                <i class="fas fa-futbol"></i>
                <span class="placar">${homeGoals} x ${awayGoals}</span>
            </div>
        `;
    }

    // Badge de resultado (ganhou/perdeu)
    let resultBadgeHtml = '';
    if (isFinished && match.bet) {
        if (match.bet_result === 'hit') {
            resultBadgeHtml = `
                <div class="palpite-result-badge result-win">
                    <i class="fas fa-trophy"></i>
                    <span>ACERTOU!</span>
                    <span class="result-points">+${match.bet.points_earned} pts</span>
                </div>
            `;
        } else if (match.bet_result === 'miss') {
            resultBadgeHtml = `
                <div class="palpite-result-badge result-loss">
                    <i class="fas fa-times-circle"></i>
                    <span>NAO ACERTOU</span>
                </div>
            `;
        }
    }

    // Palpite do usuario
    let betHtml = '';
    if (match.bet) {
        if (isFinished) {
            // Partida encerrada - mostra apenas o badge de resultado
            betHtml = resultBadgeHtml;
        } else {
            // Partida ainda nao encerrada - mostra os palpites
            betHtml = `
                <div class="palpite-user-bet">
                    <span class="bet-label"><i class="fas fa-check-circle"></i> Seu palpite:</span>
                    <div class="bet-values">
                        <span class="bet-value">
                            <i class="fas fa-hand-point-up"></i> Triunfo ${match.bet.home_win_bahia}x${match.bet.home_win_opponent}
                        </span>
                        <span class="bet-separator">|</span>
                        <span class="bet-value">
                            <i class="fas fa-handshake"></i> Empate ${match.bet.draw_bahia}x${match.bet.draw_opponent}
                        </span>
                    </div>
                </div>
            `;
        }
    } else if (isFinished) {
        betHtml = `
            <div class="palpite-no-bet">
                <i class="fas fa-times-circle"></i> Sem palpite registrado
            </div>
        `;
    }

    // Botao de acao
    let actionHtml = '';
    if (!isFinished) {
        if (match.can_bet) {
            actionHtml = `
                <button class="btn btn-bet-small" onclick="openBetModal(${match.id})">
                    <i class="fas fa-${match.bet ? 'edit' : 'ticket-alt'}"></i>
                    ${match.bet ? 'Alterar' : 'Palpitar'}
                </button>
            `;
        } else {
            actionHtml = `
                <span class="bet-locked"><i class="fas fa-lock"></i> Bloqueado</span>
            `;
        }
    }

    return `
        <div class="palpite-card ${resultClass}" data-match-id="${match.id}">
            <div class="palpite-header">
                <span class="palpite-competition">${match.competition}</span>
                <span class="palpite-date">${dateStr} - ${timeStr}</span>
            </div>
            <div class="palpite-teams">
                <div class="palpite-team">
                    <img src="${match.home_team_logo || getTeamBadge(match.home_team)}" alt="${match.home_team}" class="palpite-team-logo">
                    <span class="palpite-team-name">${match.home_team}</span>
                </div>
                <span class="palpite-vs">VS</span>
                <div class="palpite-team">
                    <img src="${match.away_team_logo || getTeamBadge(match.away_team)}" alt="${match.away_team}" class="palpite-team-logo">
                    <span class="palpite-team-name">${match.away_team}</span>
                </div>
            </div>
            ${scoreHtml}
            ${betHtml}
            <div class="palpite-action">
                ${actionHtml}
            </div>
        </div>
    `;
}

function togglePalpitesAnteriores() {
    const lista = document.getElementById('palpites-anteriores-lista');
    const btn = document.getElementById('btn-ver-anteriores');
    if (!lista || !btn) return;

    lista.classList.toggle('expanded');
    btn.classList.toggle('expanded');

    const span = btn.querySelector('span');
    const arrow = btn.querySelector('.arrow-icon');

    if (lista.classList.contains('expanded')) {
        span.textContent = 'Ocultar palpites anteriores';
        if (arrow) arrow.style.transform = 'rotate(180deg)';
    } else {
        const count = lista.querySelectorAll('.palpite-card').length;
        span.textContent = `Ver palpites anteriores (${count})`;
        if (arrow) arrow.style.transform = 'rotate(0deg)';
    }
}

// ==================== RANKING ====================
async function loadRanking() {
    const podiumEl = document.getElementById('podium');
    const listEl = document.getElementById('ranking-list');
    const totalEl = document.querySelector('#ranking-total-players span');
    const positionEl = document.getElementById('stat-position');

    if (!podiumEl) return;

    try {
        const response = await fetch('/app/bahia/api/ranking/', {
            credentials: 'same-origin'
        });
        const data = await response.json();

        // Atualiza total de participantes
        if (totalEl) {
            totalEl.textContent = data.total_players || 0;
        }

        // Atualiza posicao do usuario no card de stats
        if (positionEl && data.current_user_position) {
            positionEl.textContent = `${data.current_user_position}º`;
        }

        // Renderiza podio
        renderPodium(data.top3 || []);

        // Renderiza lista
        renderRankingList(data.ranking || [], data.current_user);

    } catch (error) {
        console.error('Erro ao carregar ranking:', error);
        podiumEl.innerHTML = '<div class="empty-state"><i class="fas fa-exclamation-triangle"></i><p>Erro ao carregar ranking</p></div>';
    }
}

function renderPodium(top3) {
    const podiumEl = document.getElementById('podium');
    if (!podiumEl || top3.length === 0) {
        podiumEl.innerHTML = '<div class="empty-state"><i class="fas fa-trophy"></i><p>Ainda nao ha participantes</p></div>';
        return;
    }

    // Ordem visual do podio: 2º, 1º, 3º
    const podiumOrder = [1, 0, 2];

    const getMedalIcon = (position) => {
        switch(position) {
            case 1: return '<i class="fas fa-trophy"></i>';
            case 2: return '<i class="fas fa-medal"></i>';
            case 3: return '<i class="fas fa-medal"></i>';
            default: return position;
        }
    };

    const getMedalClass = (position) => {
        switch(position) {
            case 1: return 'medal-gold';
            case 2: return 'medal-silver';
            case 3: return 'medal-bronze';
            default: return '';
        }
    };

    let html = '<div class="podium-container">';

    podiumOrder.forEach(index => {
        const user = top3[index];
        if (!user) {
            html += '<div class="podium-place empty"></div>';
            return;
        }

        const position = index + 1;
        const initial = user.name.charAt(0).toUpperCase();

        html += `
            <div class="podium-place place-${position} ${user.is_current_user ? 'current-user' : ''}">
                <div class="podium-avatar">
                    <span>${initial}</span>
                    <div class="podium-medal ${getMedalClass(position)}">
                        ${getMedalIcon(position)}
                    </div>
                </div>
                <div class="podium-info">
                    <span class="podium-name">${user.name}</span>
                    <span class="podium-points">${user.points} pts</span>
                    <span class="podium-stats">${user.hits} acertos</span>
                </div>
                <div class="podium-bar"></div>
            </div>
        `;
    });

    html += '</div>';
    podiumEl.innerHTML = html;
}

function renderRankingList(ranking, currentUserOutside) {
    const listEl = document.getElementById('ranking-list');
    if (!listEl) return;

    if (ranking.length === 0 && !currentUserOutside) {
        listEl.innerHTML = '';
        return;
    }

    let html = '<div class="ranking-table">';

    // Header
    html += `
        <div class="ranking-header">
            <span class="ranking-col-pos">#</span>
            <span class="ranking-col-user">Participante</span>
            <span class="ranking-col-hits">Acertos</span>
            <span class="ranking-col-bets">Palpites</span>
            <span class="ranking-col-points">Pontos</span>
        </div>
    `;

    // Linhas do ranking
    ranking.forEach(user => {
        const initial = user.name.charAt(0).toUpperCase();

        html += `
            <div class="ranking-row ${user.is_current_user ? 'current-user' : ''}">
                <span class="ranking-position">${user.position}º</span>
                <div class="ranking-user">
                    <div class="ranking-avatar">
                        <span>${initial}</span>
                    </div>
                    <span class="ranking-name">${user.name}</span>
                </div>
                <span class="ranking-hits">${user.hits}</span>
                <span class="ranking-bets">${user.total_bets || 0}</span>
                <span class="ranking-points">${user.points}</span>
            </div>
        `;
    });

    // Usuario atual fora do top 10
    if (currentUserOutside) {
        const initial = currentUserOutside.name.charAt(0).toUpperCase();

        html += `
            <div class="ranking-row-separator">
                <span>• • •</span>
            </div>
            <div class="ranking-row current-user highlight">
                <span class="ranking-position">${currentUserOutside.position}º</span>
                <div class="ranking-user">
                    <div class="ranking-avatar">
                        <span>${initial}</span>
                    </div>
                    <span class="ranking-name">${currentUserOutside.name} <small>(voce)</small></span>
                </div>
                <span class="ranking-hits">${currentUserOutside.hits}</span>
                <span class="ranking-bets">${currentUserOutside.total_bets || 0}</span>
                <span class="ranking-points">${currentUserOutside.points}</span>
            </div>
        `;
    }

    html += '</div>';
    listEl.innerHTML = html;
}

// ==================== TABS ====================
function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn, .bottom-nav-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;

            // Remove active de todos
            tabButtons.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            // Ativa o selecionado
            btn.classList.add('active');
            document.querySelectorAll(`[data-tab="${tab}"]`).forEach(b => b.classList.add('active'));
            document.getElementById(tab)?.classList.add('active');

            // Se clicou na aba Tabela (classificacao), sincroniza com a competicao da partida em destaque
            if (tab === 'classificacao' && heroMatchData && heroMatchData.competition_id) {
                const standingsSelect = document.getElementById('standings-select');
                if (standingsSelect) {
                    const competitionId = heroMatchData.competition_id.toString();
                    // Verifica se a competicao existe no select
                    const optionExists = Array.from(standingsSelect.options).some(opt => opt.value === competitionId);
                    if (optionExists && standingsSelect.value !== competitionId) {
                        standingsSelect.value = competitionId;
                        // Dispara o evento de change para carregar a nova competicao
                        roundsCache = {};
                        roundsData = [];
                        loadStandings(parseInt(competitionId));
                    }
                }
            }
        });
    });
}

// ==================== BET MODAL ====================
function initBetModal() {
    const modal = document.getElementById('bet-modal');
    const closeBtn = document.getElementById('close-bet-modal');
    const confirmBtn = document.getElementById('confirm-bet-btn');
    const inputs = document.querySelectorAll('.score-input');

    if (closeBtn) {
        closeBtn.addEventListener('click', () => modal?.classList.remove('active'));
    }

    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.classList.remove('active');
        });
    }

    // Validação dos inputs
    inputs.forEach(input => {
        input.addEventListener('input', validateBetInputs);
    });
}

function validateBetInputs() {
    const homeWinBahia = parseInt(document.getElementById('home-win-bahia')?.value) || 0;
    const homeWinOpponent = parseInt(document.getElementById('home-win-opponent')?.value) || 0;
    const drawBahia = parseInt(document.getElementById('draw-bahia')?.value) || 0;
    const drawOpponent = parseInt(document.getElementById('draw-opponent')?.value) || 0;

    const confirmBtn = document.getElementById('confirm-bet-btn');
    const homeWinOption = document.querySelector('.score-bet-option:first-child');
    const drawOption = document.querySelector('.score-bet-option:last-child');

    // Validação Vitória
    const homeWinValid = homeWinBahia > homeWinOpponent;
    homeWinOption?.classList.toggle('valid', homeWinValid && homeWinBahia > 0);
    homeWinOption?.classList.toggle('invalid', !homeWinValid && homeWinBahia > 0);

    // Validação Empate
    const drawValid = drawBahia === drawOpponent && drawBahia >= 0;
    drawOption?.classList.toggle('valid', drawValid && drawBahia >= 0 && drawOpponent >= 0);
    drawOption?.classList.toggle('invalid', !drawValid && (drawBahia > 0 || drawOpponent > 0));

    // Habilita botão se ambos válidos
    if (confirmBtn) {
        confirmBtn.disabled = !(homeWinValid && drawValid);
    }
}

async function openBetModal(matchId, matchData, viewOnly = false) {
    const modal = document.getElementById('bet-modal');
    if (!modal) return;

    // Sempre busca dados atualizados via API para garantir consistencia
    // Isso evita problemas de cache ou dados desatualizados
    if (matchId) {
        try {
            const response = await fetch(`/app/bahia/api/matches/${matchId}/`, {
                credentials: 'same-origin'
            });
            if (!response.ok) {
                showToast('Erro ao carregar dados da partida', 'error');
                return;
            }
            const data = await response.json();
            matchData = data.match;
        } catch (error) {
            console.error('Erro ao buscar partida:', error);
            showToast('Erro ao carregar dados da partida', 'error');
            return;
        }
    }

    // Validacao: nao abre modal sem partida
    if (!matchData || !matchId) {
        showToast('Nenhuma partida disponivel para palpite', 'error');
        return;
    }

    // Determina se eh partida encerrada ou em andamento
    const isFinished = matchData.status === 'FT' || matchData.status === 'finished';
    const isLive = matchData.status === 'LIVE' || matchData.status === 'live' ||
        matchData.status === '1H' || matchData.status === '2H' || matchData.status === 'HT';

    // Calcula tempo ate a partida
    const matchDate = matchData.date ? new Date(matchData.date) : null;
    const now = new Date();
    const minutesUntilMatch = matchDate ? (matchDate - now) / (1000 * 60) : -1;

    // Usa can_bet da API se disponivel (mais confiavel), senao calcula localmente
    // can_bet da API ja considera status e tempo
    let canBet;
    if (matchData.can_bet !== undefined) {
        canBet = matchData.can_bet;
    } else {
        // Fallback: calcula localmente
        canBet = !isFinished && !isLive && minutesUntilMatch >= CONFIG.BET_LOCK_MINUTES;
    }

    // Se nao pode apostar, verifica se abre em modo visualizacao ou mostra erro
    if (!viewOnly && !canBet) {
        // Abre em modo visualizacao se tiver palpite do usuario
        if (matchData.user_bet) {
            openBetModal(matchId, matchData, true);
            return;
        } else {
            // Sem palpite, apenas mostra mensagem
            if (isFinished) {
                showToast('Partida encerrada. Voce nao fez palpite.', 'error');
            } else if (isLive) {
                showToast('Partida em andamento. Palpites encerrados!', 'error');
            } else {
                showToast('Palpites encerrados para esta partida', 'error');
            }
            return;
        }
    }

    // NOTA: Se canBet=true e usuario ja tem palpite, permite edicao (nao bloqueia)

    // Determina times
    const homeTeam = matchData.home_team || 'Time Casa';
    const awayTeam = matchData.away_team || 'Time Fora';
    const isHomeBahia = homeTeam.toLowerCase().includes('bahia');
    const opponentName = isHomeBahia ? awayTeam : homeTeam;
    const opponentLogo = isHomeBahia ? (matchData.away_team_logo || getTeamBadge(awayTeam)) : (matchData.home_team_logo || getTeamBadge(homeTeam));

    // Atualiza nomes nos elementos
    const opponentNameEl = document.getElementById('bet-opponent-name');
    const opponentName1El = document.getElementById('score-opponent-name-1');
    const opponentName2El = document.getElementById('score-opponent-name-2');

    if (opponentNameEl) opponentNameEl.textContent = opponentName;
    if (opponentName1El) opponentName1El.textContent = opponentName;
    if (opponentName2El) opponentName2El.textContent = opponentName;

    // Atualiza info do jogo
    const dateEl = document.getElementById('bet-match-date');
    const compEl = document.getElementById('bet-match-competition');
    const venueEl = document.getElementById('bet-match-venue');

    if (dateEl && matchDate && !isNaN(matchDate.getTime())) {
        dateEl.textContent = formatDate(matchData.date) + ' - ' + formatTime(matchData.date);
    } else if (dateEl) {
        dateEl.textContent = 'Data a definir';
    }

    if (compEl) {
        compEl.textContent = matchData.competition || '';
    }
    if (venueEl) {
        venueEl.textContent = matchData.venue || '';
    }

    // Atualiza logos
    const bahiaLogoEl = document.querySelector('#bet-bahia-logo img');
    const opponentLogoEl = document.querySelector('#bet-opponent-logo img');

    if (bahiaLogoEl) {
        bahiaLogoEl.src = getTeamBadge('Bahia');
        bahiaLogoEl.alt = 'Bahia';
    }
    if (opponentLogoEl) {
        opponentLogoEl.src = opponentLogo;
        opponentLogoEl.alt = opponentName;
    }

    // Atualiza VS/Placar entre os escudos
    const vsScoreEl = document.getElementById('bet-vs-score');
    if (vsScoreEl) {
        if (matchData.status === 'finished' && matchData.result_bahia !== null && matchData.result_opponent !== null) {
            // Partida encerrada - exibe placar
            vsScoreEl.textContent = `${matchData.result_bahia} x ${matchData.result_opponent}`;
            vsScoreEl.classList.add('bet-score-result');
        } else {
            // Partida nao encerrada - exibe VS
            vsScoreEl.textContent = 'VS';
            vsScoreEl.classList.remove('bet-score-result');
        }
    }

    // Atualiza indicador de mando (casa/fora) baseado no status da partida
    const mandoEl = document.getElementById('bet-mando-info');
    if (mandoEl) {
        // Usa o campo location se disponivel, senao deduz pelo home_team
        const isHome = matchData.location === 'home' || isHomeBahia;

        // Define verbo baseado no status da partida
        let verbo;
        if (matchData.status === 'finished') {
            verbo = 'jogou';
        } else if (matchData.status === 'live') {
            verbo = 'jogando';
        } else {
            verbo = 'jogará';
        }

        if (isHome) {
            mandoEl.innerHTML = `<i class="fas fa-home"></i> Bahia ${verbo} em casa`;
            mandoEl.className = 'bet-mando-info mando-home';
        } else {
            mandoEl.innerHTML = `<i class="fas fa-plane"></i> Bahia ${verbo} fora`;
            mandoEl.className = 'bet-mando-info mando-away';
        }
    }

    // Atualiza countdown no modal
    const countdownEl = document.getElementById('bet-countdown');
    if (countdownEl) {
        countdownEl.classList.remove('urgent', 'hidden', 'finished', 'live');

        if (viewOnly) {
            // Modo visualizacao - esconde countdown
            countdownEl.classList.add('hidden');
        } else if (matchDate && !isNaN(matchDate.getTime()) && minutesUntilMatch > 0) {
            const hours = Math.floor(minutesUntilMatch / 60);
            const mins = Math.floor(minutesUntilMatch % 60);
            if (hours > 24) {
                const days = Math.floor(hours / 24);
                countdownEl.innerHTML = `<i class="fas fa-clock"></i> Palpites encerram em ${days}d ${hours % 24}h`;
            } else if (hours > 0) {
                countdownEl.innerHTML = `<i class="fas fa-clock"></i> Palpites encerram em ${hours}h ${mins}min`;
            } else {
                countdownEl.innerHTML = `<i class="fas fa-clock"></i> Palpites encerram em ${mins}min`;
                if (mins < 30) {
                    countdownEl.classList.add('urgent');
                }
            }
        } else {
            countdownEl.innerHTML = '<i class="fas fa-clock"></i> Palpites encerram em breve';
        }
    }

    // Verifica se eh edicao (usuario ja tem palpite mas ainda pode editar)
    const isEditing = !viewOnly && matchData.user_bet && canBet;

    // Atualiza titulo do modal
    const modalTitle = modal.querySelector('.modal-header h2');
    if (modalTitle) {
        if (viewOnly) {
            modalTitle.innerHTML = '<i class="fas fa-eye"></i> Seu Palpite';
        } else if (isEditing) {
            modalTitle.innerHTML = '<i class="fas fa-edit"></i> Editar Palpite';
        } else {
            modalTitle.innerHTML = '<i class="fas fa-futbol"></i> Fazer Palpite';
        }
    }

    // Configura inputs e botoes
    const inputs = modal.querySelectorAll('.score-input');
    const confirmBtn = document.getElementById('confirm-bet-btn');
    const rulesEl = modal.querySelector('.bet-rules');
    const disclaimerEl = modal.querySelector('.bet-disclaimer');

    if (viewOnly && matchData.user_bet) {
        // Modo visualizacao - preenche com palpite do usuario
        const bet = matchData.user_bet;

        document.getElementById('home-win-bahia').value = bet.home_win_bahia ?? '';
        document.getElementById('home-win-opponent').value = bet.home_win_opponent ?? '';
        document.getElementById('draw-bahia').value = bet.draw_bahia ?? '';
        document.getElementById('draw-opponent').value = bet.draw_opponent ?? '';

        // Desabilita inputs
        inputs.forEach(input => {
            input.disabled = true;
            input.classList.add('readonly');
        });

        // Esconde botao e regras
        if (confirmBtn) confirmBtn.classList.add('hidden');
        if (rulesEl) rulesEl.classList.add('hidden');
        if (disclaimerEl) {
            // Mostra resultado se partida encerrada
            if (isFinished && bet.points_earned !== undefined) {
                const points = bet.points_earned || 0;
                if (points > 0) {
                    disclaimerEl.innerHTML = `<i class="fas fa-trophy"></i> ACERTOU! <strong>+${points} ponto${points > 1 ? 's' : ''}</strong>`;
                    disclaimerEl.classList.add('result-win');
                } else {
                    disclaimerEl.innerHTML = '<i class="fas fa-times-circle"></i> NAO ACERTOU';
                    disclaimerEl.classList.add('result-loss');
                }
            } else {
                disclaimerEl.innerHTML = '<i class="fas fa-hourglass-half"></i> Aguardando resultado da partida';
            }
        }

        // Marca opcoes com cor baseada no resultado
        const betOptionWin = document.getElementById('bet-option-win');
        const betOptionDraw = document.getElementById('bet-option-draw');

        // Remove classes anteriores
        [betOptionWin, betOptionDraw].forEach(opt => {
            if (opt) opt.classList.remove('valid', 'invalid', 'view-mode', 'bet-win', 'bet-loss');
        });

        if (isFinished && matchData.result_bahia !== undefined) {
            const points = bet.points_earned || 0;
            const resultClass = points > 0 ? 'bet-win' : 'bet-loss';

            if (matchData.result_bahia > matchData.result_opponent) {
                // Bahia venceu - palpite de vitoria foi considerado
                if (betOptionWin) betOptionWin.classList.add(resultClass, 'view-mode');
                if (betOptionDraw) betOptionDraw.classList.add('view-mode', 'bet-not-used');
            } else if (matchData.result_bahia === matchData.result_opponent) {
                // Empate - palpite de empate foi considerado
                if (betOptionDraw) betOptionDraw.classList.add(resultClass, 'view-mode');
                if (betOptionWin) betOptionWin.classList.add('view-mode', 'bet-not-used');
            } else {
                // Bahia perdeu - nenhum palpite aplicavel
                if (betOptionWin) betOptionWin.classList.add('view-mode', 'bet-not-used');
                if (betOptionDraw) betOptionDraw.classList.add('view-mode', 'bet-not-used');
            }
        } else {
            // Partida nao encerrada
            modal.querySelectorAll('.score-bet-option').forEach(opt => {
                opt.classList.add('view-mode');
            });
        }

    } else {
        // Modo edicao ou novo palpite
        inputs.forEach(input => {
            input.disabled = false;
            input.classList.remove('readonly');
        });

        // Se estiver editando, preenche com valores existentes
        if (isEditing && matchData.user_bet) {
            const bet = matchData.user_bet;
            document.getElementById('home-win-bahia').value = bet.home_win_bahia ?? '';
            document.getElementById('home-win-opponent').value = bet.home_win_opponent ?? '';
            document.getElementById('draw-bahia').value = bet.draw_bahia ?? '';
            document.getElementById('draw-opponent').value = bet.draw_opponent ?? '';
            // Valida os inputs apos preencher
            validateBetInputs();
        } else {
            // Novo palpite - limpa inputs
            inputs.forEach(input => {
                input.value = '';
            });
        }

        modal.querySelectorAll('.score-bet-option').forEach(opt => {
            opt.classList.remove('valid', 'invalid', 'view-mode');
        });

        // Mostra botao e regras
        if (confirmBtn) {
            confirmBtn.classList.remove('hidden');
            confirmBtn.disabled = !isEditing; // Se editando, pode ja estar habilitado
            confirmBtn.innerHTML = isEditing
                ? '<i class="fas fa-save"></i> Salvar Alteracoes'
                : '<i class="fas fa-check"></i> Confirmar Palpites';
            confirmBtn.onclick = () => submitBet(matchId);
        }
        if (rulesEl) rulesEl.classList.remove('hidden');
        if (disclaimerEl) {
            disclaimerEl.innerHTML = '<i class="fas fa-info-circle"></i> Voce pode alterar seu palpite ate 10 minutos antes da partida';
            disclaimerEl.classList.remove('result-win', 'result-loss');
        }
    }

    modal.classList.add('active');
}

async function submitBet(matchId) {
    const homeWinBahia = parseInt(document.getElementById('home-win-bahia')?.value);
    const homeWinOpponent = parseInt(document.getElementById('home-win-opponent')?.value);
    const drawBahia = parseInt(document.getElementById('draw-bahia')?.value);
    const drawOpponent = parseInt(document.getElementById('draw-opponent')?.value);

    // Validacao final antes de enviar
    if (isNaN(homeWinBahia) || isNaN(homeWinOpponent) || isNaN(drawBahia) || isNaN(drawOpponent)) {
        showToast('Preencha todos os placares', 'error');
        return;
    }

    if (homeWinBahia <= homeWinOpponent) {
        showToast('No palpite de Triunfo, Bahia precisa ter mais gols', 'error');
        return;
    }

    if (drawBahia !== drawOpponent) {
        showToast('No palpite de Empate, os placares devem ser iguais', 'error');
        return;
    }

    // Desabilita botao durante envio
    const confirmBtn = document.getElementById('confirm-bet-btn');
    if (confirmBtn) {
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enviando...';
    }

    try {
        const response = await fetch('/app/bahia/api/bet/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify({
                match_id: matchId,
                home_win_bahia: homeWinBahia,
                home_win_opponent: homeWinOpponent,
                draw_bahia: drawBahia,
                draw_opponent: drawOpponent
            })
        });

        const data = await response.json();

        if (response.ok) {
            showToast('Palpite registrado com sucesso!', 'success');
            document.getElementById('bet-modal')?.classList.remove('active');
            // Recarrega a pagina para atualizar os dados
            setTimeout(() => location.reload(), 1000);
        } else {
            showToast(data.error || 'Erro ao registrar palpite', 'error');
            // Reabilita botao
            if (confirmBtn) {
                confirmBtn.disabled = false;
                confirmBtn.innerHTML = '<i class="fas fa-check"></i> Confirmar Palpites';
            }
        }
    } catch (error) {
        console.error('Erro:', error);
        showToast('Erro ao registrar palpite', 'error');
        // Reabilita botao
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = '<i class="fas fa-check"></i> Confirmar Palpites';
        }
    }
}

function getCsrfToken() {
    // Tenta pegar do cookie primeiro
    const cookie = document.cookie.split(';').find(c => c.trim().startsWith('csrftoken='));
    if (cookie) {
        return cookie.split('=')[1];
    }
    // Fallback: busca do meta tag ou input hidden
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) {
        return metaTag.getAttribute('content');
    }
    const hiddenInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
    if (hiddenInput) {
        return hiddenInput.value;
    }
    return '';
}

// ==================== STANDINGS ====================
let currentLeague = 71;
let currentSeason = new Date().getFullYear();  // Ano atual como padrão
let currentRound = 1;
let currentRoundIndex = 0;
let totalRounds = 1;
let roundsCache = {};
let roundsData = [];  // Armazena os dados completos das rodadas
let competitionType = 'league';  // Tipo de competição atual

// Inicializa o select de temporada
function initSeasonSelect() {
    const seasonSelect = document.getElementById('season-select');
    if (!seasonSelect) return;

    const currentYear = new Date().getFullYear();

    // Opções: próximo ano, ano atual, ano anterior (maior para menor no select)
    const seasons = [
        { value: currentYear + 1, label: currentYear + 1 },
        { value: currentYear, label: currentYear },
        { value: currentYear - 1, label: currentYear - 1 }
    ];

    let html = '';
    seasons.forEach(s => {
        const selected = s.value === currentSeason ? 'selected' : '';
        html += `<option value="${s.value}" ${selected}>${s.label}</option>`;
    });

    seasonSelect.innerHTML = html;

    // Evento de mudança
    seasonSelect.addEventListener('change', (e) => {
        currentSeason = parseInt(e.target.value);
        roundsCache = {};  // Limpa cache ao trocar temporada
        roundsData = [];
        loadStandings(currentLeague);
    });
}

async function loadStandings(leagueId) {
    const container = document.getElementById('standings-container');
    if (!container) return;

    currentLeague = leagueId;

    // Reset: remove modo cup e mostra container
    container.classList.remove('hidden');
    document.querySelector('.standings-layout')?.classList.remove('cup-mode');

    container.innerHTML = '<div class="loading-spinner"><i class="fas fa-futbol fa-spin"></i></div>';

    try {
        // Inclui a temporada na requisição
        const response = await fetch(`/app/bahia/api/standings/${leagueId}/?season=${currentSeason}`);
        const data = await response.json();

        // Verifica se a temporada ainda nao comecou
        if (data.season_not_started) {
            const startDate = data.season_starts_at ? new Date(data.season_starts_at) : null;
            const formattedDate = startDate ? startDate.toLocaleDateString('pt-BR', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            }) : '';

            container.innerHTML = `
                <div class="empty-state season-not-started">
                    <i class="fas fa-calendar-alt"></i>
                    <h3>Temporada ${currentSeason} ainda nao iniciada</h3>
                    ${startDate ? `<p>Primeira rodada em <strong>${formattedDate}</strong></p>` : ''}
                    <p class="hint">A classificacao estara disponivel apos o inicio da competicao.</p>
                </div>
            `;
            // Ainda carrega as rodadas/jogos agendados
            await loadRounds(leagueId);
            return;
        }

        if (data.standings && data.standings.length > 0) {
            renderStandings(data);
            // Carregar rodadas e jogos
            await loadRounds(leagueId);
        } else {
            // Verifica se é competição de mata-mata (cup)
            if (data.competition_type === 'cup') {
                // Esconde container de standings e centraliza a listagem de jogos
                container.classList.add('hidden');
                document.querySelector('.standings-layout')?.classList.add('cup-mode');
                // Carregar rodadas/jogos
                await loadRounds(leagueId);
            } else {
                container.innerHTML = '<div class="empty-state"><i class="fas fa-table"></i><p>Classificação não disponível para ' + currentSeason + '</p></div>';
            }
        }
    } catch (error) {
        console.error('Erro ao carregar classificação:', error);
        container.innerHTML = '<div class="empty-state"><i class="fas fa-exclamation-triangle"></i><p>Erro ao carregar classificação</p></div>';
    }
}

function renderStandings(data) {
    const container = document.getElementById('standings-container');
    if (!container) return;

    let html = `
        <div class="standings-table">
            <div class="standings-header">
                <span class="col-pos">#</span>
                <span class="col-team">Time</span>
                <span class="col-pts">Pts</span>
                <span class="col-stat">SG</span>
                <span class="col-stat">V</span>
                <span class="col-stat">E</span>
                <span class="col-stat">D</span>
                <span class="col-stat">P</span>
                <span class="col-form">Ultimas 5</span>
            </div>
    `;

    data.standings.forEach((team, index) => {
        const isBahia = team.team_name?.toLowerCase().includes('bahia');
        const zone = getZoneClass(index + 1);
        const formIndicators = renderFormIndicators(team.form || '');

        html += `
            <div class="standings-row ${isBahia ? 'bahia-row' : ''} ${zone}">
                <span class="standings-pos col-pos">${team.position}</span>
                <div class="standings-team col-team">
                    <img src="${team.team_logo || getTeamBadge(team.team_name)}" alt="${team.team_name}" class="team-logo-small">
                    <span class="standings-team-name">${team.team_name}</span>
                </div>
                <span class="standings-points col-pts">${team.points}</span>
                <span class="standings-gd col-stat ${team.goal_difference > 0 ? 'positive' : team.goal_difference < 0 ? 'negative' : ''}">${team.goal_difference > 0 ? '+' : ''}${team.goal_difference}</span>
                <span class="standings-stat col-stat">${team.wins}</span>
                <span class="standings-stat col-stat">${team.draws}</span>
                <span class="standings-stat col-stat">${team.losses}</span>
                <span class="standings-stat col-stat">${team.played}</span>
                <div class="standings-form col-form">${formIndicators}</div>
            </div>
        `;
    });

    html += '</div>';

    // Legenda
    html += `
        <div class="standings-legend">
            <div class="legend-item"><div class="legend-color zone-libertadores"></div> Libertadores</div>
            <div class="legend-item"><div class="legend-color zone-prelibertadores"></div> Pré-Libertadores</div>
            <div class="legend-item"><div class="legend-color zone-sulamericana"></div> Sul-Americana</div>
            <div class="legend-item"><div class="legend-color zone-rebaixamento"></div> Rebaixamento</div>
        </div>
    `;

    container.innerHTML = html;
}

function renderFormIndicators(form) {
    if (!form) return '';
    // Converte letras do ingles para portugues
    // W (Win) -> V (Vitoria), D (Draw) -> E (Empate), L (Loss) -> D (Derrota)
    const translations = { 'W': 'V', 'D': 'E', 'L': 'D' };
    return form.split('').map(char => {
        const ptChar = translations[char] || char;
        return `<span class="form-indicator form-${ptChar}">${ptChar}</span>`;
    }).join('');
}

function getZoneClass(position) {
    if (position <= 4) return 'zone-libertadores';
    if (position <= 6) return 'zone-prelibertadores';
    if (position <= 12) return 'zone-sulamericana';
    if (position >= 17) return 'zone-rebaixamento';
    return '';
}

// ==================== ROUND FIXTURES ====================
async function loadRounds(leagueId) {
    const fixturesList = document.getElementById('round-fixtures-list');
    const roundSelector = document.getElementById('round-selector');

    try {
        // Inclui a temporada na requisição
        const response = await fetch(`/app/bahia/api/rounds/${leagueId}/?season=${currentSeason}`);
        const data = await response.json();

        // Verifica se nao ha dados para a temporada
        if (data.no_data_for_season) {
            const compName = data.competition_name || 'Esta competicao';
            if (fixturesList) {
                fixturesList.innerHTML = `
                    <div class="empty-state competition-no-data">
                        <i class="fas fa-calendar-times"></i>
                        <h3>${compName}</h3>
                        <p>Nenhuma partida disponivel para ${currentSeason}</p>
                        <p class="hint">Os dados desta competicao ainda nao foram publicados para esta temporada.</p>
                    </div>
                `;
            }
            if (roundSelector) {
                roundSelector.innerHTML = '';
            }
            return;
        }

        if (data.rounds && data.rounds.length > 0) {
            // Nova estrutura: data.rounds é um array de objetos com {raw, label, number, phase}
            roundsData = data.rounds;
            competitionType = data.competition_type || 'league';
            totalRounds = roundsData.length;

            // Usa o índice da rodada atual (próxima a acontecer) retornado pela API
            // Se não fornecido, usa a primeira rodada como fallback
            let startIndex = data.current_round_index ?? 0;

            // Garante que o índice está dentro dos limites
            if (startIndex < 0 || startIndex >= roundsData.length) {
                startIndex = 0;
            }

            currentRoundIndex = startIndex;
            currentRound = roundsData[startIndex].number || (startIndex + 1);

            // Atualiza o seletor de rodadas
            updateRoundSelector();

            // Carrega os jogos da rodada atual
            await loadFixturesByIndex(currentRoundIndex);
            updateNavButtons();
        } else {
            // Nenhuma rodada encontrada
            if (fixturesList) {
                fixturesList.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-futbol"></i>
                        <p>Nenhuma partida encontrada para ${currentSeason}</p>
                    </div>
                `;
            }
            if (roundSelector) {
                roundSelector.innerHTML = '';
            }
        }
    } catch (error) {
        console.error('Erro ao carregar rodadas:', error);
        if (fixturesList) {
            fixturesList.innerHTML = '<div class="empty-state"><i class="fas fa-exclamation-triangle"></i><p>Erro ao carregar partidas</p></div>';
        }
    }
}

function updateRoundSelector() {
    const roundSelector = document.getElementById('round-selector');
    if (!roundSelector) return;

    // Agrupa por fase
    const phases = {};
    roundsData.forEach((round, index) => {
        const phase = round.phase || 'regular';
        if (!phases[phase]) phases[phase] = [];
        phases[phase].push({ ...round, index });
    });

    let html = '<select id="round-select" class="round-select">';

    // Adiciona opções agrupadas por fase
    Object.entries(phases).forEach(([phase, rounds]) => {
        const phaseLabels = {
            'regular': 'Temporada Regular',
            '1st_phase': '1ª Fase',
            '2nd_phase': '2ª Fase',
            'knockout': 'Mata-Mata',
            'group': 'Fase de Grupos'
        };

        if (Object.keys(phases).length > 1) {
            html += `<optgroup label="${phaseLabels[phase] || phase}">`;
        }

        rounds.forEach(round => {
            html += `<option value="${round.index}" ${round.index === currentRoundIndex ? 'selected' : ''}>${round.label}</option>`;
        });

        if (Object.keys(phases).length > 1) {
            html += '</optgroup>';
        }
    });

    html += '</select>';
    roundSelector.innerHTML = html;

    // Adiciona evento de change
    const select = document.getElementById('round-select');
    if (select) {
        select.addEventListener('change', async (e) => {
            currentRoundIndex = parseInt(e.target.value);
            currentRound = roundsData[currentRoundIndex].number || (currentRoundIndex + 1);
            await loadFixturesByIndex(currentRoundIndex);
            updateNavButtons();
        });
    }
}

async function loadFixturesByIndex(roundIndex) {
    if (!roundsData[roundIndex]) {
        console.warn('[Fixtures] roundIndex invalido:', roundIndex, 'roundsData:', roundsData);
        return;
    }

    const roundInfo = roundsData[roundIndex];
    const roundRaw = roundInfo.raw;
    const roundLabel = roundInfo.label;

    console.log('[Fixtures] Carregando rodada:', roundIndex, roundRaw, roundLabel, 'temporada:', currentSeason);

    const fixturesList = document.getElementById('round-fixtures-list');

    if (!fixturesList) return;

    fixturesList.innerHTML = '<div class="loading-spinner"><i class="fas fa-futbol fa-spin"></i></div>';

    // Verificar cache (inclui temporada na chave)
    const cacheKey = `${currentLeague}_${currentSeason}_${roundRaw}`;
    if (roundsCache[cacheKey]) {
        renderFixtures(roundsCache[cacheKey], roundInfo.phase);
        return;
    }

    try {
        // Usa round_raw e season para buscar os jogos
        const url = `/app/bahia/api/fixtures/${currentLeague}/?round_raw=${encodeURIComponent(roundRaw)}&season=${currentSeason}`;
        console.log('[Fixtures] Fetch URL:', url);
        const response = await fetch(url);
        const data = await response.json();
        console.log('[Fixtures] Resposta:', data.matches?.length, 'jogos');

        if (data.matches) {
            roundsCache[cacheKey] = data.matches;
            renderFixtures(data.matches, roundInfo.phase);
        } else {
            fixturesList.innerHTML = '<div class="empty-state"><p>Nenhum jogo encontrado</p></div>';
        }
    } catch (error) {
        console.error('Erro ao carregar jogos:', error);
        fixturesList.innerHTML = '<div class="empty-state"><p>Erro ao carregar jogos</p></div>';
    }
}

async function loadFixtures(round) {
    // Função legada - tenta encontrar o índice correspondente
    const roundIndex = roundsData.findIndex(r => r.number === round);
    if (roundIndex >= 0) {
        currentRoundIndex = roundIndex;
        await loadFixturesByIndex(roundIndex);
        return;
    }

    // Fallback para comportamento antigo (sem roundsData)
    const fixturesList = document.getElementById('round-fixtures-list');
    const currentRoundEl = document.getElementById('current-round');

    if (!fixturesList) return;

    if (currentRoundEl) currentRoundEl.textContent = `Rodada ${round}`;
    fixturesList.innerHTML = '<div class="loading-spinner"><i class="fas fa-futbol fa-spin"></i></div>';

    // Verificar cache
    const cacheKey = `${currentLeague}_${round}`;
    if (roundsCache[cacheKey]) {
        renderFixtures(roundsCache[cacheKey]);
        return;
    }

    try {
        const response = await fetch(`/app/bahia/api/fixtures/${currentLeague}/?round=${round}`);
        const data = await response.json();

        if (data.matches) {
            roundsCache[cacheKey] = data.matches;
            renderFixtures(data.matches);
        } else {
            fixturesList.innerHTML = '<div class="empty-state"><p>Nenhum jogo encontrado</p></div>';
        }
    } catch (error) {
        console.error('Erro ao carregar jogos:', error);
        fixturesList.innerHTML = '<div class="empty-state"><p>Erro ao carregar jogos</p></div>';
    }
}

function renderFixtures(matches, phase = 'regular') {
    const fixturesList = document.getElementById('round-fixtures-list');
    if (!fixturesList) return;

    if (!matches || matches.length === 0) {
        fixturesList.innerHTML = '<div class="empty-state"><p>Nenhum jogo nesta rodada</p></div>';
        return;
    }

    // Para fases de mata-mata, agrupa jogos de ida e volta
    if (phase === 'knockout') {
        renderKnockoutFixtures(matches, fixturesList);
        return;
    }

    let html = '';
    matches.forEach(match => {
        html += renderFixtureCard(match);
    });

    fixturesList.innerHTML = html;
}

function renderFixtureCard(match) {
    const isBahia = match.is_bahia;
    const statusClass = match.status === 'finished' ? 'finished' : match.status === 'live' ? 'live' : 'upcoming';
    const date = match.date ? new Date(match.date) : null;
    const dateStr = date ? date.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit' }) : '';
    const timeStr = date ? date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '';

    // Informação do local
    let venueInfo = '';
    if (match.venue) {
        venueInfo = match.venue;
        if (match.venue_city) {
            venueInfo += ` - ${match.venue_city}`;
        }
    }

    // Layout: Nome | Escudo | Placar | Escudo | Nome
    return `
        <div class="fixture-card ${isBahia ? 'bahia-fixture' : ''} ${statusClass}">
            <div class="fixture-teams">
                <div class="fixture-team home">
                    <span class="fixture-team-name">${match.home_team}</span>
                </div>
                <img src="${match.home_logo}" alt="${match.home_team}" class="fixture-team-logo">
                <div class="fixture-score">
                    ${match.status === 'finished' || match.status === 'live'
                        ? `<span class="score">${match.home_goals ?? '-'}</span><span class="score-separator">x</span><span class="score">${match.away_goals ?? '-'}</span>`
                        : `<span class="fixture-time">${timeStr}</span>`
                    }
                </div>
                <img src="${match.away_logo}" alt="${match.away_team}" class="fixture-team-logo">
                <div class="fixture-team away">
                    <span class="fixture-team-name">${match.away_team}</span>
                </div>
            </div>
            ${match.status === 'live' ? '<div class="fixture-live-badge"><i class="fas fa-circle"></i> AO VIVO</div>' : ''}
            <div class="fixture-info">
                ${venueInfo ? `<div class="fixture-venue"><i class="fas fa-map-marker-alt"></i> ${venueInfo}</div>` : ''}
                <div class="fixture-datetime">
                    <span><i class="fas fa-calendar"></i> ${dateStr}</span>
                    ${match.status !== 'finished' ? `<span><i class="fas fa-clock"></i> ${timeStr}</span>` : ''}
                </div>
            </div>
        </div>
    `;
}

function renderKnockoutFixtures(matches, container) {
    // Agrupa jogos por confronto (mesmo par de times)
    const confrontos = {};

    matches.forEach(match => {
        // Cria chave normalizada (ordena nomes dos times)
        const teams = [match.home_team, match.away_team].sort();
        const key = teams.join(' vs ');

        if (!confrontos[key]) {
            confrontos[key] = {
                teams: teams,
                matches: []
            };
        }
        confrontos[key].matches.push(match);
    });

    let html = '<div class="knockout-fixtures">';

    Object.values(confrontos).forEach(confronto => {
        // Ordena por data (jogo de ida primeiro)
        confronto.matches.sort((a, b) => new Date(a.date) - new Date(b.date));

        const isBahia = confronto.matches.some(m => m.is_bahia);

        html += `<div class="knockout-confronto ${isBahia ? 'bahia-confronto' : ''}">`;
        html += `<div class="confronto-header">
            <span class="confronto-teams">${confronto.teams[0]} x ${confronto.teams[1]}</span>
        </div>`;

        html += '<div class="confronto-games">';
        confronto.matches.forEach((match, idx) => {
            const gameLabel = idx === 0 ? 'Jogo 1 (Ida)' : 'Jogo 2 (Volta)';
            html += `<div class="confronto-game-label">${gameLabel}</div>`;
            html += renderFixtureCard(match);
        });
        html += '</div>';

        // Calcula agregado se ambos jogos terminaram
        if (confronto.matches.length === 2 &&
            confronto.matches.every(m => m.status === 'finished')) {
            const team1 = confronto.teams[0];
            const team2 = confronto.teams[1];
            let team1Goals = 0, team2Goals = 0;

            confronto.matches.forEach(m => {
                if (m.home_team === team1) {
                    team1Goals += m.home_goals || 0;
                    team2Goals += m.away_goals || 0;
                } else {
                    team2Goals += m.home_goals || 0;
                    team1Goals += m.away_goals || 0;
                }
            });

            html += `<div class="confronto-aggregate">
                <span class="aggregate-label">Agregado:</span>
                <span class="aggregate-score">${team1} ${team1Goals} x ${team2Goals} ${team2}</span>
            </div>`;
        }

        html += '</div>';
    });

    html += '</div>';
    container.innerHTML = html;
}

function updateNavButtons() {
    const prevBtn = document.getElementById('prev-round');
    const nextBtn = document.getElementById('next-round');

    if (prevBtn) {
        prevBtn.disabled = currentRoundIndex <= 0;
        prevBtn.classList.toggle('disabled', currentRoundIndex <= 0);
    }
    if (nextBtn) {
        nextBtn.disabled = currentRoundIndex >= totalRounds - 1;
        nextBtn.classList.toggle('disabled', currentRoundIndex >= totalRounds - 1);
    }

    // Atualiza o select se existir
    const roundSelect = document.getElementById('round-select');
    if (roundSelect) {
        roundSelect.value = currentRoundIndex;
    }
}

function initRoundNavigation() {
    const prevBtn = document.getElementById('prev-round');
    const nextBtn = document.getElementById('next-round');

    if (prevBtn) {
        prevBtn.addEventListener('click', async () => {
            if (currentRoundIndex > 0) {
                currentRoundIndex--;
                currentRound = roundsData[currentRoundIndex]?.number || currentRoundIndex + 1;
                await loadFixturesByIndex(currentRoundIndex);
                updateNavButtons();
            }
        });
    }

    if (nextBtn) {
        nextBtn.addEventListener('click', async () => {
            if (currentRoundIndex < totalRounds - 1) {
                currentRoundIndex++;
                currentRound = roundsData[currentRoundIndex]?.number || currentRoundIndex + 1;
                await loadFixturesByIndex(currentRoundIndex);
                updateNavButtons();
            }
        });
    }
}

// ==================== COMPETITIONS SELECT ====================
async function loadCompetitionsSelect() {
    const standingsSelect = document.getElementById('standings-select');
    if (!standingsSelect) return;

    try {
        const response = await fetch('/app/bahia/api/competitions/', {
            credentials: 'same-origin'
        });
        const data = await response.json();

        if (data.competitions && data.competitions.length > 0) {
            let html = '';

            // Agrupa por tipo
            const types = {
                'league': { label: 'Campeonatos', comps: [] },
                'cup': { label: 'Copas', comps: [] },
                'state': { label: 'Estaduais', comps: [] }
            };

            data.competitions.forEach(comp => {
                const type = comp.type || 'league';
                if (types[type]) {
                    types[type].comps.push(comp);
                } else {
                    types['league'].comps.push(comp);
                }
            });

            // Renderiza options agrupados
            Object.entries(types).forEach(([type, group]) => {
                if (group.comps.length === 0) return;

                if (Object.values(types).filter(g => g.comps.length > 0).length > 1) {
                    html += `<optgroup label="${group.label}">`;
                }

                group.comps.forEach(comp => {
                    const selected = comp.id === currentLeague ? 'selected' : '';
                    html += `<option value="${comp.id}" ${selected}>${comp.short_name || comp.name}</option>`;
                });

                if (Object.values(types).filter(g => g.comps.length > 0).length > 1) {
                    html += '</optgroup>';
                }
            });

            standingsSelect.innerHTML = html;
        }
    } catch (error) {
        console.error('Erro ao carregar competições:', error);
    }
}

// ==================== INITIALIZATION ====================
document.addEventListener('DOMContentLoaded', async () => {
    hideSplash();
    initTabs();
    initBetModal();
    initRoundNavigation();
    initSeasonSelect();  // Inicializa select de temporada

    // Carrega proxima partida do Bahia (card principal) - aguarda para ter o competition_id
    await loadNextBahiaMatch();

    // Carrega historico de palpites
    loadBetsHistory();

    // Carrega ranking
    loadRanking();

    // Carrega competições e inicializa standings select
    const standingsSelect = document.getElementById('standings-select');
    if (standingsSelect) {
        // Carrega opções dinamicamente
        await loadCompetitionsSelect();

        standingsSelect.addEventListener('change', (e) => {
            roundsCache = {}; // Limpa cache ao trocar liga
            roundsData = []; // Limpa dados de rodadas
            loadStandings(parseInt(e.target.value));
        });

        // Define a competicao inicial baseada na partida em destaque
        let initialLeagueId = parseInt(standingsSelect.value);
        if (heroMatchData && heroMatchData.competition_id) {
            const competitionId = heroMatchData.competition_id.toString();
            const optionExists = Array.from(standingsSelect.options).some(opt => opt.value === competitionId);
            if (optionExists) {
                standingsSelect.value = competitionId;
                initialLeagueId = heroMatchData.competition_id;
            }
        }

        // Carrega standings inicial
        loadStandings(initialLeagueId);
    }

    // Botões de apostar
    document.querySelectorAll('[data-match-id]').forEach(btn => {
        btn.addEventListener('click', () => {
            const matchId = btn.dataset.matchId;
            const matchData = JSON.parse(btn.dataset.match || '{}');
            openBetModal(matchId, matchData);
        });
    });

    // Inicializa modal admin se existir
    initAdminModal();

    // Inicializa gerenciamento de partidas (DEV ONLY)
    initMatchManagement();

    // Sistema inteligente de polling para partidas ao vivo
    initLiveMatchPolling();

    // Inicializa modal de menu do usuario
    initUserMenuModal();

    console.log('JampaBet Django initialized!');
});

// ==================== USER MENU MODAL ====================
function initUserMenuModal() {
    const userMenuModal = document.getElementById('user-menu-modal');
    const openUserMenuBtn = document.getElementById('open-user-menu');
    const closeUserMenuBtn = document.getElementById('close-user-menu');

    if (!userMenuModal) return;

    // Abrir modal
    if (openUserMenuBtn) {
        openUserMenuBtn.addEventListener('click', (e) => {
            e.preventDefault();
            userMenuModal.classList.add('active');
        });
    }

    // Fechar modal
    if (closeUserMenuBtn) {
        closeUserMenuBtn.addEventListener('click', () => {
            userMenuModal.classList.remove('active');
        });
    }

    // Fechar ao clicar fora
    userMenuModal.addEventListener('click', (e) => {
        if (e.target === userMenuModal) {
            userMenuModal.classList.remove('active');
        }
    });
}

// ==================== ADMIN MODAL ====================
function initAdminModal() {
    const adminModal = document.getElementById('admin-modal');
    const openAdminBtn = document.getElementById('open-admin-modal');
    const closeAdminBtn = document.getElementById('close-admin-modal');

    if (!adminModal || !openAdminBtn) return;

    // Abrir modal
    openAdminBtn.addEventListener('click', async () => {
        adminModal.classList.add('active');
        // Verifica autenticacao admin primeiro
        await checkAdminAuth();
        loadAdminStats();
        loadAdminCompetitions();
        // Inicializa gerenciamento de usuarios
        initUserManagement();
    });

    // Fechar modal
    if (closeAdminBtn) {
        closeAdminBtn.addEventListener('click', () => {
            adminModal.classList.remove('active');
        });
    }

    // Fechar ao clicar fora
    adminModal.addEventListener('click', (e) => {
        if (e.target === adminModal) {
            adminModal.classList.remove('active');
        }
    });

    // Botões de sincronização
    document.getElementById('sync-teams-btn')?.addEventListener('click', () => syncData('teams'));
    document.getElementById('sync-competitions-btn')?.addEventListener('click', () => syncData('competitions'));
    document.getElementById('sync-fixtures-btn')?.addEventListener('click', () => syncData('fixtures'));
}

async function checkAdminAuth() {
    try {
        const response = await fetch('/app/bahia/api/admin/check/', {
            credentials: 'same-origin'
        });

        // Sessao expirou
        if (response.status === 401) {
            addLog('error', 'Sessao expirada. Redirecionando para login...');
            setTimeout(() => { window.location.href = '/app/bahia/login/'; }, 2000);
            return false;
        }

        const data = await response.json();
        console.log('[Admin] Auth check:', data);

        if (!data.is_authenticated) {
            addLog('error', 'Sessao expirada. Faca login novamente.');
            return false;
        }
        if (!data.is_admin) {
            addLog('error', 'Usuario nao tem permissao de admin.');
            return false;
        }
        addLog('success', `Autenticado como ${data.user_email}`);
        return true;
    } catch (error) {
        console.error('Erro ao verificar auth:', error);
        addLog('error', 'Erro ao verificar autenticacao');
        return false;
    }
}

async function loadAdminStats() {
    try {
        const response = await fetch('/app/bahia/api/admin/stats/', {
            credentials: 'same-origin'
        });
        if (!response.ok) {
            if (response.status === 401) {
                addLog('error', 'Sessao expirada.');
                return;
            }
            if (response.status === 403) {
                addLog('error', 'Sem permissao. Verifique se esta logado como admin.');
            }
            return;
        }
        const data = await response.json();

        if (data.stats) {
            document.getElementById('admin-stat-teams').textContent = data.stats.teams;
            document.getElementById('admin-stat-competitions').textContent = data.stats.competitions;
            document.getElementById('admin-stat-fixtures').textContent = data.stats.fixtures;
            document.getElementById('admin-stat-users').textContent = data.stats.users;
        }
    } catch (error) {
        console.error('Erro ao carregar stats:', error);
    }
}

async function loadAdminCompetitions() {
    const container = document.getElementById('admin-competitions-list');
    if (!container) return;

    try {
        const response = await fetch('/app/bahia/api/admin/competitions/', {
            credentials: 'same-origin'
        });

        if (response.status === 401 || response.status === 403) {
            container.innerHTML = '<p class="empty-state">Sem permissao para acessar.</p>';
            return;
        }

        const data = await response.json();

        if (!data.competitions || data.competitions.length === 0) {
            container.innerHTML = '<p class="empty-state">Nenhuma competicao cadastrada. Sincronize primeiro.</p>';
            return;
        }

        let html = '';
        data.competitions.forEach(comp => {
            html += `
                <div class="admin-competition-item">
                    <div class="admin-competition-info">
                        ${comp.logo_url ? `<img src="${comp.logo_url}" class="admin-competition-logo" alt="${comp.name}">` : '<i class="fas fa-trophy"></i>'}
                        <div>
                            <div class="admin-competition-name">${comp.short_name || comp.name}</div>
                            <div class="admin-competition-stats">${comp.fixture_count} partidas</div>
                        </div>
                    </div>
                    <div class="admin-competition-toggle ${comp.is_tracked ? 'active' : ''}"
                         data-competition-id="${comp.id}"
                         onclick="toggleCompetition(${comp.id}, this)">
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
    } catch (error) {
        console.error('Erro ao carregar competições:', error);
        container.innerHTML = '<p class="empty-state">Erro ao carregar competições</p>';
    }
}

async function toggleCompetition(compId, element) {
    try {
        const response = await fetch(`/app/bahia/api/admin/competitions/${compId}/toggle/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin'
        });

        if (response.status === 401) {
            addLog('error', 'Sessao expirada.');
            return;
        }
        if (response.status === 403) {
            addLog('error', 'Sem permissao.');
            return;
        }

        const data = await response.json();

        if (data.success) {
            element.classList.toggle('active', data.is_tracked);
            addLog('success', data.message);
        } else {
            addLog('error', data.error || 'Erro ao alterar competição');
        }
    } catch (error) {
        console.error('Erro:', error);
        addLog('error', 'Erro de conexão');
    }
}

async function syncData(type) {
    const btn = document.getElementById(`sync-${type}-btn`);
    if (!btn) return;

    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.classList.add('loading');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sincronizando...';

    addLog('info', `Iniciando sincronização de ${type}...`);

    try {
        const csrfToken = getCsrfToken();
        console.log('[Admin] Sync request:', type, 'CSRF:', csrfToken ? 'presente' : 'ausente');

        const response = await fetch(`/app/bahia/api/admin/sync/${type}/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            credentials: 'same-origin'  // Garante que cookies de sessao sejam enviados
        });

        console.log('[Admin] Sync response status:', response.status);

        // Trata erros de autenticacao
        if (response.status === 401) {
            addLog('error', 'Sessao expirada. Redirecionando para login...');
            setTimeout(() => { window.location.href = '/app/bahia/login/'; }, 2000);
            return;
        }

        // Trata erro 403 especificamente
        if (response.status === 403) {
            const text = await response.text();
            console.error('[Admin] 403 Response:', text.substring(0, 200));
            addLog('error', 'Acesso negado. Verifique se esta logado como admin.');
            return;
        }

        const data = await response.json();

        if (data.success) {
            addLog('success', data.message);
            loadAdminStats();
            if (type === 'competitions') {
                loadAdminCompetitions();
            }
        } else {
            addLog('error', data.error || 'Erro na sincronização');
        }
    } catch (error) {
        console.error('Erro:', error);
        addLog('error', `Erro: ${error.message}`);
    } finally {
        btn.disabled = false;
        btn.classList.remove('loading');
        btn.innerHTML = originalHtml;
    }
}

function addLog(type, message) {
    const logContainer = document.getElementById('admin-log');
    if (!logContainer) return;

    const icons = {
        info: 'fa-info-circle',
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        warning: 'fa-exclamation-triangle'
    };

    const entry = document.createElement('div');
    entry.className = `log-entry ${type}`;
    entry.innerHTML = `<i class="fas ${icons[type]}"></i><span>${new Date().toLocaleTimeString('pt-BR')} - ${message}</span>`;

    logContainer.insertBefore(entry, logContainer.firstChild);

    // Limita a 20 entradas
    while (logContainer.children.length > 20) {
        logContainer.removeChild(logContainer.lastChild);
    }
}

// ==================== GERENCIAMENTO DE PARTIDAS (DEV ONLY) ====================

// Cache para times e competicoes carregados
let _teamsCache = [];
let _competitionsCache = [];
let _autocompleteTimeout = null;

function initMatchManagement() {
    const matchEditModal = document.getElementById('match-edit-modal');
    const btnNewMatch = document.getElementById('btn-new-match');
    const closeMatchEditBtn = document.getElementById('close-match-edit-modal');
    const btnCancelMatch = document.getElementById('btn-cancel-match');
    const matchEditForm = document.getElementById('match-edit-form');
    const matchStatus = document.getElementById('match-status');

    if (!matchEditModal || !btnNewMatch) return;

    // Abrir modal para nova partida
    btnNewMatch.addEventListener('click', () => {
        openMatchEditModal();
    });

    // Fechar modal
    closeMatchEditBtn?.addEventListener('click', () => {
        matchEditModal.classList.remove('active');
    });

    btnCancelMatch?.addEventListener('click', () => {
        matchEditModal.classList.remove('active');
    });

    matchEditModal.addEventListener('click', (e) => {
        if (e.target === matchEditModal) {
            matchEditModal.classList.remove('active');
        }
    });

    // Mostrar/ocultar campos de resultado baseado no status
    matchStatus?.addEventListener('change', () => {
        const resultGroup = document.getElementById('match-result-group');
        if (resultGroup) {
            const showResult = ['live', 'finished'].includes(matchStatus.value);
            resultGroup.style.display = showResult ? 'block' : 'none';
        }
    });

    // Submit do formulario
    matchEditForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        await saveMatch();
    });

    // Inicializa autocomplete para times
    initTeamAutocomplete('match-home-team', 'home');
    initTeamAutocomplete('match-away-team', 'away');

    // Inicializa autocomplete para competicoes
    initCompetitionAutocomplete();

    // Inicializa eventos de mando do Bahia
    initLocationRadio();

    // Inicializa botoes de limpar selecao
    initClearButtons();

    // Carrega lista de partidas quando o modal admin abre
    const adminModal = document.getElementById('admin-modal');
    const openAdminBtn = document.getElementById('open-admin-modal');

    if (openAdminBtn && adminModal) {
        openAdminBtn.addEventListener('click', () => {
            setTimeout(() => loadAdminMatches(), 500);
        });
    }

    // Pre-carrega times e competicoes
    preloadTeamsAndCompetitions();
}

// Pre-carrega dados para autocomplete
async function preloadTeamsAndCompetitions() {
    try {
        const [teamsRes, compsRes] = await Promise.all([
            fetch('/app/bahia/api/admin/search/teams/', { credentials: 'same-origin' }),
            fetch('/app/bahia/api/admin/search/competitions/', { credentials: 'same-origin' })
        ]);

        if (teamsRes.ok) {
            const data = await teamsRes.json();
            _teamsCache = data.teams || [];
        }

        if (compsRes.ok) {
            const data = await compsRes.json();
            _competitionsCache = data.competitions || [];
        }
    } catch (error) {
        console.log('Erro ao pre-carregar dados:', error);
    }
}

// Inicializa autocomplete para times
function initTeamAutocomplete(inputId, type) {
    const input = document.getElementById(inputId);
    const resultsContainer = document.getElementById(`${type}-team-results`);

    if (!input || !resultsContainer) return;

    input.addEventListener('input', (e) => {
        clearTimeout(_autocompleteTimeout);
        const query = e.target.value.trim();

        if (query.length < 2) {
            resultsContainer.innerHTML = '';
            resultsContainer.style.display = 'none';
            return;
        }

        _autocompleteTimeout = setTimeout(() => {
            searchTeams(query, type, resultsContainer);
        }, 300);
    });

    input.addEventListener('focus', () => {
        if (input.value.length >= 2) {
            searchTeams(input.value, type, resultsContainer);
        }
    });

    // Fecha ao clicar fora
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !resultsContainer.contains(e.target)) {
            resultsContainer.style.display = 'none';
        }
    });
}

// Busca times na API
async function searchTeams(query, type, resultsContainer) {
    try {
        // Primeiro tenta usar cache
        let teams = _teamsCache.filter(t =>
            t.name.toLowerCase().includes(query.toLowerCase()) ||
            t.short_name.toLowerCase().includes(query.toLowerCase()) ||
            (t.display_name && t.display_name.toLowerCase().includes(query.toLowerCase()))
        );

        // Se nao encontrou no cache, busca na API
        if (teams.length === 0) {
            const response = await fetch(`/app/bahia/api/admin/search/teams/?q=${encodeURIComponent(query)}`, {
                credentials: 'same-origin'
            });

            if (response.ok) {
                const data = await response.json();
                teams = data.teams || [];
            }
        }

        renderTeamResults(teams, type, resultsContainer);
    } catch (error) {
        console.error('Erro ao buscar times:', error);
    }
}

// Renderiza resultados de times
function renderTeamResults(teams, type, container) {
    if (teams.length === 0) {
        container.innerHTML = '<div class="autocomplete-no-results">Nenhum time encontrado</div>';
        container.style.display = 'block';
        return;
    }

    let html = '';
    teams.forEach(team => {
        html += `
            <div class="autocomplete-item team-item" data-team='${JSON.stringify(team).replace(/'/g, "&#39;")}' data-type="${type}">
                <img src="${team.logo || '/static/jampabet/images/team-placeholder.png'}" alt="${team.name}" class="team-logo-mini">
                <div class="team-info-mini">
                    <span class="team-name">${team.display_name || team.name}</span>
                    <span class="team-city">${team.city || ''} ${team.state ? '- ' + team.state : ''}</span>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
    container.style.display = 'block';

    // Adiciona eventos de click
    container.querySelectorAll('.team-item').forEach(item => {
        item.addEventListener('click', () => {
            const team = JSON.parse(item.dataset.team);
            selectTeam(team, item.dataset.type);
            container.style.display = 'none';
        });
    });
}

// Seleciona um time
function selectTeam(team, type) {
    const input = document.getElementById(`match-${type}-team`);
    const preview = document.getElementById(`${type}-team-preview`);
    const previewLogo = document.getElementById(`${type}-team-preview-logo`);
    const previewName = document.getElementById(`${type}-team-preview-name`);

    // Preenche campos ocultos
    document.getElementById(`match-${type}-team-id`).value = team.external_id || '';
    document.getElementById(`match-${type}-team-logo`).value = team.logo || '';
    document.getElementById(`match-${type}-team-stadium`).value = team.stadium || '';

    // Preenche input visivel
    input.value = team.display_name || team.name;

    // Mostra preview
    if (preview && previewLogo && previewName) {
        previewLogo.src = team.logo || '/static/jampabet/images/team-placeholder.png';
        previewName.textContent = team.display_name || team.name;
        preview.style.display = 'flex';
        input.style.display = 'none';
    }

    // Atualiza estadio automaticamente baseado no mando
    updateVenueAutomatically();
}

// Inicializa autocomplete para competicoes
function initCompetitionAutocomplete() {
    const input = document.getElementById('match-competition');
    const resultsContainer = document.getElementById('competition-results');

    if (!input || !resultsContainer) return;

    input.addEventListener('input', (e) => {
        clearTimeout(_autocompleteTimeout);
        const query = e.target.value.trim();

        if (query.length < 2) {
            resultsContainer.innerHTML = '';
            resultsContainer.style.display = 'none';
            return;
        }

        _autocompleteTimeout = setTimeout(() => {
            searchCompetitions(query, resultsContainer);
        }, 300);
    });

    input.addEventListener('focus', () => {
        if (input.value.length >= 2) {
            searchCompetitions(input.value, resultsContainer);
        }
    });

    // Fecha ao clicar fora
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !resultsContainer.contains(e.target)) {
            resultsContainer.style.display = 'none';
        }
    });
}

// Busca competicoes na API
async function searchCompetitions(query, resultsContainer) {
    try {
        // Primeiro tenta usar cache
        let competitions = _competitionsCache.filter(c =>
            c.name.toLowerCase().includes(query.toLowerCase()) ||
            (c.short_name && c.short_name.toLowerCase().includes(query.toLowerCase()))
        );

        // Se nao encontrou no cache, busca na API
        if (competitions.length === 0) {
            const response = await fetch(`/app/bahia/api/admin/search/competitions/?q=${encodeURIComponent(query)}`, {
                credentials: 'same-origin'
            });

            if (response.ok) {
                const data = await response.json();
                competitions = data.competitions || [];
            }
        }

        renderCompetitionResults(competitions, resultsContainer);
    } catch (error) {
        console.error('Erro ao buscar competicoes:', error);
    }
}

// Renderiza resultados de competicoes
function renderCompetitionResults(competitions, container) {
    if (competitions.length === 0) {
        container.innerHTML = '<div class="autocomplete-no-results">Nenhuma competicao encontrada</div>';
        container.style.display = 'block';
        return;
    }

    let html = '';
    competitions.forEach(comp => {
        html += `
            <div class="autocomplete-item competition-item" data-competition='${JSON.stringify(comp).replace(/'/g, "&#39;")}'>
                <img src="${comp.logo || '/static/jampabet/images/trophy-placeholder.png'}" alt="${comp.name}" class="competition-logo-mini">
                <div class="competition-info-mini">
                    <span class="competition-name">${comp.name}</span>
                    <span class="competition-type">${getCompetitionTypeLabel(comp.type)}</span>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
    container.style.display = 'block';

    // Adiciona eventos de click
    container.querySelectorAll('.competition-item').forEach(item => {
        item.addEventListener('click', () => {
            const comp = JSON.parse(item.dataset.competition);
            selectCompetition(comp);
            container.style.display = 'none';
        });
    });
}

// Seleciona uma competicao
function selectCompetition(comp) {
    const input = document.getElementById('match-competition');
    const preview = document.getElementById('competition-preview');
    const previewLogo = document.getElementById('competition-preview-logo');
    const previewName = document.getElementById('competition-preview-name');

    // Preenche campos ocultos
    document.getElementById('match-competition-id').value = comp.external_id || '';
    document.getElementById('match-competition-logo').value = comp.logo || '';

    // Preenche input visivel
    input.value = comp.name;

    // Mostra preview
    if (preview && previewLogo && previewName) {
        previewLogo.src = comp.logo || '/static/jampabet/images/trophy-placeholder.png';
        previewName.textContent = comp.name;
        preview.style.display = 'flex';
        input.style.display = 'none';
    }
}

// Label do tipo de competicao
function getCompetitionTypeLabel(type) {
    const labels = {
        'league': 'Campeonato',
        'cup': 'Copa',
        'state': 'Estadual'
    };
    return labels[type] || type;
}

// Inicializa eventos do radio de mando
function initLocationRadio() {
    const radios = document.querySelectorAll('input[name="match-location"]');

    radios.forEach(radio => {
        radio.addEventListener('change', () => {
            updateVenueAutomatically();
            updateTeamLabels();
        });
    });
}

// Atualiza estadio automaticamente baseado no mando
function updateVenueAutomatically() {
    const location = document.querySelector('input[name="match-location"]:checked')?.value || 'home';
    const venueInput = document.getElementById('match-venue');
    const venueHint = document.getElementById('venue-auto-hint');

    let stadium = '';

    if (location === 'home') {
        // Bahia joga em casa - usa estadio do Bahia (Arena Fonte Nova)
        stadium = 'Arena Fonte Nova';
    } else {
        // Bahia joga fora - usa estadio do time da casa
        stadium = document.getElementById('match-home-team-stadium')?.value || '';
    }

    if (stadium && venueInput) {
        venueInput.value = stadium;
        if (venueHint) venueHint.style.display = 'inline';
    }
}

// Atualiza labels dos times baseado no mando
function updateTeamLabels() {
    // Funcionalidade opcional para destacar qual time e o Bahia
}

// Inicializa botoes de limpar selecao
function initClearButtons() {
    // Botoes de limpar time
    document.querySelectorAll('.btn-clear-team').forEach(btn => {
        btn.addEventListener('click', () => {
            const type = btn.dataset.target;
            clearTeamSelection(type);
        });
    });

    // Botao de limpar competicao
    const clearCompBtn = document.querySelector('.btn-clear-competition');
    if (clearCompBtn) {
        clearCompBtn.addEventListener('click', clearCompetitionSelection);
    }
}

// Limpa selecao de time
function clearTeamSelection(type) {
    const input = document.getElementById(`match-${type}-team`);
    const preview = document.getElementById(`${type}-team-preview`);

    // Limpa campos ocultos
    document.getElementById(`match-${type}-team-id`).value = '';
    document.getElementById(`match-${type}-team-logo`).value = '';
    document.getElementById(`match-${type}-team-stadium`).value = '';

    // Limpa e mostra input
    if (input) {
        input.value = '';
        input.style.display = 'block';
        input.focus();
    }

    // Esconde preview
    if (preview) {
        preview.style.display = 'none';
    }

    // Limpa estadio se era automatico
    const venueHint = document.getElementById('venue-auto-hint');
    if (venueHint && venueHint.style.display !== 'none') {
        document.getElementById('match-venue').value = '';
        venueHint.style.display = 'none';
    }
}

// Limpa selecao de competicao
function clearCompetitionSelection() {
    const input = document.getElementById('match-competition');
    const preview = document.getElementById('competition-preview');

    // Limpa campos ocultos
    document.getElementById('match-competition-id').value = '';
    document.getElementById('match-competition-logo').value = '';

    // Limpa e mostra input
    if (input) {
        input.value = '';
        input.style.display = 'block';
        input.focus();
    }

    // Esconde preview
    if (preview) {
        preview.style.display = 'none';
    }
}

function openMatchEditModal(match = null) {
    const modal = document.getElementById('match-edit-modal');
    const title = document.getElementById('match-edit-title');
    const form = document.getElementById('match-edit-form');

    if (!modal || !form) return;

    // Limpa o formulario
    form.reset();
    resetMatchFormSelections();

    if (match) {
        // Modo edicao
        title.innerHTML = '<i class="fas fa-edit"></i> Editar Partida';
        document.getElementById('match-edit-id').value = match.id;

        // Preenche times como texto (sem preview, pois nao temos os dados completos)
        document.getElementById('match-home-team').value = match.home_team || '';
        document.getElementById('match-away-team').value = match.away_team || '';

        // Preenche logos se disponiveis
        if (match.home_team_logo) {
            document.getElementById('match-home-team-logo').value = match.home_team_logo;
        }
        if (match.away_team_logo) {
            document.getElementById('match-away-team-logo').value = match.away_team_logo;
        }

        // Preenche competicao
        document.getElementById('match-competition').value = match.competition || '';
        if (match.competition_logo) {
            document.getElementById('match-competition-logo').value = match.competition_logo;
        }

        document.getElementById('match-venue').value = match.venue || '';

        // Preenche mando usando radio buttons
        const locationValue = match.location || 'home';
        const locationRadio = document.querySelector(`input[name="match-location"][value="${locationValue}"]`);
        if (locationRadio) locationRadio.checked = true;

        document.getElementById('match-round').value = match.round || '';
        document.getElementById('match-status').value = match.status || 'upcoming';
        document.getElementById('match-result-bahia').value = match.result_bahia ?? '';
        document.getElementById('match-result-opponent').value = match.result_opponent ?? '';

        // Formata data para datetime-local
        if (match.date) {
            const date = new Date(match.date);
            const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
            document.getElementById('match-date').value = localDate.toISOString().slice(0, 16);
        }

        // Mostra/oculta resultado
        const resultGroup = document.getElementById('match-result-group');
        if (resultGroup) {
            resultGroup.style.display = ['live', 'finished'].includes(match.status) ? 'block' : 'none';
        }
    } else {
        // Modo criacao
        title.innerHTML = '<i class="fas fa-plus"></i> Nova Partida';
        document.getElementById('match-edit-id').value = '';
        document.getElementById('match-result-group').style.display = 'none';

        // Default: Bahia joga em casa
        const homeRadio = document.querySelector('input[name="match-location"][value="home"]');
        if (homeRadio) homeRadio.checked = true;
    }

    modal.classList.add('active');
}

// Reseta selecoes do formulario
function resetMatchFormSelections() {
    // Limpa campos ocultos
    document.getElementById('match-edit-id').value = '';
    document.getElementById('match-home-team-id').value = '';
    document.getElementById('match-home-team-logo').value = '';
    document.getElementById('match-home-team-stadium').value = '';
    document.getElementById('match-away-team-id').value = '';
    document.getElementById('match-away-team-logo').value = '';
    document.getElementById('match-away-team-stadium').value = '';
    document.getElementById('match-competition-id').value = '';
    document.getElementById('match-competition-logo').value = '';

    // Mostra inputs e esconde previews
    const homeInput = document.getElementById('match-home-team');
    const awayInput = document.getElementById('match-away-team');
    const compInput = document.getElementById('match-competition');

    if (homeInput) homeInput.style.display = 'block';
    if (awayInput) awayInput.style.display = 'block';
    if (compInput) compInput.style.display = 'block';

    const homePreview = document.getElementById('home-team-preview');
    const awayPreview = document.getElementById('away-team-preview');
    const compPreview = document.getElementById('competition-preview');

    if (homePreview) homePreview.style.display = 'none';
    if (awayPreview) awayPreview.style.display = 'none';
    if (compPreview) compPreview.style.display = 'none';

    // Esconde hint do estadio
    const venueHint = document.getElementById('venue-auto-hint');
    if (venueHint) venueHint.style.display = 'none';
}

async function saveMatch() {
    const matchId = document.getElementById('match-edit-id').value;
    const isEdit = !!matchId;

    // Obtem mando do radio button
    const location = document.querySelector('input[name="match-location"]:checked')?.value || 'home';

    const data = {
        home_team: document.getElementById('match-home-team').value,
        away_team: document.getElementById('match-away-team').value,
        home_team_logo: document.getElementById('match-home-team-logo').value || '',
        away_team_logo: document.getElementById('match-away-team-logo').value || '',
        date: document.getElementById('match-date').value,
        competition: document.getElementById('match-competition').value,
        competition_logo: document.getElementById('match-competition-logo').value || '',
        venue: document.getElementById('match-venue').value,
        location: location,
        round: document.getElementById('match-round').value,
        status: document.getElementById('match-status').value,
    };

    // Adiciona resultado se status for live ou finished
    if (['live', 'finished'].includes(data.status)) {
        const resultBahia = document.getElementById('match-result-bahia').value;
        const resultOpponent = document.getElementById('match-result-opponent').value;
        if (resultBahia !== '') data.result_bahia = parseInt(resultBahia);
        if (resultOpponent !== '') data.result_opponent = parseInt(resultOpponent);
    }

    const btn = document.getElementById('btn-save-match');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Salvando...';

    try {
        const url = isEdit
            ? `/app/bahia/api/admin/matches/${matchId}/update/`
            : '/app/bahia/api/admin/matches/create/';

        const method = isEdit ? 'PUT' : 'POST';

        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (response.ok && result.success) {
            addLog('success', result.message);
            showToast(result.message, 'success');
            document.getElementById('match-edit-modal').classList.remove('active');
            loadAdminMatches();
        } else {
            addLog('error', result.error || 'Erro ao salvar partida');
            showToast(result.error || 'Erro ao salvar partida', 'error');
        }
    } catch (error) {
        console.error('Erro:', error);
        addLog('error', 'Erro ao salvar partida');
        showToast('Erro ao salvar partida', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalText;
    }
}

async function loadAdminMatches() {
    const container = document.getElementById('admin-matches-list');
    if (!container) return;

    container.innerHTML = '<div class="loading-spinner"><i class="fas fa-spinner fa-spin"></i> Carregando partidas...</div>';

    try {
        const response = await fetch('/app/bahia/api/admin/matches/', {
            credentials: 'same-origin'
        });

        if (!response.ok) {
            if (response.status === 403) {
                container.innerHTML = '<div class="empty-state"><i class="fas fa-lock"></i><p>Funcao disponivel apenas em modo de desenvolvimento</p></div>';
                return;
            }
            throw new Error('Erro ao carregar partidas');
        }

        const data = await response.json();

        if (!data.matches || data.matches.length === 0) {
            container.innerHTML = '<div class="empty-state"><i class="fas fa-calendar-times"></i><p>Nenhuma partida cadastrada</p></div>';
            return;
        }

        let html = '<div class="admin-matches-table">';

        data.matches.forEach(match => {
            const statusClass = getStatusClass(match.status);
            const statusLabel = getStatusLabel(match.status);
            const matchDate = match.date ? new Date(match.date) : null;
            const dateStr = matchDate ? matchDate.toLocaleDateString('pt-BR') : '-';
            const timeStr = matchDate ? matchDate.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '';

            html += `
                <div class="admin-match-row">
                    <div class="match-info">
                        <div class="match-teams-mini">
                            <span class="team-home">${match.home_team}</span>
                            <span class="vs">x</span>
                            <span class="team-away">${match.away_team}</span>
                        </div>
                        <div class="match-details-mini">
                            <span class="match-date-mini"><i class="fas fa-calendar"></i> ${dateStr} ${timeStr}</span>
                            <span class="match-comp-mini"><i class="fas fa-trophy"></i> ${match.competition || '-'}</span>
                        </div>
                    </div>
                    <div class="match-status-badge ${statusClass}">${statusLabel}</div>
                    <div class="match-actions">
                        <button class="btn-icon btn-edit" onclick="editMatch(${match.id})" title="Editar">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn-icon btn-delete" onclick="deleteMatch(${match.id})" title="Excluir">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `;
        });

        html += '</div>';
        container.innerHTML = html;

        // Armazena matches para edicao
        window._adminMatches = data.matches;

    } catch (error) {
        console.error('Erro:', error);
        container.innerHTML = '<div class="empty-state error"><i class="fas fa-exclamation-triangle"></i><p>Erro ao carregar partidas</p></div>';
    }
}

function getStatusClass(status) {
    const classes = {
        'upcoming': 'status-upcoming',
        'live': 'status-live',
        'finished': 'status-finished',
        'cancelled': 'status-cancelled',
        'postponed': 'status-postponed'
    };
    return classes[status] || 'status-upcoming';
}

function getStatusLabel(status) {
    const labels = {
        'upcoming': 'Agendado',
        'live': 'Ao Vivo',
        'finished': 'Encerrado',
        'cancelled': 'Cancelado',
        'postponed': 'Adiado'
    };
    return labels[status] || status;
}

function editMatch(matchId) {
    const match = window._adminMatches?.find(m => m.id === matchId);
    if (match) {
        openMatchEditModal(match);
    } else {
        showToast('Partida nao encontrada', 'error');
    }
}

async function deleteMatch(matchId) {
    if (!confirm('Tem certeza que deseja excluir esta partida? Todos os palpites associados serao removidos!')) {
        return;
    }

    try {
        const response = await fetch(`/app/bahia/api/admin/matches/${matchId}/delete/`, {
            method: 'DELETE',
            headers: {
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin'
        });

        const result = await response.json();

        if (response.ok && result.success) {
            addLog('success', result.message);
            showToast(result.message, 'success');
            loadAdminMatches();
        } else {
            addLog('error', result.error || 'Erro ao excluir partida');
            showToast(result.error || 'Erro ao excluir partida', 'error');
        }
    } catch (error) {
        console.error('Erro:', error);
        addLog('error', 'Erro ao excluir partida');
        showToast('Erro ao excluir partida', 'error');
    }
}

// ==================== GERENCIAMENTO DE USUARIOS ====================

let usersCache = [];
let usersFilterTimeout = null;

async function loadAdminUsers() {
    const listEl = document.getElementById('admin-users-list');
    if (!listEl) return;

    const roleFilter = document.getElementById('filter-user-role')?.value || '';
    const statusFilter = document.getElementById('filter-user-status')?.value || '';
    const searchFilter = document.getElementById('filter-user-search')?.value || '';

    try {
        const params = new URLSearchParams();
        if (roleFilter) params.append('role', roleFilter);
        if (statusFilter) params.append('status', statusFilter);
        if (searchFilter) params.append('search', searchFilter);

        const response = await fetch(`/app/bahia/api/admin/users/?${params}`, {
            credentials: 'same-origin'
        });

        if (!response.ok) {
            throw new Error('Erro ao carregar usuarios');
        }

        const data = await response.json();
        usersCache = data.users;

        // Atualiza stats
        updateUsersStats(data.stats);

        // Renderiza lista
        renderUsersList(data.users);

    } catch (error) {
        console.error('Erro ao carregar usuarios:', error);
        listEl.innerHTML = `
            <div class="users-empty">
                <i class="fas fa-exclamation-triangle"></i>
                <p>Erro ao carregar usuarios</p>
            </div>
        `;
    }
}

function updateUsersStats(stats) {
    document.getElementById('stat-total-users').textContent = stats.total || 0;
    document.getElementById('stat-admins').textContent = stats.admins || 0;
    document.getElementById('stat-supervisors').textContent = stats.supervisors || 0;
    document.getElementById('stat-palpiteiros').textContent = stats.users || 0;
}

function renderUsersList(users) {
    const listEl = document.getElementById('admin-users-list');
    if (!listEl) return;

    if (!users || users.length === 0) {
        listEl.innerHTML = `
            <div class="users-empty">
                <i class="fas fa-users"></i>
                <p>Nenhum usuario encontrado</p>
            </div>
        `;
        return;
    }

    listEl.innerHTML = users.map(user => {
        const initials = user.name.split(' ').map(n => n[0]).join('').substring(0, 2);
        const roleBadgeClass = {
            'admin': 'badge-admin',
            'supervisor': 'badge-supervisor',
            'user': 'badge-user'
        }[user.role] || 'badge-user';

        let statusBadge = '';
        if (!user.is_active) {
            statusBadge = '<span class="user-status-badge status-inactive">Inativo</span>';
        } else if (!user.is_verified) {
            statusBadge = '<span class="user-status-badge status-unverified">Nao verificado</span>';
        }

        return `
            <div class="user-card ${!user.is_active ? 'inactive' : ''}" data-user-id="${user.id}">
                <div class="user-card-info">
                    <div class="user-avatar">${initials}</div>
                    <div class="user-details">
                        <span class="user-name">${user.name}</span>
                        <span class="user-email">${user.email}</span>
                        <div class="user-meta">
                            <span class="user-role-badge ${roleBadgeClass}">${user.role_display}</span>
                            ${statusBadge}
                        </div>
                    </div>
                </div>
                <div class="user-stats">
                    <div class="user-stat">
                        <span class="value">${user.points}</span>
                        <span class="label">Pontos</span>
                    </div>
                    <div class="user-stat">
                        <span class="value">${user.hits}</span>
                        <span class="label">Acertos</span>
                    </div>
                </div>
                <div class="user-actions">
                    <button class="btn-icon btn-edit" onclick="openUserEditModal(${user.id})" title="Editar">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn-icon btn-toggle" onclick="toggleUserStatus(${user.id})" title="${user.is_active ? 'Desativar' : 'Ativar'}">
                        <i class="fas fa-${user.is_active ? 'ban' : 'check'}"></i>
                    </button>
                    <button class="btn-icon btn-delete" onclick="deleteUser(${user.id}, '${user.name}')" title="Excluir">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function openUserEditModal(userId = null) {
    const modal = document.getElementById('user-edit-modal');
    const form = document.getElementById('user-edit-form');
    const title = document.getElementById('user-edit-title');

    if (!modal || !form) return;

    // Limpa form
    form.reset();
    document.getElementById('user-edit-id').value = '';
    document.getElementById('user-points').value = 0;
    document.getElementById('user-hits').value = 0;
    document.getElementById('user-is-active').checked = true;
    document.getElementById('user-is-verified').checked = false;

    if (userId) {
        // Modo edicao - busca dados do usuario
        title.innerHTML = '<i class="fas fa-user-edit"></i> Editar Usuario';

        const user = usersCache.find(u => u.id === userId);
        if (user) {
            document.getElementById('user-edit-id').value = user.id;
            document.getElementById('user-name').value = user.name;
            document.getElementById('user-email').value = user.email;
            document.getElementById('user-role').value = user.role;
            document.getElementById('user-points').value = user.points;
            document.getElementById('user-hits').value = user.hits;
            document.getElementById('user-is-active').checked = user.is_active;
            document.getElementById('user-is-verified').checked = user.is_verified;
        }
    } else {
        // Modo criacao
        title.innerHTML = '<i class="fas fa-user-plus"></i> Novo Usuario';
    }

    modal.classList.add('active');
}

function closeUserEditModal() {
    const modal = document.getElementById('user-edit-modal');
    if (modal) {
        modal.classList.remove('active');
    }
}

async function saveUser(event) {
    event.preventDefault();

    const userId = document.getElementById('user-edit-id').value;
    const isNew = !userId;

    const userData = {
        name: document.getElementById('user-name').value.trim(),
        email: document.getElementById('user-email').value.trim(),
        role: document.getElementById('user-role').value,
        password: document.getElementById('user-password').value,
        points: parseInt(document.getElementById('user-points').value) || 0,
        hits: parseInt(document.getElementById('user-hits').value) || 0,
        is_active: document.getElementById('user-is-active').checked,
        is_verified: document.getElementById('user-is-verified').checked,
    };

    // Validacoes
    if (!userData.name || !userData.email) {
        showToast('Nome e e-mail sao obrigatorios', 'error');
        return;
    }

    if (isNew && !userData.password) {
        // Para novo usuario sem senha, avisa que sera enviado link de ativacao
        userData.send_activation = true;
    }

    if (userData.password && userData.password.length < 6) {
        showToast('Senha deve ter no minimo 6 caracteres', 'error');
        return;
    }

    const saveBtn = document.getElementById('btn-save-user');
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Salvando...';
    }

    try {
        const url = isNew
            ? '/app/bahia/api/admin/users/create/'
            : `/app/bahia/api/admin/users/${userId}/update/`;

        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify(userData)
        });

        const result = await response.json();

        if (response.ok && result.success) {
            showToast(result.message, 'success');
            addLog('success', result.message);
            closeUserEditModal();
            loadAdminUsers();
        } else {
            showToast(result.error || 'Erro ao salvar usuario', 'error');
            addLog('error', result.error || 'Erro ao salvar usuario');
        }
    } catch (error) {
        console.error('Erro:', error);
        showToast('Erro ao salvar usuario', 'error');
        addLog('error', 'Erro ao salvar usuario');
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = '<i class="fas fa-save"></i> Salvar Usuario';
        }
    }
}

async function toggleUserStatus(userId) {
    try {
        const response = await fetch(`/app/bahia/api/admin/users/${userId}/toggle-status/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin'
        });

        const result = await response.json();

        if (response.ok && result.success) {
            showToast(result.message, 'success');
            addLog('success', result.message);
            loadAdminUsers();
        } else {
            showToast(result.error || 'Erro ao alterar status', 'error');
        }
    } catch (error) {
        console.error('Erro:', error);
        showToast('Erro ao alterar status do usuario', 'error');
    }
}

async function deleteUser(userId, userName) {
    if (!confirm(`Tem certeza que deseja excluir o usuario "${userName}"?\n\nEsta acao nao pode ser desfeita.`)) {
        return;
    }

    try {
        const response = await fetch(`/app/bahia/api/admin/users/${userId}/delete/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin'
        });

        const result = await response.json();

        if (response.ok && result.success) {
            showToast(result.message, 'success');
            addLog('success', result.message);
            loadAdminUsers();
        } else {
            showToast(result.error || 'Erro ao excluir usuario', 'error');
        }
    } catch (error) {
        console.error('Erro:', error);
        showToast('Erro ao excluir usuario', 'error');
    }
}

// Event listeners para gerenciamento de usuarios
function initUserManagement() {
    // Botao novo usuario
    const btnNewUser = document.getElementById('btn-new-user');
    if (btnNewUser) {
        btnNewUser.addEventListener('click', () => openUserEditModal());
    }

    // Fechar modal
    const closeBtn = document.getElementById('close-user-edit-modal');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeUserEditModal);
    }

    const cancelBtn = document.getElementById('btn-cancel-user');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', closeUserEditModal);
    }

    // Form submit
    const form = document.getElementById('user-edit-form');
    if (form) {
        form.addEventListener('submit', saveUser);
    }

    // Filtros
    const roleFilter = document.getElementById('filter-user-role');
    const statusFilter = document.getElementById('filter-user-status');
    const searchFilter = document.getElementById('filter-user-search');

    if (roleFilter) {
        roleFilter.addEventListener('change', loadAdminUsers);
    }

    if (statusFilter) {
        statusFilter.addEventListener('change', loadAdminUsers);
    }

    if (searchFilter) {
        searchFilter.addEventListener('input', () => {
            clearTimeout(usersFilterTimeout);
            usersFilterTimeout = setTimeout(loadAdminUsers, 300);
        });
    }

    // Modal click outside
    const modal = document.getElementById('user-edit-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeUserEditModal();
            }
        });
    }

    // Carrega lista inicial
    loadAdminUsers();

    // Inicializa configuracoes da API
    initAPIConfig();
}

// ==================== CONFIGURACOES DA API ====================

async function loadAPIConfig() {
    try {
        const response = await fetch('/app/bahia/api/admin/config/', {
            credentials: 'same-origin'
        });

        if (!response.ok) return;

        const config = await response.json();

        // Atualiza campos do formulario - API
        const apiEnabled = document.getElementById('config-api-enabled');
        const autoStart = document.getElementById('config-auto-start');
        const autoUpdate = document.getElementById('config-auto-update');
        const pollingInterval = document.getElementById('config-polling-interval');
        const minutesBefore = document.getElementById('config-minutes-before');
        const apiCallsCount = document.getElementById('api-calls-count');

        if (apiEnabled) apiEnabled.checked = config.api_enabled;
        if (autoStart) autoStart.checked = config.auto_start_matches;
        if (autoUpdate) autoUpdate.checked = config.auto_update_scores;
        if (pollingInterval) pollingInterval.value = config.polling_interval;
        if (minutesBefore) minutesBefore.value = config.minutes_before_match;
        if (apiCallsCount) apiCallsCount.textContent = config.total_api_calls_today || 0;

        // Atualiza status do polling
        updatePollingStatus(config.last_poll_status, config.last_poll_message, config.last_poll_at);

        // Atualiza campos do formulario - Seguranca
        const require2fa = document.getElementById('config-require-2fa');
        if (require2fa) require2fa.checked = config.require_2fa || false;

        // Atualiza status visual do 2FA
        update2FAStatus(config.require_2fa);

        // Atualiza campos do formulario - Pontuacao
        const pointsVictory = document.getElementById('config-points-victory');
        const pointsDraw = document.getElementById('config-points-draw');
        const roundCost = document.getElementById('config-round-cost');

        if (pointsVictory) pointsVictory.value = config.points_exact_victory || 3;
        if (pointsDraw) pointsDraw.value = config.points_exact_draw || 1;
        if (roundCost) roundCost.value = (config.round_cost || 0).toFixed(2);

        // Atualiza display de regras atuais
        updateScoringInfo(config.points_exact_victory, config.points_exact_draw, config.round_cost);

    } catch (error) {
        console.error('Erro ao carregar configuracoes:', error);
    }
}

function updateScoringInfo(pointsVictory, pointsDraw, roundCost) {
    const infoVictory = document.getElementById('info-points-victory');
    const infoDraw = document.getElementById('info-points-draw');
    const infoCost = document.getElementById('info-round-cost');

    if (infoVictory) infoVictory.textContent = pointsVictory || 3;
    if (infoDraw) infoDraw.textContent = pointsDraw || 1;
    if (infoCost) infoCost.textContent = (roundCost || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function update2FAStatus(enabled) {
    const statusEl = document.getElementById('info-2fa-status');
    if (!statusEl) return;

    if (enabled) {
        statusEl.innerHTML = '<i class="fas fa-lock text-green"></i> Ativado';
    } else {
        statusEl.innerHTML = '<i class="fas fa-lock-open text-muted"></i> Desativado';
    }
}

async function saveSecurityConfig() {
    const require2fa = document.getElementById('config-require-2fa');

    const configData = {
        require_2fa: require2fa ? require2fa.checked : false
    };

    try {
        const response = await fetch('/app/bahia/api/admin/config/update/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            credentials: 'same-origin',
            body: JSON.stringify(configData)
        });

        const data = await response.json();

        if (response.ok && data.success) {
            showToast('Configuracoes de seguranca salvas com sucesso', 'success');
            update2FAStatus(configData.require_2fa);
        } else {
            showToast(data.error || 'Erro ao salvar configuracoes', 'error');
        }
    } catch (error) {
        console.error('Erro ao salvar configuracoes de seguranca:', error);
        showToast('Erro ao salvar configuracoes', 'error');
    }
}

function updatePollingStatus(status, message, lastPoll) {
    const statusEl = document.getElementById('polling-status');
    if (!statusEl) return;

    const badge = statusEl.querySelector('.status-badge');
    const lastUpdate = document.getElementById('polling-last-update');

    if (badge) {
        // Remove classes antigas
        badge.classList.remove('status-idle', 'status-success', 'status-error', 'status-running');

        // Define texto e classe baseado no status
        let badgeText = 'Aguardando';
        let badgeClass = 'status-idle';

        switch (status) {
            case 'success':
                badgeText = 'OK';
                badgeClass = 'status-success';
                break;
            case 'error':
                badgeText = 'Erro';
                badgeClass = 'status-error';
                break;
            case 'running':
                badgeText = 'Executando...';
                badgeClass = 'status-running';
                break;
            case 'idle':
                badgeText = 'Aguardando';
                badgeClass = 'status-idle';
                break;
        }

        badge.textContent = badgeText;
        badge.classList.add(badgeClass);

        if (message) {
            badge.title = message;
        }
    }

    if (lastUpdate && lastPoll) {
        lastUpdate.textContent = `Ultima atualizacao: ${lastPoll}`;
    }
}

async function saveAPIConfig() {
    const apiEnabled = document.getElementById('config-api-enabled');
    const autoStart = document.getElementById('config-auto-start');
    const autoUpdate = document.getElementById('config-auto-update');
    const pollingInterval = document.getElementById('config-polling-interval');
    const minutesBefore = document.getElementById('config-minutes-before');

    const data = {
        api_enabled: apiEnabled ? apiEnabled.checked : true,
        auto_start_matches: autoStart ? autoStart.checked : true,
        auto_update_scores: autoUpdate ? autoUpdate.checked : true,
        polling_interval: pollingInterval ? parseInt(pollingInterval.value) : 60,
        minutes_before_match: minutesBefore ? parseInt(minutesBefore.value) : 10,
    };

    try {
        const response = await fetch('/app/bahia/api/admin/config/update/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin',
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (response.ok && result.success) {
            showToast('Configuracoes salvas com sucesso', 'success');
        } else {
            showToast(result.error || 'Erro ao salvar configuracoes', 'error');
        }
    } catch (error) {
        console.error('Erro ao salvar configuracoes:', error);
        showToast('Erro ao salvar configuracoes', 'error');
    }
}

async function saveScoringConfig() {
    const pointsVictory = document.getElementById('config-points-victory');
    const pointsDraw = document.getElementById('config-points-draw');
    const roundCost = document.getElementById('config-round-cost');

    const data = {
        points_exact_victory: pointsVictory ? parseInt(pointsVictory.value) : 3,
        points_exact_draw: pointsDraw ? parseInt(pointsDraw.value) : 1,
        round_cost: roundCost ? parseFloat(roundCost.value) : 0,
    };

    try {
        const response = await fetch('/app/bahia/api/admin/config/update/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin',
            body: JSON.stringify(data)
        });

        const result = await response.json();

        if (response.ok && result.success) {
            showToast('Regras de pontuacao salvas com sucesso', 'success');
            // Atualiza display de regras atuais
            updateScoringInfo(result.config.points_exact_victory, result.config.points_exact_draw, result.config.round_cost);
        } else {
            showToast(result.error || 'Erro ao salvar pontuacao', 'error');
        }
    } catch (error) {
        console.error('Erro ao salvar pontuacao:', error);
        showToast('Erro ao salvar pontuacao', 'error');
    }
}

function initAPIConfig() {
    // Botao salvar Seguranca
    const btnSaveSecurity = document.getElementById('btn-save-security-config');
    if (btnSaveSecurity) {
        btnSaveSecurity.addEventListener('click', saveSecurityConfig);
    }

    // Botao salvar API
    const btnSave = document.getElementById('btn-save-api-config');
    if (btnSave) {
        btnSave.addEventListener('click', saveAPIConfig);
    }

    // Botao salvar Pontuacao
    const btnSaveScoring = document.getElementById('btn-save-scoring-config');
    if (btnSaveScoring) {
        btnSaveScoring.addEventListener('click', saveScoringConfig);
    }

    // Carrega configuracoes
    loadAPIConfig();
}
