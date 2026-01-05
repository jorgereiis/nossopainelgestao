/**
 * receita_anual.js
 * Gerencia o gráfico de Receita Anual por Forma de Pagamento
 */
(function() {
    'use strict';

    // ========== ELEMENTOS DOM ==========
    const tabButton = document.getElementById('tab-receita-anual');
    const periodoSelect = document.getElementById('receita-anual-periodo');
    const chartCanvas = document.getElementById('receitaAnualChart');
    const loadingEl = document.getElementById('receita-anual-loading');
    const emptyEl = document.getElementById('receita-anual-empty');
    const summaryEl = document.getElementById('receita-anual-summary');
    const totalEl = document.getElementById('receita-anual-total');

    // ========== ESTADO ==========
    let chart = null;
    let dataLoaded = false;
    let currentData = null;

    // ========== PALETA DE CORES ==========
    const COLORS = [
        '#624bff', // Roxo principal
        '#38b2ac', // Teal
        '#f59e0b', // Amber
        '#ef4444', // Vermelho
        '#8b5cf6', // Violeta
        '#10b981', // Verde
        '#3b82f6', // Azul
        '#ec4899', // Rosa
        '#6366f1', // Indigo
        '#14b8a6', // Cyan
    ];

    // ========== UTILITÁRIOS ==========
    function formatBRL(value) {
        return new Intl.NumberFormat('pt-BR', {
            style: 'currency',
            currency: 'BRL',
            minimumFractionDigits: 2
        }).format(value);
    }

    function showLoading() {
        if (loadingEl) loadingEl.classList.remove('d-none');
        if (emptyEl) emptyEl.classList.add('d-none');
        if (chartCanvas) chartCanvas.style.display = 'none';
    }

    function hideLoading() {
        if (loadingEl) loadingEl.classList.add('d-none');
    }

    function showEmpty() {
        hideLoading();
        if (emptyEl) emptyEl.classList.remove('d-none');
        if (chartCanvas) chartCanvas.style.display = 'none';
    }

    function showChart() {
        hideLoading();
        if (emptyEl) emptyEl.classList.add('d-none');
        if (chartCanvas) chartCanvas.style.display = 'block';
    }

    // ========== FETCH DATA ==========
    async function fetchData(periodo) {
        showLoading();
        try {
            const response = await fetch(`/api/receita-anual/?periodo=${periodo}`);
            if (!response.ok) {
                throw new Error('Erro ao carregar dados');
            }
            const data = await response.json();
            currentData = data;
            return data;
        } catch (error) {
            console.error('[ReceitaAnual] Erro ao buscar dados:', error);
            showEmpty();
            return null;
        }
    }

    // ========== BUILD CHART ==========
    function buildChart(data) {
        if (!data || !data.categories || data.categories.length === 0) {
            showEmpty();
            return;
        }

        showChart();

        // Destruir gráfico anterior se existir
        if (chart) {
            chart.destroy();
            chart = null;
        }

        const ctx = chartCanvas.getContext('2d');

        // Preparar datasets com cores
        const datasets = data.series.map((serie, index) => ({
            label: serie.label,
            data: serie.data,
            backgroundColor: COLORS[index % COLORS.length],
            borderColor: COLORS[index % COLORS.length],
            borderWidth: 1,
            borderRadius: 4,
            barPercentage: 0.7,
            categoryPercentage: 0.8
        }));

        chart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.categories,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            usePointStyle: true,
                            padding: 20,
                            font: {
                                size: 11
                            }
                        }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            label: function(context) {
                                const label = context.dataset.label || '';
                                const value = context.parsed.y || 0;
                                return `${label}: ${formatBRL(value)}`;
                            },
                            footer: function(tooltipItems) {
                                let total = 0;
                                tooltipItems.forEach(item => {
                                    total += item.parsed.y || 0;
                                });
                                return `Total: ${formatBRL(total)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        stacked: true,
                        grid: {
                            display: false
                        },
                        ticks: {
                            font: {
                                size: 11
                            }
                        }
                    },
                    y: {
                        stacked: true,
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        },
                        ticks: {
                            font: {
                                size: 11
                            },
                            callback: function(value) {
                                if (value >= 1000000) {
                                    return 'R$ ' + (value / 1000000).toFixed(1) + 'M';
                                } else if (value >= 1000) {
                                    return 'R$ ' + (value / 1000).toFixed(0) + 'k';
                                }
                                return 'R$ ' + value;
                            }
                        }
                    }
                },
                interaction: {
                    mode: 'index',
                    intersect: false
                }
            }
        });
    }

    // ========== UPDATE SUMMARY ==========
    function updateSummary(data) {
        const summaryTitleEl = document.querySelector('#pane-receita-anual .card-title');
        const totalLabelEl = totalEl ? totalEl.querySelector('span:first-child') : null;

        if (!data || !data.summary) {
            if (summaryEl) summaryEl.innerHTML = '<span class="text-muted small">Sem dados</span>';
            if (totalEl) totalEl.querySelector('span:last-child').textContent = '-';
            return;
        }

        // Atualizar título do card conforme período
        const periodo = data.meta?.periodo || 'current';
        let tituloResumo = 'Resumo por Forma de Pagamento';
        let tituloTotal = 'Total Geral';

        if (periodo === 'current') {
            tituloResumo = `Projeção ${data.meta.ano_atual}`;
            tituloTotal = 'Total Projetado';
        } else if (periodo === 'last5') {
            tituloResumo = 'Últimos 5 Anos (Acumulado)';
            tituloTotal = 'Total Acumulado';
        } else if (periodo === 'all') {
            tituloResumo = 'Todos os Anos (Acumulado)';
            tituloTotal = 'Total Acumulado';
        }

        if (summaryTitleEl) {
            summaryTitleEl.innerHTML = `<i class="bi bi-list-ul me-2"></i>${tituloResumo}`;
        }
        if (totalLabelEl) {
            totalLabelEl.textContent = tituloTotal;
        }

        // Renderizar lista de formas de pagamento
        let html = '';
        data.summary.forEach((item, index) => {
            const color = COLORS[index % COLORS.length];
            html += `
                <div class="d-flex justify-content-between align-items-center py-2 border-bottom">
                    <div class="d-flex align-items-center">
                        <span class="rounded-circle me-2" style="width: 10px; height: 10px; background-color: ${color}; display: inline-block;"></span>
                        <span class="small text-truncate" style="max-width: 150px;" title="${item.nome}">${item.nome}</span>
                    </div>
                    <span class="small fw-semibold">${formatBRL(item.valor)}</span>
                </div>
            `;
        });

        if (summaryEl) summaryEl.innerHTML = html || '<span class="text-muted small">Sem dados</span>';

        // Atualizar total geral
        if (totalEl && data.meta) {
            totalEl.querySelector('span:last-child').textContent = formatBRL(data.meta.total_geral || 0);
        }
    }

    // ========== CARREGAR DADOS ==========
    async function loadData() {
        const periodo = periodoSelect ? periodoSelect.value : 'current';
        const data = await fetchData(periodo);
        if (data) {
            buildChart(data);
            updateSummary(data);
            dataLoaded = true;
        }
    }

    // ========== EVENT LISTENERS ==========

    // Lazy loading: carregar apenas quando a aba for exibida
    if (tabButton) {
        tabButton.addEventListener('shown.bs.tab', function() {
            if (!dataLoaded) {
                loadData();
            }
        });
    }

    // Filtro de período
    if (periodoSelect) {
        periodoSelect.addEventListener('change', function() {
            loadData();
        });
    }

    // Debug
    console.log('[ReceitaAnual] Módulo inicializado');

})();
