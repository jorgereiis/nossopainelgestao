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
    // Criar tooltip no body para que possa sobrepor qualquer elemento
    let tooltip = d3.select("body").select(".mapa-clientes-tooltip");
    if (tooltip.empty()) {
      tooltip = d3
        .select("body")
        .append("div")
        .attr("class", "mapa-clientes-tooltip");
    }
    svg
      .append("g")
      .selectAll("path")
      .data(features)
      .join("path")
      .attr("d", geoPath)
      .attr("fill", (d) =>
        d.properties.clientes ? colorScale(d.properties.clientes) : "#f3f1ff"
      )
      .attr("class", (d) =>
        d.properties.clientes ? "mapa-estado-ativo" : "mapa-estado-inativo"
      )
      .style("cursor", (d) => d.properties.clientes ? "pointer" : "default")
      .on("mouseenter", function (event, d) {
        // Só ativar hover se houver clientes
        if (d.properties.clientes > 0) {
          highlightState(this, tooltip, event, d, container);
        }
      })
      .on("mousemove", function (event, d) {
        // Só mover tooltip se houver clientes
        if (d.properties.clientes > 0) {
          moveTooltip(event, container, tooltip);
        }
      })
      .on("mouseleave", function (event, d) {
        // Só resetar se houver clientes
        if (d.properties.clientes > 0) {
          resetState(this, tooltip);
        }
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
    const tooltipEl = tooltip.node();
    if (!tooltipEl) {
      return;
    }

    // Usar coordenadas da viewport (clientX/clientY para position: fixed)
    const mouseX = event.clientX;
    const mouseY = event.clientY;

    const tooltipWidth = tooltipEl.offsetWidth || 160;
    const tooltipHeight = tooltipEl.offsetHeight || 80;

    // Dimensões da janela do navegador
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    // Margem de segurança das bordas
    const margin = 12;
    const offset = 8; // Distância muito próxima do cursor

    // Posicionamento padrão: à direita e ligeiramente abaixo do cursor
    let left = mouseX + offset;
    let top = mouseY + offset;

    // Verificar se ultrapassa a borda direita da viewport
    if (left + tooltipWidth > viewportWidth - margin) {
      // Posicionar à esquerda do cursor
      left = mouseX - tooltipWidth - offset;
    }

    // Garantir que não ultrapasse a borda esquerda
    if (left < margin) {
      left = margin;
    }

    // Verificar se ultrapassa a borda inferior da viewport
    if (top + tooltipHeight > viewportHeight - margin) {
      // Posicionar acima do cursor
      top = mouseY - tooltipHeight - offset;
    }

    // Verificar se ultrapassa a borda superior
    if (top < margin) {
      // Forçar a ficar dentro da viewport
      top = margin;
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