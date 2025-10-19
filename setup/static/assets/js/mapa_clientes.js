/* Mapa de Clientes Ativos por Estado */
(function () {
  const API_URL = "/api/mapa-clientes/";
  const state = {
    features: null,
    summary: null,
  };
  const formatNumber = (value) =>
    new Intl.NumberFormat("pt-BR").format(value || 0);
  const debounce = (fn, wait = 250) => {
    let timeout;
    return function (...args) {
      clearTimeout(timeout);
      timeout = setTimeout(() => fn.apply(this, args), wait);
    };
  };
  document.addEventListener("DOMContentLoaded", () => {
    const container = document.getElementById("mapa-clientes");
    if (!container) {
      return;
    }
    loadMapData(container);
    window.addEventListener(
      "resize",
      debounce(() => {
        if (state.features) {
          renderMap(container);
        }
      }, 200)
    );
  });
  async function loadMapData(container) {
    setLoading(container, true);
    try {
      const response = await fetch(API_URL, { credentials: "same-origin" });
      if (!response.ok) {
        throw new Error("Erro ao obter dados do mapa.");
      }
      const data = await response.json();
      state.features = data.features || [];
      state.summary = data.summary || {};
      updateSummary(state.summary);
      renderMap(container);
    } catch (error) {
      console.error("[MapaClientes] Falha ao carregar dados:", error);
      showError(container, "Não foi possível carregar o mapa. Atualize a página.");
    } finally {
      setLoading(container, false);
    }
  }
  function setLoading(container, isLoading) {
    if (isLoading) {
      container.innerHTML = '<div class="mapa-clientes-loading">Carregando mapa...</div>';
    }
  }
  function showError(container, message) {
    container.innerHTML = `<div class="mapa-clientes-error">${message}</div>`;
  }
  function updateSummary(summary) {
    const summaryBox = document.getElementById("mapa-clientes-summary");
    if (!summaryBox) {
      return;
    }
    const totalSpan = summaryBox.querySelectorAll(".mapa-summary-chip strong")[0];
    const offSpan = summaryBox.querySelectorAll(".mapa-summary-chip strong")[1];
    if (totalSpan) {
      totalSpan.textContent = formatNumber(summary.total_geral || 0);
    }
    if (offSpan) {
      offSpan.textContent = formatNumber(summary.fora_pais || 0);
    }
  }
  function renderMap(container) {
    const features = state.features;
    if (!features || !features.length) {
      showError(container, "Nenhum cliente com UF cadastrado até o momento.");
      return;
    }
    container.innerHTML = "";
    const width = container.clientWidth || 620;
    const height = container.clientHeight || 380;
    const featureCollection = {
      type: "FeatureCollection",
      features,
    };
    const svg = d3
      .select(container)
      .append("svg")
      .attr("class", "mapa-clientes-svg")
      .attr("viewBox", `0 0 ${width} ${height}`)
      .attr("preserveAspectRatio", "xMidYMid meet");
    const projection = d3.geoMercator().center([-55, -15]);
    projection.fitSize([width, height], featureCollection);
    const geoPath = d3.geoPath(projection);
    const maxClientes =
      d3.max(features, (d) => d.properties.clientes) || 0;
    const colorScale = d3
      .scaleLinear()
      .domain([0, maxClientes || 1])
      .range(["#edeaff", "#624bff"]);
    const tooltip = d3
      .select(container)
      .append("div")
      .attr("class", "mapa-clientes-tooltip");
    svg
      .append("g")
      .selectAll("path")
      .data(features)
      .join("path")
      .attr("d", geoPath)
      .attr("fill", (d) =>
        d.properties.clientes ? colorScale(d.properties.clientes) : "#f3f1ff"
      )
      .on("mouseenter", function (event, d) {
        highlightState(this, tooltip, event, d, container);
      })
      .on("mousemove", function (event) {
        moveTooltip(event, container, tooltip);
      })
      .on("mouseleave", function () {
        resetState(this, tooltip);
      });
  }
  function highlightState(element, tooltip, event, feature, container) {
    const selection = d3.select(element);
    selection.raise().classed("is-hover", true);
    tooltip
      .style("opacity", 1)
      .html(buildTooltipContent(feature.properties || {}));
    moveTooltip(event, container, tooltip);
  }
  function resetState(element, tooltip) {
    d3.select(element).classed("is-hover", false);
    tooltip.style("opacity", 0);
  }
  function moveTooltip(event, container, tooltip) {
    const [x, y] = d3.pointer(event, container);
    const tooltipEl = tooltip.node();
    if (!tooltipEl) {
      return;
    }
    const tooltipWidth = tooltipEl.offsetWidth || 160;
    const tooltipHeight = tooltipEl.offsetHeight || 80;
    let left = x + 18;
    let top = y - tooltipHeight - 12;
    const boundsWidth = container.clientWidth || tooltipWidth;
    const boundsHeight = container.clientHeight || tooltipHeight;
    if (left + tooltipWidth > boundsWidth - 12) {
      left = boundsWidth - tooltipWidth - 12;
    }
    if (left < 12) {
      left = 12;
    }
    if (top < 12) {
      top = y + 20;
      if (top + tooltipHeight > boundsHeight - 12) {
        top = boundsHeight - tooltipHeight - 12;
      }
    }
    tooltip.style("left", `${left}px`).style("top", `${top}px`);
  }
  function buildTooltipContent(props) {
    const nome = props.name || props.sigla || "Estado";
    const clientes = formatNumber(props.clientes || 0);
    const porcentagemValor = Number(props.porcentagem || 0);
    const porcentagem = `${porcentagemValor.toFixed(1)}%`;
    return `
      <strong>${nome}</strong>
      <span>Clientes ativos: <strong>${clientes}</strong></span>
      <span>Participação: ${porcentagem}</span>
    `;
  }
})();