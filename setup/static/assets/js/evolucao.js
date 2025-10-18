/* Evolução do Patrimônio - renderização do gráfico (Chart.js) */

(function () {
  let chartInstance = null;
  let currentMonths = null;

  function formatCurrencyBRL(value) {
    try {
      return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value);
    } catch (e) {
      return `R$ ${Number(value || 0).toFixed(2)}`;
    }
  }

  const $canvas = () => document.getElementById('evolucaoChart');
  const $wrapper = () => document.getElementById('evolucao-chart-wrapper');
  const $empty = () => document.getElementById('evolucao-empty-state');
  const $periodSelect = () => document.getElementById('evolucao-period-select');

  function showEmpty(message) {
    const empty = $empty();
    const canvas = $canvas();
    if (chartInstance) {
      try { chartInstance.destroy(); } catch (err) { console.warn('Falha ao destruir gráfico:', err); }
      chartInstance = null;
      currentMonths = null;
    }
    if (empty) {
      empty.textContent = message || 'Nenhum dado encontrado para o período escolhido.';
      empty.classList.remove('d-none');
    }
    if (canvas) {
      canvas.classList.add('d-none');
    }
  }

  function hideEmpty() {
    const empty = $empty();
    const canvas = $canvas();
    if (empty) empty.classList.add('d-none');
    if (canvas) canvas.classList.remove('d-none');
  }

  async function fetchData(months = 12) {
    const url = `/api/evolucao-patrimonio/?months=${months}`;
    try {
      const resp = await fetch(url, { credentials: 'same-origin' });
      if (!resp.ok) throw new Error(`Falha ao carregar dados (${resp.status})`);
      return await resp.json();
    } catch (e) {
      console.error('Erro ao buscar dados da evolução:', e);
      showEmpty('Não foi possível carregar os dados. Tente novamente mais tarde.');
      return null;
    }
  }

  function buildChart(ctx, payload) {
    const { categories, series } = payload;
    const patrimonio = (series.find((s) => s.name === 'Patrimônio')?.data || []).map(Number);
    const evolucao = (series.find((s) => s.name === 'Evolução')?.data || []).map(Number);

    const allZeros = patrimonio.every((v) => Number(v) === 0) && evolucao.every((v) => Number(v) === 0);
    if (!categories.length || allZeros) {
      showEmpty('Nenhum dado encontrado para o período escolhido.');
      return;
    }

    hideEmpty();

    const data = {
      labels: categories,
      datasets: [
        {
          type: 'bar',
          label: 'Patrimônio',
          data: patrimonio,
          backgroundColor: '#10b981',
          borderRadius: 6,
          borderSkipped: false,
          barPercentage: 0.7,
          categoryPercentage: 0.6,
        },
        {
          type: 'line',
          label: 'Evolução',
          data: evolucao,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59, 130, 246, 0.15)',
          tension: 0.35,
          yAxisID: 'y1',
          pointRadius: 3,
          pointHoverRadius: 4,
        },
      ],
    };

    const options = {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'top' },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              const v = ctx.parsed.y;
              return `${ctx.dataset.label}: ${formatCurrencyBRL(v)}`;
            },
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: {
            callback: (v) => formatCurrencyBRL(v),
          },
          grid: { color: 'rgba(2, 6, 23, 0.06)' },
        },
        y1: {
          beginAtZero: true,
          position: 'right',
          grid: { drawOnChartArea: false },
          ticks: {
            callback: (v) => formatCurrencyBRL(v),
          },
        },
        x: {
          grid: { display: false },
        },
      },
    };

    if (chartInstance) {
      chartInstance.destroy();
    }
    chartInstance = new Chart(ctx, { type: 'bar', data, options });
  }

  async function ensureChart(forceUpdate = false) {
    const canvas = $canvas();
    if (!canvas) return;

    const periodSelect = $periodSelect();
    const months = parseInt(periodSelect?.value || '12', 10) || 12;

    if (!forceUpdate && chartInstance && currentMonths === months) {
      try {
        chartInstance.resize();
      } catch (err) {
        console.warn('Falha ao redimensionar gráfico:', err);
      }
      return;
    }

    const payload = await fetchData(months);
    if (!payload) return;
    currentMonths = months;
    buildChart(canvas.getContext('2d'), payload);
  }

  document.addEventListener('DOMContentLoaded', () => {
    const tabBtn = document.getElementById('tab-evolucao');
    const periodSelect = $periodSelect();

    if (periodSelect) {
      periodSelect.addEventListener('change', () => ensureChart(true));
    }

    if (tabBtn) {
      tabBtn.addEventListener('shown.bs.tab', () => {
        ensureChart(true);
      });
    }

    setTimeout(() => ensureChart(true), 400);

    if (tabBtn && tabBtn.classList.contains('active')) {
      ensureChart(true);
    }
  });
})();
