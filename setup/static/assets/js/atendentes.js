/**
 * atendentes.js — Gestão de atendentes e suas permissões.
 */

'use strict';

let _atendentesCurrentPage = 1;
let _prodChart = null;

// ---- Estado dos gráficos de timeline por atendente ----
const _openTimelines  = new Set();  // IDs com painel aberto
const _timelineCharts = {};         // { atendenteId: Chart }
const _timelineLoaded = {};         // { atendenteId: monthOffset atual }

// Paleta de cores para os datasets do gráfico
const _PROD_CORES = [
    { border: '#4f46e5', bg: 'rgba(79,70,229,0.08)' },
    { border: '#0ea5e9', bg: 'rgba(14,165,233,0.08)' },
    { border: '#10b981', bg: 'rgba(16,185,129,0.08)' },
    { border: '#f59e0b', bg: 'rgba(245,158,11,0.08)' },
    { border: '#ef4444', bg: 'rgba(239,68,68,0.08)' },
    { border: '#8b5cf6', bg: 'rgba(139,92,246,0.08)' },
    { border: '#ec4899', bg: 'rgba(236,72,153,0.08)' },
    { border: '#14b8a6', bg: 'rgba(20,184,166,0.08)' },
];

// ---------------------------------------------------------------------------
// Inicialização
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', function () {
    carregarListaAtendentes(1);
    _inicializarSeletoresProdutividade();

    // Busca com debounce
    const searchInput = document.getElementById('atendentes-search');
    if (searchInput) {
        let debounceTimer;
        searchInput.addEventListener('input', function () {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => carregarListaAtendentes(1), 400);
        });
    }

    // Delegação de cliques da lista (paginação + toggle timeline + período)
    document.getElementById('atendentes-lista-container').addEventListener('click', function (e) {
        const link = e.target.closest('.page-link[data-page]');
        if (link) { e.preventDefault(); carregarListaAtendentes(parseInt(link.dataset.page)); return; }

        const toggleBtn = e.target.closest('.timeline-toggle');
        if (toggleBtn) { _toggleTimeline(parseInt(toggleBtn.dataset.atendId)); return; }

        // Clicar em qualquer parte da linha (exceto botões de ação) também abre/fecha
        const atendRow = e.target.closest('tr.atendente-row');
        if (atendRow && !e.target.closest('button') && !e.target.closest('a')) {
            _toggleTimeline(parseInt(atendRow.dataset.atendId));
            return;
        }
    });
    document.getElementById('atendentes-lista-container').addEventListener('change', function (e) {
        const sel = e.target.closest('.timeline-day-sel');
        if (sel) {
            const atendId = parseInt(sel.dataset.atendId);
            const day     = parseInt(sel.value);
            const now     = new Date();
            _carregarTimeline(atendId, day, now.getMonth() + 1, now.getFullYear());
        }
    });
});

// ---------------------------------------------------------------------------
// Gráfico de Produtividade
// ---------------------------------------------------------------------------

const _NOMES_MESES = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];
let _prodMode = 'monthly'; // 'monthly' | 'annual'

// Mapa de períodos: { ano: [meses] } vindo do servidor
let _periodosProdutividade = {};

function _inicializarSeletoresProdutividade() {
    const monthSel = document.getElementById('prod-month-select');
    const yearSel  = document.getElementById('prod-year-select');
    if (!monthSel || !yearSel) return;

    // Desabilitar enquanto carrega
    monthSel.disabled = true;
    yearSel.disabled  = true;

    fetch('/atendentes/periodos/', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(r => r.json())
        .then(data => {
            _periodosProdutividade = data.periodos || {};
            const current = data.current;

            const anos = Object.keys(_periodosProdutividade).map(Number).sort((a, b) => b - a);

            // Sem dados: usar mês/ano atual como único período
            if (anos.length === 0) {
                _periodosProdutividade[current.year] = [current.month];
                anos.push(current.year);
            }

            // Popular years
            yearSel.innerHTML = '';
            anos.forEach(y => {
                const opt = document.createElement('option');
                opt.value = y;
                opt.textContent = y;
                yearSel.appendChild(opt);
            });

            // Selecionar ano: preferir ano atual se disponível, senão o primeiro
            const anoInicial = anos.includes(current.year) ? current.year : anos[0];
            yearSel.value = anoInicial;

            // Popular meses do ano selecionado
            _popularMeses(monthSel, anoInicial, current);

            monthSel.disabled = false;
            yearSel.disabled  = false;

            carregarGraficoProdutividade();

            yearSel.addEventListener('change', function () {
                if (_prodMode === 'monthly') _popularMeses(monthSel, parseInt(this.value), current);
                carregarGraficoProdutividade();
            });
            monthSel.addEventListener('change', carregarGraficoProdutividade);

            // Botões de modo
            document.getElementById('prod-mode-monthly')?.addEventListener('click', () => _setProdMode('monthly', current));
            document.getElementById('prod-mode-annual')?.addEventListener('click',  () => _setProdMode('annual', current));
        })
        .catch(() => {
            // Fallback: popular com mês/ano atual
            const hoje = new Date();
            yearSel.innerHTML = `<option value="${hoje.getFullYear()}">${hoje.getFullYear()}</option>`;
            monthSel.innerHTML = `<option value="${hoje.getMonth()+1}">${_NOMES_MESES[hoje.getMonth()]}</option>`;
            monthSel.disabled = false;
            yearSel.disabled  = false;
            carregarGraficoProdutividade();
        });
}

function _popularMeses(monthSel, ano, current) {
    const meses = (_periodosProdutividade[ano] || []).slice().sort((a, b) => a - b);
    monthSel.innerHTML = '';
    meses.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = _NOMES_MESES[m - 1];
        monthSel.appendChild(opt);
    });
    // Selecionar mês atual se disponível, senão o último do ano
    if (ano === current.year && meses.includes(current.month)) {
        monthSel.value = current.month;
    } else {
        monthSel.value = meses[meses.length - 1];
    }
}

function _setProdMode(mode, current) {
    _prodMode = mode;
    const monthSel  = document.getElementById('prod-month-select');
    const btnMes    = document.getElementById('prod-mode-monthly');
    const btnAno    = document.getElementById('prod-mode-annual');
    const subtitle  = document.getElementById('prod-subtitle');

    if (mode === 'annual') {
        if (monthSel) monthSel.style.display = 'none';
        btnMes?.classList.replace('btn-primary', 'btn-outline-primary');
        btnAno?.classList.replace('btn-outline-primary', 'btn-primary');
        if (subtitle) subtitle.textContent = 'Clientes cadastrados por atendente ao longo do ano';
    } else {
        if (monthSel) monthSel.style.display = '';
        btnMes?.classList.replace('btn-outline-primary', 'btn-primary');
        btnAno?.classList.replace('btn-primary', 'btn-outline-primary');
        if (subtitle) subtitle.textContent = 'Clientes cadastrados por atendente ao longo do mês';
        const yearSel = document.getElementById('prod-year-select');
        if (yearSel) _popularMeses(monthSel, parseInt(yearSel.value), current);
    }
    carregarGraficoProdutividade();
}

function carregarGraficoProdutividade() {
    const monthSel = document.getElementById('prod-month-select');
    const yearSel  = document.getElementById('prod-year-select');
    if (!yearSel) return;

    const year  = yearSel.value;
    const month = monthSel?.value;

    const loading = document.getElementById('prod-loading');
    const empty   = document.getElementById('prod-empty');
    const canvas  = document.getElementById('prod-chart');
    const totais  = document.getElementById('prod-totais');

    if (loading) loading.classList.remove('d-none');
    if (empty)   empty.classList.add('d-none');
    if (canvas)  canvas.style.display = 'none';
    if (totais)  totais.innerHTML = '';

    const params = _prodMode === 'annual'
        ? `mode=annual&year=${year}`
        : `mode=monthly&month=${month}&year=${year}`;

    fetch(`/atendentes/produtividade/?${params}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
        .then(r => r.json())
        .then(data => {
            if (loading) loading.classList.add('d-none');

            if (!data.atendentes || data.atendentes.length === 0 || data.atendentes.every(a => a.total === 0)) {
                if (empty) empty.classList.remove('d-none');
                return;
            }

            if (canvas) canvas.style.display = '';
            _renderizarGrafico(data);
            _renderizarTotais(data.atendentes);
        })
        .catch(() => {
            if (loading) loading.classList.add('d-none');
            if (empty)   empty.classList.remove('d-none');
        });
}

function _renderizarGrafico(data) {
    const canvas = document.getElementById('prod-chart');
    if (!canvas) return;

    const labels = data.mode === 'annual'
        ? data.labels.map(m => _NOMES_MESES[m - 1])
        : data.days.map(d => `Dia ${d}`);
    const datasets = data.atendentes.map((atend, i) => {
        const cor = _PROD_CORES[i % _PROD_CORES.length];
        return {
            label:           `${atend.nome} (${atend.total})`,
            data:            atend.data,
            borderColor:     cor.border,
            backgroundColor: cor.bg,
            borderWidth:     2,
            pointRadius:     atend.data.map(v => v > 0 ? 4 : 2),
            pointHoverRadius: 6,
            fill:            true,
            tension:         0.35,
        };
    });

    if (_prodChart) {
        _prodChart.destroy();
        _prodChart = null;
    }

    _prodChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'top', labels: { usePointStyle: true, padding: 16 } },
                tooltip: {
                    callbacks: {
                        title: ctx => data.mode === 'annual'
                            ? _NOMES_MESES[(data.labels[ctx[0].dataIndex] ?? ctx[0].dataIndex + 1) - 1]
                            : `Dia ${data.days[ctx[0].dataIndex] ?? ctx[0].dataIndex + 1}`,
                        label: ctx => ` ${ctx.dataset.label.split(' (')[0]}: ${ctx.parsed.y} cadastro${ctx.parsed.y !== 1 ? 's' : ''}`,
                    },
                },
            },
            scales: {
                x: { grid: { display: false } },
                y: {
                    beginAtZero: true,
                    ticks: { stepSize: 1, precision: 0 },
                    grid: { color: 'rgba(0,0,0,0.05)' },
                },
            },
        },
    });
}

function _renderizarTotais(atendentes) {
    const totais = document.getElementById('prod-totais');
    if (!totais) return;
    totais.innerHTML = atendentes.map((a, i) => {
        const cor = _PROD_CORES[i % _PROD_CORES.length].border;
        return `<span class="badge rounded-pill px-3 py-2" style="background:${cor};font-size:0.82rem;">
                    ${a.nome} &mdash; <strong>${a.total}</strong> cadastro${a.total !== 1 ? 's' : ''}
                </span>`;
    }).join('');
}

// ---------------------------------------------------------------------------
// Reload completo da página (tabela + gráfico)
// ---------------------------------------------------------------------------

function _recarregarPagina(page) {
    const previouslyOpen = Array.from(_openTimelines);
    _destruirTimelines();
    carregarListaAtendentes(page ?? _atendentesCurrentPage, previouslyOpen);
    carregarGraficoProdutividade();
}

// ---------------------------------------------------------------------------
// Tabela AJAX
// ---------------------------------------------------------------------------

function carregarListaAtendentes(page, reabrir = []) {
    _atendentesCurrentPage = page || 1;
    const q = (document.getElementById('atendentes-search')?.value || '').trim();
    const container = document.getElementById('atendentes-lista-container');

    const params = new URLSearchParams({ page: _atendentesCurrentPage, q });

    fetch(`/atendentes/lista/?${params}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(r => r.text())
        .then(html => {
            container.innerHTML = html;
            // Re-abrir timelines que estavam abertas antes do reload
            reabrir.forEach(id => {
                if (document.getElementById(`timeline-row-${id}`)) _toggleTimeline(id);
            });
        })
        .catch(() => {
            container.innerHTML = '<div class="alert alert-danger">Erro ao carregar atendentes.</div>';
        });
}

// ---------------------------------------------------------------------------
// Timeline colapsável por atendente
// ---------------------------------------------------------------------------

// Cores por tipo de ação
const _COR_ACAO = {
    create:     '#22c55e',
    update:     '#3b82f6',
    delete:     '#ef4444',
    payment:    '#a855f7',
    cancel:     '#f97316',
    reactivate: '#06b6d4',
    import:     '#eab308',
    migration:  '#94a3b8',
    other:      '#475569',
};

const _LABEL_ACAO = {
    create:     'Criação',
    update:     'Atualização',
    delete:     'Exclusão',
    payment:    'Pagamento',
    cancel:     'Cancelamento',
    reactivate: 'Reativação',
    import:     'Importação',
    migration:  'Migração',
    other:      'Ação',
};

function _pad2(n) { return String(n).padStart(2, '0'); }

function _toggleTimeline(id) {
    const row = document.getElementById(`timeline-row-${id}`);
    if (!row) return;

    const mainRow = row.previousElementSibling;
    const chevron = mainRow?.querySelector('.timeline-chevron');

    const isOpen = !row.classList.contains('d-none');
    if (isOpen) {
        row.classList.add('d-none');
        chevron?.classList.remove('open');
        _openTimelines.delete(id);
    } else {
        row.classList.remove('d-none');
        chevron?.classList.add('open');
        _openTimelines.add(id);
        if (_timelineLoaded[id] === undefined) {
            const now = new Date();
            _carregarTimeline(id, now.getDate(), now.getMonth() + 1, now.getFullYear());
        }
    }
}

function _preencherDaySelector(id, daysInMonth, selectedDay) {
    const sel = document.querySelector(`.timeline-day-sel[data-atend-id="${id}"]`);
    if (!sel || sel.options.length > 0) return; // já preenchido

    const nomes = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
    const now   = new Date();
    const mes   = nomes[now.getMonth()];

    for (let d = 1; d <= daysInMonth; d++) {
        const opt = document.createElement('option');
        opt.value = d;
        opt.textContent = `Dia ${d} / ${mes}`;
        if (d === selectedDay) opt.selected = true;
        sel.appendChild(opt);
    }
}

function _carregarTimeline(id, day, month, year) {
    const panel = document.querySelector(`#timeline-row-${id} .timeline-panel`);
    if (!panel) return;

    const loading   = panel.querySelector('.timeline-loading');
    const empty     = panel.querySelector('.timeline-empty');
    const noHorario = panel.querySelector('.timeline-no-horario');
    const canvas    = panel.querySelector('canvas');

    if (loading)   loading.classList.remove('d-none');
    if (empty)     empty.classList.add('d-none');
    if (noHorario) noHorario.classList.add('d-none');
    if (canvas)    canvas.style.display = 'none';

    fetch(`/atendentes/${id}/timeline/?day=${day}&month=${month}&year=${year}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
        .then(r => r.json())
        .then(data => {
            if (loading) loading.classList.add('d-none');

            // Preencher seletor de dias (apenas uma vez)
            _preencherDaySelector(id, data.days_in_month, data.day);

            if (data.sem_horario && data.logs.length > 0) {
                if (noHorario) noHorario.classList.remove('d-none');
            }

            if (!data.logs || data.logs.length === 0) {
                if (empty) empty.classList.remove('d-none');
                _timelineLoaded[id] = true;
                return;
            }

            if (canvas) canvas.style.display = '';
            _renderTimeline(id, data, canvas);
            _timelineLoaded[id] = true;
        })
        .catch(() => {
            if (loading) loading.classList.add('d-none');
            if (empty)   empty.classList.remove('d-none');
        });
}

function _renderTimeline(id, data, canvas) {
    if (_timelineCharts[id]) {
        _timelineCharts[id].destroy();
        delete _timelineCharts[id];
    }
    if (!canvas) return;

    // Agrupar logs por tipo de ação
    const byAcao = {};
    data.logs.forEach(log => {
        if (!byAcao[log.acao]) byAcao[log.acao] = [];
        byAcao[log.acao].push(log);
    });

    const datasets = Object.entries(byAcao).map(([acao, logs]) => {
        const cor = _COR_ACAO[acao] || '#475569';
        return {
            label:            _LABEL_ACAO[acao] || acao,
            data:             logs.map(l => ({ x: l.hora, y: l.minuto, _log: l })),
            backgroundColor:  cor,
            borderColor:      cor,
            pointRadius:      6,
            pointHoverRadius: 9,
            pointStyle:       'circle',
        };
    });

    // Plugin inline para overlay do expediente
    const expedientePlugin = {
        id: 'expedienteBackground',
        beforeDraw(chart) {
            if (data.sem_horario || !data.horario_inicio || !data.horario_fim) return;
            const { ctx, scales: { x, y } } = chart;
            const area = chart.chartArea;

            const parseH = str => {
                const [h, m] = str.split(':').map(Number);
                return h + m / 60;
            };

            const hi  = parseH(data.horario_inicio);
            const hf  = parseH(data.horario_fim);
            const ii  = data.tem_intervalo && data.intervalo_inicio ? parseH(data.intervalo_inicio) : null;
            const inf = data.tem_intervalo && data.intervalo_fim    ? parseH(data.intervalo_fim)    : null;

            const drawBand = (from, to, color) => {
                const xLeft  = Math.max(x.getPixelForValue(from), area.left);
                const xRight = Math.min(x.getPixelForValue(to),   area.right);
                if (xRight <= xLeft) return;
                ctx.save();
                ctx.fillStyle = color;
                ctx.fillRect(xLeft, area.top, xRight - xLeft, area.bottom - area.top);
                ctx.restore();
            };

            // Antes do expediente
            drawBand(0, hi, 'rgba(249,115,22,0.08)');
            // Durante (entre início e fim, excluindo intervalo)
            if (ii !== null && inf !== null) {
                drawBand(hi, ii,  'rgba(34,197,94,0.10)');
                drawBand(ii, inf, 'rgba(148,163,184,0.12)');
                drawBand(inf, hf, 'rgba(34,197,94,0.10)');
            } else {
                drawBand(hi, hf, 'rgba(34,197,94,0.10)');
            }
            // Após o expediente
            drawBand(hf, 24, 'rgba(239,68,68,0.08)');
        },
    };

    _timelineCharts[id] = new Chart(canvas.getContext('2d'), {
        type: 'scatter',
        data: { datasets },
        plugins: [expedientePlugin],
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { usePointStyle: true, padding: 14, font: { size: 11 } },
                },
                tooltip: {
                    callbacks: {
                        title: ctx => {
                            const log = ctx[0]?.raw?._log;
                            if (!log) return '';
                            return log.acao_label + ' — ' + _pad2(log.hora) + ':' + _pad2(log.minuto);
                        },
                        label: ctx => {
                            const log = ctx.raw?._log;
                            if (!log) return '';
                            const linhas = [];
                            if (log.entidade)    linhas.push('Entidade: ' + log.entidade);
                            if (log.objeto_repr) linhas.push('Objeto: '   + log.objeto_repr);
                            if (log.mensagem)    linhas.push(log.mensagem);
                            return linhas;
                        },
                    },
                },
            },
            scales: {
                x: {
                    type: 'linear',
                    min: 0,
                    max: 23,
                    ticks: {
                        stepSize: 1,
                        font: { size: 10 },
                        callback: v => _pad2(v) + 'h',
                    },
                    grid: { color: 'rgba(0,0,0,0.05)' },
                    title: { display: true, text: 'Hora do dia', font: { size: 10 }, color: '#94a3b8' },
                },
                y: {
                    min: 0,
                    max: 59,
                    ticks: {
                        stepSize: 10,
                        font: { size: 10 },
                        callback: v => ':' + _pad2(v),
                    },
                    grid: { color: 'rgba(0,0,0,0.05)' },
                    title: { display: true, text: 'Minuto', font: { size: 10 }, color: '#94a3b8' },
                },
            },
        },
    });
}

function _destruirTimelines() {
    Object.keys(_timelineCharts).forEach(id => {
        _timelineCharts[id]?.destroy();
        delete _timelineCharts[id];
    });
    Object.keys(_timelineLoaded).forEach(id => delete _timelineLoaded[id]);
    _openTimelines.clear();
}

// ---------------------------------------------------------------------------
// Modal "Ver outros períodos"
// ---------------------------------------------------------------------------

function abrirModalPeriodosAtendente(atendenteId) {
    const row = document.getElementById(`timeline-row-${atendenteId}`);
    const nome = row ? (row.dataset.atendNome || '') : '';

    document.getElementById('modal-periodos-atend-id').value = atendenteId;
    document.getElementById('modal-periodos-nome').textContent = nome;
    document.getElementById('periodos-error').classList.add('d-none');

    // Configurar limites de data: últimos 90 dias
    const hoje = new Date();
    const min  = new Date(hoje);
    min.setDate(min.getDate() - 90);

    const fmt = d => d.toISOString().split('T')[0];
    const inicio = document.getElementById('periodos-data-inicio');
    const fim    = document.getElementById('periodos-data-fim');
    inicio.max = fmt(hoje);
    inicio.min = fmt(min);
    inicio.value = fmt(min);
    fim.max  = fmt(hoje);
    fim.min  = fmt(min);
    fim.value = fmt(hoje);

    bootstrap.Modal.getOrCreateInstance(
        document.getElementById('modal-timeline-periodos')
    ).show();
}

function exportarPeriodoAtendente() {
    const inicio = document.getElementById('periodos-data-inicio').value;
    const fim    = document.getElementById('periodos-data-fim').value;
    const err    = document.getElementById('periodos-error');

    if (!inicio || !fim) {
        err.textContent = 'Informe a data inicial e final.';
        err.classList.remove('d-none');
        return;
    }
    if (inicio > fim) {
        err.textContent = 'A data inicial deve ser anterior ou igual à data final.';
        err.classList.remove('d-none');
        return;
    }

    err.classList.add('d-none');
    showToast('info', 'Exportação de PDF em desenvolvimento.');
}

// ---------------------------------------------------------------------------
// Criar Atendente
// ---------------------------------------------------------------------------

function abrirModalCriarAtendente() {
    document.getElementById('form-criar-atendente').reset();
    document.getElementById('atend-create-error').classList.add('d-none');
    document.getElementById('atend-create-intervalo-block')?.classList.add('d-none');
    document.getElementById('atend-create-tem-intervalo').checked = false;
    // Resetar checkboxes para os defaults do modelo (nav_clientes e dash_card_clientes ligados)
    document.querySelectorAll('#modal-criar-atendente .create-perm-check').forEach(cb => {
        cb.checked = ['nav_clientes', 'dash_card_clientes'].includes(cb.name);
    });
    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById('modal-criar-atendente'));
    modal.show();
}

function submeterCriarAtendente() {
    const btn = document.getElementById('btn-criar-atendente');
    const errorDiv = document.getElementById('atend-create-error');
    errorDiv.classList.add('d-none');

    const permissoes = {};
    document.querySelectorAll('#modal-criar-atendente .create-perm-check').forEach(cb => {
        permissoes[cb.name] = cb.checked;
    });

    const temIntervalo = document.getElementById('atend-create-tem-intervalo').checked;
    const payload = {
        first_name:       document.getElementById('atend-create-first-name').value.trim(),
        last_name:        document.getElementById('atend-create-last-name').value.trim(),
        username:         document.getElementById('atend-create-username').value.trim(),
        email:            document.getElementById('atend-create-email').value.trim(),
        password:         document.getElementById('atend-create-password').value,
        password2:        document.getElementById('atend-create-password2').value,
        horario_inicio:   document.getElementById('atend-create-horario-inicio').value,
        horario_fim:      document.getElementById('atend-create-horario-fim').value,
        tem_intervalo:    temIntervalo,
        intervalo_inicio: temIntervalo ? document.getElementById('atend-create-intervalo-inicio').value : null,
        intervalo_fim:    temIntervalo ? document.getElementById('atend-create-intervalo-fim').value : null,
        permissoes,
    };

    if (!payload.first_name || !payload.username || !payload.password) {
        errorDiv.textContent = 'Nome, usuário e senha são obrigatórios.';
        errorDiv.classList.remove('d-none');
        return;
    }
    if (!payload.horario_inicio || !payload.horario_fim) {
        errorDiv.textContent = 'Informe o horário de início e fim do expediente.';
        errorDiv.classList.remove('d-none');
        return;
    }

    setButtonLoading(btn, true);

    fetch('/atendentes/criar/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify(payload),
    })
        .then(r => r.json())
        .then(data => {
            setButtonLoading(btn, false);
            if (data.error_message) {
                errorDiv.innerHTML = data.error_message;
                errorDiv.classList.remove('d-none');
                return;
            }
            bootstrap.Modal.getInstance(document.getElementById('modal-criar-atendente'))?.hide();
            _recarregarPagina(1);
            showToast('success', data.success_message || 'Atendente criado com sucesso!');
        })
        .catch(() => {
            setButtonLoading(btn, false);
            errorDiv.textContent = 'Erro inesperado. Tente novamente.';
            errorDiv.classList.remove('d-none');
        });
}

// ---------------------------------------------------------------------------
// Editar Permissões
// ---------------------------------------------------------------------------

function editarPermissoes(atendenteId) {
    document.getElementById('perm-atendente-id').value = atendenteId;
    document.getElementById('perm-edit-error').classList.add('d-none');

    fetch(`/atendentes/${atendenteId}/permissoes/?get=1`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(r => r.json())
        .then(data => {
            if (data.error) { showToast('error', data.error); return; }

            document.getElementById('perm-atendente-nome').textContent = data.nome;

            // Preencher checkboxes
            document.querySelectorAll('#modal-editar-permissoes-atendente .perm-check').forEach(cb => {
                cb.checked = !!data.permissoes[cb.name];
            });

            bootstrap.Modal.getOrCreateInstance(
                document.getElementById('modal-editar-permissoes-atendente')
            ).show();
        })
        .catch(() => showToast('error', 'Erro ao carregar permissões.'));
}

function submeterPermissoes() {
    const btn = document.getElementById('btn-salvar-permissoes');
    const atendenteId = document.getElementById('perm-atendente-id').value;
    const errorDiv = document.getElementById('perm-edit-error');
    errorDiv.classList.add('d-none');

    const payload = {};
    document.querySelectorAll('#modal-editar-permissoes-atendente .perm-check').forEach(cb => {
        payload[cb.name] = cb.checked;
    });

    setButtonLoading(btn, true);

    fetch(`/atendentes/${atendenteId}/permissoes/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify(payload),
    })
        .then(r => r.json())
        .then(data => {
            setButtonLoading(btn, false);
            if (data.error_message) {
                errorDiv.innerHTML = data.error_message;
                errorDiv.classList.remove('d-none');
                return;
            }
            bootstrap.Modal.getInstance(document.getElementById('modal-editar-permissoes-atendente'))?.hide();
            showToast('success', data.success_message || 'Permissões salvas!');
            _recarregarPagina();
        })
        .catch(() => {
            setButtonLoading(btn, false);
            errorDiv.textContent = 'Erro inesperado. Tente novamente.';
            errorDiv.classList.remove('d-none');
        });
}

// ---------------------------------------------------------------------------
// Editar Dados do Atendente
// ---------------------------------------------------------------------------

function abrirModalEditarAtendenteDados(atendenteId) {
    document.getElementById('edit-dados-atendente-id').value = atendenteId;
    document.getElementById('edit-dados-error').classList.add('d-none');
    document.getElementById('form-editar-atendente-dados').reset();
    document.getElementById('edit-dados-atendente-id').value = atendenteId;

    fetch(`/atendentes/${atendenteId}/editar/`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(r => r.json())
        .then(data => {
            if (data.error_message) { showToast('error', data.error_message); return; }

            document.getElementById('edit-dados-atendente-nome').textContent =
                (data.first_name + ' ' + data.last_name).trim() || data.username;
            document.getElementById('edit-dados-first-name').value = data.first_name || '';
            document.getElementById('edit-dados-last-name').value  = data.last_name  || '';
            document.getElementById('edit-dados-username').value   = data.username   || '';
            document.getElementById('edit-dados-email').value      = data.email      || '';

            // Horário de expediente
            document.getElementById('edit-dados-horario-inicio').value = data.horario_inicio || '';
            document.getElementById('edit-dados-horario-fim').value    = data.horario_fim    || '';
            const temIntervalo = !!data.tem_intervalo;
            document.getElementById('edit-dados-tem-intervalo').checked = temIntervalo;
            document.getElementById('edit-dados-intervalo-block').classList.toggle('d-none', !temIntervalo);
            document.getElementById('edit-dados-intervalo-inicio').value = data.intervalo_inicio || '';
            document.getElementById('edit-dados-intervalo-fim').value    = data.intervalo_fim    || '';

            bootstrap.Modal.getOrCreateInstance(
                document.getElementById('modal-editar-atendente-dados')
            ).show();
        })
        .catch(() => showToast('error', 'Erro ao carregar dados do atendente.'));
}

function submeterEditarAtendenteDados() {
    const btn = document.getElementById('btn-salvar-atendente-dados');
    const atendenteId = document.getElementById('edit-dados-atendente-id').value;
    const errorDiv = document.getElementById('edit-dados-error');
    errorDiv.classList.add('d-none');

    const temIntervalo = document.getElementById('edit-dados-tem-intervalo').checked;
    const payload = {
        first_name:       document.getElementById('edit-dados-first-name').value.trim(),
        last_name:        document.getElementById('edit-dados-last-name').value.trim(),
        username:         document.getElementById('edit-dados-username').value.trim(),
        email:            document.getElementById('edit-dados-email').value.trim(),
        nova_senha:       document.getElementById('edit-dados-nova-senha').value,
        nova_senha2:      document.getElementById('edit-dados-nova-senha2').value,
        horario_inicio:   document.getElementById('edit-dados-horario-inicio').value,
        horario_fim:      document.getElementById('edit-dados-horario-fim').value,
        tem_intervalo:    temIntervalo,
        intervalo_inicio: temIntervalo ? document.getElementById('edit-dados-intervalo-inicio').value : null,
        intervalo_fim:    temIntervalo ? document.getElementById('edit-dados-intervalo-fim').value    : null,
    };

    if (!payload.first_name || !payload.username) {
        errorDiv.textContent = 'Nome e usuário são obrigatórios.';
        errorDiv.classList.remove('d-none');
        return;
    }
    if (!payload.horario_inicio || !payload.horario_fim) {
        errorDiv.textContent = 'Horário de início e fim do expediente são obrigatórios.';
        errorDiv.classList.remove('d-none');
        return;
    }

    setButtonLoading(btn, true);

    fetch(`/atendentes/${atendenteId}/editar/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify(payload),
    })
        .then(r => r.json())
        .then(data => {
            setButtonLoading(btn, false);
            if (data.error_message) {
                errorDiv.innerHTML = data.error_message;
                errorDiv.classList.remove('d-none');
                return;
            }
            bootstrap.Modal.getInstance(document.getElementById('modal-editar-atendente-dados'))?.hide();
            showToast('success', data.success_message || 'Dados atualizados!');
            _recarregarPagina();
        })
        .catch(() => {
            setButtonLoading(btn, false);
            errorDiv.textContent = 'Erro inesperado. Tente novamente.';
            errorDiv.classList.remove('d-none');
        });
}

// ---------------------------------------------------------------------------
// Toggle Ativo/Inativo
// ---------------------------------------------------------------------------

async function toggleAtendente(atendenteId, nome) {
    const confirmado = await showConfirm(
        'Alterar status',
        `Deseja alterar o status do atendente <strong>${nome}</strong>?`,
        { confirmButtonText: 'Sim, alterar', cancelButtonText: 'Cancelar' }
    );
    if (!confirmado) return;

    fetch(`/atendentes/${atendenteId}/toggle/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrfToken() },
    })
        .then(r => r.json())
        .then(data => {
            if (data.success_message) showToast('success', data.success_message);
            else showToast('error', data.error || 'Erro ao alterar status.');
            _recarregarPagina();
        })
        .catch(() => showToast('error', 'Erro inesperado.'));
}

// ---------------------------------------------------------------------------
// Deletar
// ---------------------------------------------------------------------------

async function deletarAtendente(atendenteId, nome) {
    const confirmado = await showConfirm(
        'Remover atendente',
        `Tem certeza que deseja remover o atendente <strong>${nome}</strong>? Esta ação não pode ser desfeita.`,
        { confirmButtonText: 'Sim, remover', cancelButtonText: 'Cancelar', confirmButtonColor: '#dc3545' }
    );
    if (!confirmado) return;

    fetch(`/atendentes/${atendenteId}/deletar/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrfToken() },
    })
        .then(r => r.json())
        .then(data => {
            if (data.error_message) { showToast('error', data.error_message); return; }
            _recarregarPagina(1);
            showToast('success', data.success_message || 'Atendente removido com sucesso!');
        })
        .catch(() => showToast('error', 'Erro inesperado.'));
}

// ---------------------------------------------------------------------------
// Helper: CSRF token
// ---------------------------------------------------------------------------

function getCsrfToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
           document.cookie.split('; ').find(r => r.startsWith('csrftoken='))?.split('=')[1] || '';
}
