/**
 * modal_atendimento.js
 * Lógica do modal "Registrar Atendimento" e histórico de atendimentos no modal de info do cliente.
 */

(function () {
    'use strict';

    // ── CSRF ──────────────────────────────────────────────────────────────────
    if (typeof window.csrfToken === 'undefined') {
        var csrfMeta = document.querySelector('meta[name="csrf-token"]');
        window.csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : '';
    }

    // ── ESTADO ────────────────────────────────────────────────────────────────
    var _clienteId = null;
    var _arquivosSelecionados = [];

    // ── ABRIR MODAL ───────────────────────────────────────────────────────────
    window.exibirModalAtendimento = function (botao) {
        _clienteId = botao.dataset.id;
        var nome   = botao.dataset.nome || '';

        // Preenche o nome do cliente no título
        var spanNome = document.getElementById('atend-cliente-nome');
        if (spanNome) spanNome.textContent = nome;

        // Guarda o id no hidden input
        var inputId = document.getElementById('atend-cliente-id');
        if (inputId) inputId.value = _clienteId;

        // Reseta o formulário
        _resetarModal();

        // Carrega categorias
        _carregarCategorias();

        // Abre o modal
        var modal = new bootstrap.Modal(document.getElementById('registrar-atendimento-modal'));
        modal.show();
    };

    // ── RESET ─────────────────────────────────────────────────────────────────
    function _resetarModal() {
        var form = document.getElementById('form-registrar-atendimento');
        if (form) form.reset();

        var selCategoria = document.getElementById('atend-categoria');
        if (selCategoria) {
            selCategoria.innerHTML = '<option value="">Selecione uma categoria...</option>';
        }

        var bolinha = document.getElementById('atend-categoria-cor');
        if (bolinha) bolinha.style.background = '#dee2e6';

        var selTipo = document.getElementById('atend-tipo');
        if (selTipo) {
            selTipo.innerHTML = '<option value="">Selecione uma categoria primeiro...</option>';
            selTipo.disabled = true;
        }

        var selStatus = document.getElementById('atend-status');
        if (selStatus) selStatus.value = '';

        var btnAddTipo = document.getElementById('btn-add-tipo');
        if (btnAddTipo) btnAddTipo.disabled = true;

        var errMsg = document.getElementById('atend-error-message');
        if (errMsg) errMsg.textContent = '';

        var preview = document.getElementById('atend-preview-imagens');
        if (preview) preview.innerHTML = '';

        var contador = document.getElementById('atend-detalhes-count');
        if (contador) contador.textContent = '0';

        _arquivosSelecionados = [];
    }

    // ── CARREGAR CATEGORIAS ───────────────────────────────────────────────────
    function _carregarCategorias() {
        fetch('/atendimento/categorias/', {
            headers: { 'X-CSRFToken': window.csrfToken }
        })
        .then(function (r) { return r.json(); })
        .then(function (categorias) {
            var sel = document.getElementById('atend-categoria');
            if (!sel) return;
            sel.innerHTML = '<option value="">Selecione uma categoria...</option>';
            categorias.forEach(function (cat) {
                var opt = document.createElement('option');
                opt.value = cat.id;
                opt.textContent = cat.nome;
                opt.dataset.cor = cat.cor || '#0dcaf0';
                sel.appendChild(opt);
            });
        })
        .catch(function () {
            _mostrarErro('Erro ao carregar categorias.');
        });
    }

    // Retorna #fff ou #000 dependendo da luminosidade da cor de fundo
    function _corTextoContraste(hex) {
        var r = parseInt(hex.slice(1, 3), 16);
        var g = parseInt(hex.slice(3, 5), 16);
        var b = parseInt(hex.slice(5, 7), 16);
        var luminancia = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
        return luminancia > 0.6 ? '#000000' : '#ffffff';
    }

    // ── CARREGAR TIPOS ────────────────────────────────────────────────────────
    function _carregarTipos(categoriaId) {
        var selTipo = document.getElementById('atend-tipo');
        var btnAddTipo = document.getElementById('btn-add-tipo');

        if (!categoriaId) {
            if (selTipo) {
                selTipo.innerHTML = '<option value="">Selecione uma categoria primeiro...</option>';
                selTipo.disabled = true;
            }
            if (btnAddTipo) btnAddTipo.disabled = true;
            return;
        }

        fetch('/atendimento/tipos/?categoria_id=' + encodeURIComponent(categoriaId), {
            headers: { 'X-CSRFToken': window.csrfToken }
        })
        .then(function (r) { return r.json(); })
        .then(function (tipos) {
            if (!selTipo) return;
            selTipo.innerHTML = '<option value="">Selecione um tipo...</option>';
            tipos.forEach(function (t) {
                var opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = t.nome;
                selTipo.appendChild(opt);
            });
            selTipo.disabled = false;
            if (btnAddTipo) btnAddTipo.disabled = false;
        })
        .catch(function () {
            _mostrarErro('Erro ao carregar tipos.');
        });
    }

    // ── EVENTOS DO FORM ───────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function () {

        // Mudança de categoria → recarrega tipos + atualiza bolinha de cor
        var selCategoria = document.getElementById('atend-categoria');
        if (selCategoria) {
            selCategoria.addEventListener('change', function () {
                _carregarTipos(this.value);
                var bolinha = document.getElementById('atend-categoria-cor');
                if (bolinha) {
                    var opt = this.options[this.selectedIndex];
                    bolinha.style.background = (opt && opt.dataset.cor) ? opt.dataset.cor : '#dee2e6';
                }
            });
        }

        // Contador de caracteres do textarea
        var textarea = document.getElementById('atend-detalhes');
        var contador = document.getElementById('atend-detalhes-count');
        if (textarea && contador) {
            textarea.addEventListener('input', function () {
                contador.textContent = this.value.length;
            });
        }

        // Preview de imagens
        var inputImagens = document.getElementById('atend-imagens');
        if (inputImagens) {
            inputImagens.addEventListener('change', function () {
                _tratarSelecaoImagens(this.files);
            });
        }

        // Submit do form
        var form = document.getElementById('form-registrar-atendimento');
        if (form) {
            form.addEventListener('submit', function (e) {
                e.preventDefault();
                _submeterAtendimento();
            });
        }

        // Botão "+" Categoria (superuser)
        var btnAddCategoria = document.getElementById('btn-add-categoria');
        if (btnAddCategoria) {
            btnAddCategoria.addEventListener('click', _quickAddCategoria);
        }

        // Botão "+" Tipo (superuser)
        var btnAddTipo = document.getElementById('btn-add-tipo');
        if (btnAddTipo) {
            btnAddTipo.addEventListener('click', _quickAddTipo);
        }

        // Limpar previews ao fechar o modal
        var modalEl = document.getElementById('registrar-atendimento-modal');
        if (modalEl) {
            modalEl.addEventListener('hidden.bs.modal', function () {
                _resetarModal();
            });
        }

        // Girar chevron do painel informativo
        var infoPanel = document.getElementById('atend-info-panel');
        var infoChevron = document.getElementById('atend-info-chevron');
        if (infoPanel && infoChevron) {
            infoPanel.addEventListener('show.bs.collapse', function () {
                infoChevron.style.transform = 'rotate(180deg)';
            });
            infoPanel.addEventListener('hide.bs.collapse', function () {
                infoChevron.style.transform = 'rotate(0deg)';
            });
        }
    });

    // ── PREVIEW DE IMAGENS ────────────────────────────────────────────────────
    function _tratarSelecaoImagens(files) {
        var MAX = 3;
        var preview = document.getElementById('atend-preview-imagens');
        var errMsg  = document.getElementById('atend-error-message');

        _arquivosSelecionados = [];
        if (preview) preview.innerHTML = '';
        if (errMsg) errMsg.textContent = '';

        var validos = Array.from(files).slice(0, MAX);
        if (files.length > MAX) {
            if (errMsg) errMsg.textContent = 'Máximo de ' + MAX + ' imagens. Apenas as primeiras ' + MAX + ' foram consideradas.';
        }

        validos.forEach(function (file) {
            if (file.size > 5 * 1024 * 1024) {
                if (errMsg) errMsg.textContent = 'A imagem "' + file.name + '" excede 5MB e foi ignorada.';
                return;
            }
            _arquivosSelecionados.push(file);

            var reader = new FileReader();
            reader.onload = function (e) {
                if (!preview) return;
                var wrapper = document.createElement('div');
                wrapper.style.cssText = 'position:relative;display:inline-block;';

                var img = document.createElement('img');
                img.src = e.target.result;
                img.style.cssText = 'width:72px;height:72px;object-fit:cover;border-radius:6px;border:1px solid #dee2e6;';
                img.title = file.name;

                var btnRemover = document.createElement('button');
                btnRemover.type = 'button';
                btnRemover.innerHTML = '&times;';
                btnRemover.style.cssText = 'position:absolute;top:-6px;right:-6px;width:18px;height:18px;border-radius:50%;border:none;background:#dc3545;color:#fff;font-size:12px;line-height:1;cursor:pointer;padding:0;display:flex;align-items:center;justify-content:center;';
                btnRemover.addEventListener('click', function () {
                    var idx = _arquivosSelecionados.indexOf(file);
                    if (idx > -1) _arquivosSelecionados.splice(idx, 1);
                    wrapper.remove();
                    if (errMsg) errMsg.textContent = '';
                });

                wrapper.appendChild(img);
                wrapper.appendChild(btnRemover);
                preview.appendChild(wrapper);
            };
            reader.readAsDataURL(file);
        });
    }

    // ── SUBMETER ATENDIMENTO ──────────────────────────────────────────────────
    function _submeterAtendimento() {
        var btnSubmit = document.getElementById('btn-registrar-atendimento');
        var errMsg    = document.getElementById('atend-error-message');

        if (errMsg) errMsg.textContent = '';

        var categoriaId = document.getElementById('atend-categoria') ? document.getElementById('atend-categoria').value : '';
        var tipoId      = document.getElementById('atend-tipo') ? document.getElementById('atend-tipo').value : '';
        var status      = document.getElementById('atend-status') ? document.getElementById('atend-status').value : '';
        var detalhes    = document.getElementById('atend-detalhes') ? document.getElementById('atend-detalhes').value.trim() : '';

        if (!categoriaId || !tipoId || !status || !detalhes) {
            if (errMsg) errMsg.textContent = 'Preencha todos os campos obrigatórios.';
            return;
        }

        if (btnSubmit) setButtonLoading(btnSubmit, true);

        var formData = new FormData();
        formData.append('csrfmiddlewaretoken', window.csrfToken);
        formData.append('cliente_id', _clienteId);
        formData.append('categoria_id', categoriaId);
        formData.append('tipo_id', tipoId);
        formData.append('status', status);
        formData.append('detalhes', detalhes);
        _arquivosSelecionados.forEach(function (f) {
            formData.append('imagens', f);
        });

        fetch('/registrar-atendimento/', {
            method: 'POST',
            body: formData,
            headers: { 'X-CSRFToken': window.csrfToken }
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success_message) {
                // Fecha o modal
                var modalEl = document.getElementById('registrar-atendimento-modal');
                var modal = bootstrap.Modal.getInstance(modalEl);
                if (modal) modal.hide();

                // Exibe alerta de sucesso
                if (typeof fireAlert === 'function') {
                    fireAlert({
                        icon: 'success',
                        title: 'Atendimento registrado!',
                        html: '<span style="font-size:22px;">📋</span><br><span class="text-muted">O atendimento foi registrado com sucesso e já está disponível no histórico do cliente.</span>',
                    });
                } else {
                    alert(data.success_message);
                }
            } else {
                var msg = data.error_message || data.error || 'Ocorreu um erro ao registrar o atendimento.';
                if (errMsg) errMsg.textContent = msg;
            }
        })
        .catch(function () {
            if (errMsg) errMsg.textContent = 'Erro de conexão. Tente novamente.';
        })
        .finally(function () {
            if (btnSubmit) setButtonLoading(btnSubmit, false);
        });
    }

    // ── QUICK ADD: CATEGORIA (superuser) ──────────────────────────────────────
    function _quickAddCategoria() {
        var nome = window.prompt('Nome da nova categoria:');
        if (!nome || !nome.trim()) return;
        var cor = window.prompt('Cor em hexadecimal (ex: #e74c3c):', '#0dcaf0');
        if (!cor) cor = '#0dcaf0';

        var formData = new FormData();
        formData.append('csrfmiddlewaretoken', window.csrfToken);
        formData.append('nome', nome.trim());
        formData.append('cor', cor.trim());

        fetch('/atendimento/criar-categoria/', {
            method: 'POST',
            body: formData,
            headers: { 'X-CSRFToken': window.csrfToken }
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                var sel = document.getElementById('atend-categoria');
                if (sel) {
                    var opt = document.createElement('option');
                    opt.value = data.id;
                    opt.textContent = data.nome;
                    opt.dataset.cor = data.cor || '#0dcaf0';
                    opt.selected = true;
                    sel.appendChild(opt);
                    sel.dispatchEvent(new Event('change'));
                }
                if (typeof fireAlert === 'function') {
                    fireAlert('success', data.created ? 'Categoria criada!' : 'Categoria já existe e foi selecionada.');
                }
            } else {
                alert(data.error || 'Erro ao criar categoria.');
            }
        })
        .catch(function () { alert('Erro de conexão.'); });
    }

    // ── QUICK ADD: TIPO (superuser) ───────────────────────────────────────────
    function _quickAddTipo() {
        var categoriaId = document.getElementById('atend-categoria') ? document.getElementById('atend-categoria').value : '';
        if (!categoriaId) { alert('Selecione uma categoria primeiro.'); return; }

        var nome = window.prompt('Nome do novo tipo:');
        if (!nome || !nome.trim()) return;

        var formData = new FormData();
        formData.append('csrfmiddlewaretoken', window.csrfToken);
        formData.append('nome', nome.trim());
        formData.append('categoria_id', categoriaId);

        fetch('/atendimento/criar-tipo/', {
            method: 'POST',
            body: formData,
            headers: { 'X-CSRFToken': window.csrfToken }
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                var sel = document.getElementById('atend-tipo');
                if (sel) {
                    var opt = document.createElement('option');
                    opt.value = data.id;
                    opt.textContent = data.nome;
                    opt.selected = true;
                    sel.appendChild(opt);
                }
                if (typeof fireAlert === 'function') {
                    fireAlert('success', data.created ? 'Tipo criado!' : 'Tipo já existe e foi selecionado.');
                }
            } else {
                alert(data.error || 'Erro ao criar tipo.');
            }
        })
        .catch(function () { alert('Erro de conexão.'); });
    }

    // ── HISTÓRICO DE ATENDIMENTOS (modal info cliente) ────────────────────────
    window.carregarHistoricoAtendimentos = function (clienteId) {
        var loading  = document.getElementById('historico-atendimentos-loading');
        var empty    = document.getElementById('historico-atendimentos-empty');
        var content  = document.getElementById('historico-atendimentos-content');
        var timeline = document.getElementById('timeline-atendimentos');

        if (!content) return;

        if (loading)  loading.style.display = 'block';
        if (empty)    empty.style.display = 'none';
        if (content)  content.style.display = 'none';
        if (timeline) timeline.innerHTML = '';

        fetch('/atendimento/historico/' + encodeURIComponent(clienteId) + '/', {
            headers: { 'X-CSRFToken': window.csrfToken }
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (loading) loading.style.display = 'none';

            if (!data.length) {
                if (empty) empty.style.display = 'block';
                return;
            }

            if (content)  content.style.display = 'block';

            data.forEach(function (a) {
                var imgs = a.imagens.map(function (url) {
                    return '<a href="' + url + '" target="_blank">'
                         + '<img src="' + url + '" style="width:56px;height:56px;object-fit:cover;border-radius:6px;border:1px solid #dee2e6;" class="me-1">'
                         + '</a>';
                }).join('');

                var item = document.createElement('div');
                item.className = 'timeline-item action-create';
                var statusBadge = a.status === 'resolvido'
                    ? '<span class="badge bg-success"><i class="bi bi-check-circle me-1"></i>Resolvido</span>'
                    : '<span class="badge bg-warning text-dark"><i class="bi bi-clock-history me-1"></i>Pendente</span>';

                var corCategoria = a.categoria_cor || '#0dcaf0';
                var corTexto = _corTextoContraste(corCategoria);

                item.innerHTML = [
                    '<div class="timeline-header">',
                    '  <div class="d-flex gap-1">',
                    '    <span class="badge" style="background:' + corCategoria + ';color:' + corTexto + ';">' + _esc(a.categoria) + '</span>',
                    '    <span class="badge bg-secondary">' + _esc(a.tipo) + '</span>',
                    '    ' + statusBadge,
                    '  </div>',
                    '  <span class="timeline-date">',
                    '    <i class="bi bi-clock me-1"></i>' + _esc(a.criado_em),
                    '  </span>',
                    '</div>',
                    '<div class="timeline-changes">',
                    '  <div class="timeline-change-item">',
                    '    <span class="timeline-campo">Registro:</span>',
                    '    <span style="white-space:pre-wrap;">' + _esc(a.detalhes) + '</span>',
                    '  </div>',
                    imgs ? '<div class="d-flex flex-wrap gap-1 mt-2">' + imgs + '</div>' : '',
                    '</div>',
                    '<small class="text-muted mt-1 d-block"><i class="bi bi-person me-1"></i>' + _esc(a.usuario) + '</small>',
                ].join('');

                if (timeline) timeline.appendChild(item);
            });
        })
        .catch(function () {
            if (loading) loading.style.display = 'none';
            if (content) {
                content.innerHTML = '<p class="text-danger small">Erro ao carregar atendimentos.</p>';
                content.style.display = 'block';
            }
        });
    };

    // Escapa HTML básico para evitar XSS ao montar HTML via JS
    function _esc(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ── ABA ATENDIMENTOS DO DASHBOARD ─────────────────────────────────────────

    // Estado da aba
    var _atendTabIniciada = false;
    var _atendSort        = 'criado_em';
    var _atendOrder       = 'desc';
    var _atendPerPage     = 10;

    // Carrega tabela via AJAX
    window._carregarTabelaAtendimentos = function (page, perPage) {
        page    = page    || 1;
        perPage = perPage || _atendPerPage;
        _atendPerPage = perPage;

        var container = document.getElementById('tabela-atendimentos-container');
        if (!container) return;

        var q          = (document.getElementById('atendSearchInput')     || {}).value || '';
        var status     = (document.getElementById('atendFiltroStatus')    || {}).value || '';
        var catId      = (document.getElementById('atendFiltroCategoria') || {}).value || '';
        var dataInicio = (document.getElementById('atendFiltroDataInicio') || {}).value || '';
        var dataFim    = (document.getElementById('atendFiltroDataFim')   || {}).value || '';

        if (typeof showToast === 'function') showToast('info', 'Buscando atendimentos...');

        var params = new URLSearchParams({
            q: q,
            status: status,
            categoria_id: catId,
            data_inicio: dataInicio,
            data_fim: dataFim,
            page: page,
            per_page: perPage,
            sort: _atendSort,
            order: _atendOrder,
        });

        fetch('/atendimento/dashboard/?' + params.toString(), {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(function (r) { return r.text(); })
        .then(function (html) {
            container.innerHTML = html;
            _atualizarAlertaPendentes();
            if (typeof showToast === 'function') showToast('success', 'Tabela atualizada!');
        })
        .catch(function () {
            if (typeof showToast === 'function') showToast('error', 'Erro ao carregar atendimentos!');
        });
    };

    // Inicializa a aba na primeira ativação
    function _inicializarAbaAtendimentos() {
        if (_atendTabIniciada) return;
        _atendTabIniciada = true;

        // Popula select de categoria do filtro
        fetch('/atendimento/categorias/', {
            headers: { 'X-CSRFToken': window.csrfToken }
        })
        .then(function (r) { return r.json(); })
        .then(function (cats) {
            var sel = document.getElementById('atendFiltroCategoria');
            if (!sel) return;
            cats.forEach(function (c) {
                var opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.nome;
                sel.appendChild(opt);
            });
        });

        // Debounce para busca por nome
        var searchTimer = null;
        var searchInput = document.getElementById('atendSearchInput');
        if (searchInput) {
            searchInput.addEventListener('input', function () {
                clearTimeout(searchTimer);
                searchTimer = setTimeout(function () {
                    window._carregarTabelaAtendimentos(1);
                }, 400);
            });
        }

        // Filtros de select e datas → recarregar imediatamente
        ['atendFiltroStatus', 'atendFiltroCategoria', 'atendFiltroDataInicio', 'atendFiltroDataFim'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) {
                el.addEventListener('change', function () {
                    window._carregarTabelaAtendimentos(1);
                });
            }
        });

        // Botão limpar filtros
        var btnLimpar = document.getElementById('btnLimparFiltrosAtend');
        if (btnLimpar) {
            btnLimpar.addEventListener('click', function () {
                var ids = ['atendFiltroStatus', 'atendFiltroCategoria', 'atendFiltroDataInicio', 'atendFiltroDataFim'];
                ids.forEach(function (id) {
                    var el = document.getElementById(id);
                    if (el) el.value = '';
                });
                var searchEl = document.getElementById('atendSearchInput');
                if (searchEl) searchEl.value = '';
                window._carregarTabelaAtendimentos(1);
            });
        }

        // Delegação de cliques de paginação
        var container = document.getElementById('tabela-atendimentos-container');
        if (container) {
            container.addEventListener('click', function (e) {
                var link = e.target.closest('.atend-page-link');
                if (!link) return;
                e.preventDefault();
                var pg = parseInt(link.dataset.page, 10);
                if (pg) window._carregarTabelaAtendimentos(pg);
            });

            // Ordenação por cabeçalhos
            container.addEventListener('click', function (e) {
                var th = e.target.closest('.sortable-atend');
                if (!th) return;
                var field = th.dataset.sortField;
                if (!field) return;
                if (_atendSort === field) {
                    _atendOrder = _atendOrder === 'asc' ? 'desc' : 'asc';
                } else {
                    _atendSort  = field;
                    _atendOrder = 'asc';
                }
                window._carregarTabelaAtendimentos(1);
            });
        }

        // Carrega a tabela pela primeira vez
        window._carregarTabelaAtendimentos(1);
    }

    // Lê o count de pendentes injetado pelo template e sincroniza alerta + badge da aba
    function _atualizarAlertaPendentes() {
        var span  = document.getElementById('atend-pendentes-total');
        var alert = document.getElementById('alert-atend-pendentes');
        var label = document.getElementById('atend-pendentes-count-label');
        var badge = document.getElementById('badge-atend-pendentes');
        if (!span) return;

        var count = parseInt(span.dataset.count, 10) || 0;

        // Alerta interno da aba
        if (alert) {
            if (count > 0) {
                if (label) label.textContent = count;
                alert.classList.remove('d-none');
            } else {
                alert.classList.add('d-none');
            }
        }

        // Badge na orelha da aba
        if (badge) {
            if (count > 0) {
                badge.textContent = count;
                badge.classList.remove('d-none');
            } else {
                badge.classList.add('d-none');
            }
        }
    }

    // ── VER ATENDIMENTO ───────────────────────────────────────────────────────
    window.verAtendimento = function (id) {
        fetch('/atendimento/ver/?id=' + encodeURIComponent(id), {
            headers: { 'X-CSRFToken': window.csrfToken }
        })
        .then(function (r) { return r.json(); })
        .then(function (d) {
            if (d.error) { alert(d.error); return; }

            // Categoria badge
            var catBadge = document.getElementById('ver-categoria-badge');
            if (catBadge) {
                var corCat   = d.categoria_cor || '#0dcaf0';
                var corTexto = _corTextoContraste(corCat);
                catBadge.style.background = corCat;
                catBadge.style.color      = corTexto;
                catBadge.textContent = d.categoria_nome;
            }

            // Tipo badge
            var tipoBadge = document.getElementById('ver-tipo-badge');
            if (tipoBadge) tipoBadge.textContent = d.tipo_nome;

            // Status badge
            var statusBadge = document.getElementById('ver-status-badge');
            if (statusBadge) {
                if (d.status === 'resolvido') {
                    statusBadge.className = 'badge bg-success fs-6';
                    statusBadge.textContent = 'Resolvido';
                } else {
                    statusBadge.className = 'badge bg-warning text-dark fs-6';
                    statusBadge.textContent = 'Pendente';
                }
            }

            var el = function (id) { return document.getElementById(id); };
            if (el('ver-cliente-nome')) el('ver-cliente-nome').textContent = d.cliente_nome;
            if (el('ver-data'))         el('ver-data').textContent         = d.criado_em;
            if (el('ver-usuario'))      el('ver-usuario').textContent      = d.registrado_por;
            if (el('ver-detalhes'))     el('ver-detalhes').textContent     = d.detalhes;

            // Info de resolução
            var resolucaoContainer = el('ver-resolucao-container');
            if (resolucaoContainer) {
                if (d.status === 'resolvido' && d.resolvido_em) {
                    if (el('ver-resolvido-em'))  el('ver-resolvido-em').textContent  = d.resolvido_em;
                    if (el('ver-resolvido-por')) el('ver-resolvido-por').textContent = d.resolvido_por || '—';
                    resolucaoContainer.style.display = 'block';
                } else {
                    resolucaoContainer.style.display = 'none';
                }
            }

            // Imagens
            var imgContainer = el('ver-imagens-container');
            var imgDiv       = el('ver-imagens');
            if (imgDiv) {
                imgDiv.innerHTML = '';
                if (d.imagens && d.imagens.length) {
                    d.imagens.forEach(function (url) {
                        var a   = document.createElement('a');
                        a.href  = url;
                        a.target = '_blank';
                        var img = document.createElement('img');
                        img.src = url;
                        img.style.cssText = 'width:80px;height:80px;object-fit:cover;border-radius:6px;border:1px solid #dee2e6;';
                        a.appendChild(img);
                        imgDiv.appendChild(a);
                    });
                    if (imgContainer) imgContainer.style.display = 'block';
                } else {
                    if (imgContainer) imgContainer.style.display = 'none';
                }
            }

            var modalEl = document.getElementById('modal-ver-atendimento');
            if (modalEl) {
                var m = bootstrap.Modal.getOrCreateInstance(modalEl);
                m.show();
            }
        })
        .catch(function () { alert('Erro ao carregar atendimento.'); });
    };

    // ── MARCAR COMO RESOLVIDO ─────────────────────────────────────────────────
    window.marcarAtendimentoResolvido = async function (id) {
        var confirmado;
        if (typeof showConfirm === 'function') {
            confirmado = await showConfirm(
                'Marcar como resolvido?',
                'Após marcar como resolvido, o atendimento não poderá mais ser editado.',
                {
                    icon: 'question',
                    confirmText: 'Sim, marcar como resolvido',
                    confirmColor: '#198754',
                    cancelText: 'Cancelar',
                }
            );
        } else {
            confirmado = window.confirm('Marcar este atendimento como resolvido?\nApós isso, ele não poderá ser editado.');
        }
        if (!confirmado) return;

        var formData = new FormData();
        formData.append('csrfmiddlewaretoken', window.csrfToken);
        formData.append('id', id);

        fetch('/atendimento/resolver/', {
            method: 'POST',
            body: formData,
            headers: { 'X-CSRFToken': window.csrfToken }
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success_message) {
                if (typeof showToast === 'function') showToast('success', data.success_message);
                if (_atendTabIniciada) window._carregarTabelaAtendimentos(1);
            } else {
                var msg = data.error_message || 'Ocorreu um erro.';
                if (typeof showToast === 'function') showToast('error', msg);
                else alert(msg);
            }
        })
        .catch(function () {
            if (typeof showToast === 'function') showToast('error', 'Erro de conexão. Tente novamente.');
        });
    };

    // ── EDITAR ATENDIMENTO ────────────────────────────────────────────────────
    window.editarAtendimento = function (id) {
        fetch('/atendimento/ver/?id=' + encodeURIComponent(id), {
            headers: { 'X-CSRFToken': window.csrfToken }
        })
        .then(function (r) { return r.json(); })
        .then(function (d) {
            if (d.error) { alert(d.error); return; }

            var el = function (id) { return document.getElementById(id); };

            // Preenche o hidden id
            if (el('atend-edit-id')) el('atend-edit-id').value = d.id;

            // Preenche status
            if (el('atend-edit-status')) el('atend-edit-status').value = d.status;

            // Preenche detalhes e contador
            if (el('atend-edit-detalhes')) {
                el('atend-edit-detalhes').value = d.detalhes;
                if (el('atend-edit-detalhes-count')) {
                    el('atend-edit-detalhes-count').textContent = d.detalhes.length;
                }
            }

            // Limpa erros
            if (el('atend-edit-error')) el('atend-edit-error').textContent = '';

            // Carrega categorias, depois seleciona a correta e carrega tipos
            _carregarCategoriasEditar(d.categoria_id, d.categoria_cor, d.tipo_id);

            var modalEl = document.getElementById('modal-editar-atendimento');
            if (modalEl) {
                var m = bootstrap.Modal.getOrCreateInstance(modalEl);
                m.show();
            }
        })
        .catch(function () { alert('Erro ao carregar atendimento para edição.'); });
    };

    function _carregarCategoriasEditar(selectedCatId, selectedCatCor, selectedTipoId) {
        fetch('/atendimento/categorias/', {
            headers: { 'X-CSRFToken': window.csrfToken }
        })
        .then(function (r) { return r.json(); })
        .then(function (cats) {
            var sel = document.getElementById('atend-edit-categoria');
            if (!sel) return;
            sel.innerHTML = '<option value="">Selecione uma categoria...</option>';
            cats.forEach(function (c) {
                var opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.nome;
                opt.dataset.cor = c.cor || '#0dcaf0';
                sel.appendChild(opt);
            });

            // Seleciona a categoria correta
            if (selectedCatId) {
                sel.value = selectedCatId;
                // Atualiza a bolinha de cor
                var bolinha = document.getElementById('atend-edit-categoria-cor');
                if (bolinha) {
                    bolinha.style.background = selectedCatCor || '#0dcaf0';
                }
                // Carrega os tipos dessa categoria
                _carregarTiposEditar(selectedCatId, selectedTipoId);
            }
        });
    }

    function _carregarTiposEditar(categoriaId, selectedTipoId) {
        var sel = document.getElementById('atend-edit-tipo');
        if (!sel) return;
        sel.innerHTML = '<option value="">Selecione um tipo...</option>';
        sel.disabled = true;

        if (!categoriaId) return;

        fetch('/atendimento/tipos/?categoria_id=' + encodeURIComponent(categoriaId), {
            headers: { 'X-CSRFToken': window.csrfToken }
        })
        .then(function (r) { return r.json(); })
        .then(function (tipos) {
            sel.innerHTML = '<option value="">Selecione um tipo...</option>';
            tipos.forEach(function (t) {
                var opt = document.createElement('option');
                opt.value = t.id;
                opt.textContent = t.nome;
                sel.appendChild(opt);
            });
            sel.disabled = false;
            if (selectedTipoId) sel.value = selectedTipoId;
        });
    }

    // ── EVENTOS DA ABA E DO FORM EDITAR ───────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function () {

        // Ativa a aba ao primeiro clique em "Atendimentos"
        var tabBtn = document.getElementById('tab-atendimentos');
        if (tabBtn) {
            tabBtn.addEventListener('show.bs.tab', function () {
                _inicializarAbaAtendimentos();
            });
        }

        // Mudança de categoria no editar → recarrega tipos + bolinha
        var selEditCat = document.getElementById('atend-edit-categoria');
        if (selEditCat) {
            selEditCat.addEventListener('change', function () {
                var bolinha = document.getElementById('atend-edit-categoria-cor');
                if (bolinha) {
                    var opt = this.options[this.selectedIndex];
                    bolinha.style.background = (opt && opt.dataset.cor) ? opt.dataset.cor : '#dee2e6';
                }
                _carregarTiposEditar(this.value, null);
            });
        }

        // Contador de caracteres no textarea de edição
        var editTextarea  = document.getElementById('atend-edit-detalhes');
        var editContador  = document.getElementById('atend-edit-detalhes-count');
        if (editTextarea && editContador) {
            editTextarea.addEventListener('input', function () {
                editContador.textContent = this.value.length;
            });
        }

        // Submit do form editar
        var formEditar = document.getElementById('form-editar-atendimento');
        if (formEditar) {
            formEditar.addEventListener('submit', function (e) {
                e.preventDefault();
                _submeterEdicaoAtendimento();
            });
        }

        // Resetar bolinha ao fechar o modal editar
        var modalEditar = document.getElementById('modal-editar-atendimento');
        if (modalEditar) {
            modalEditar.addEventListener('hidden.bs.modal', function () {
                var bolinha = document.getElementById('atend-edit-categoria-cor');
                if (bolinha) bolinha.style.background = '#dee2e6';
                var errEl = document.getElementById('atend-edit-error');
                if (errEl) errEl.textContent = '';
            });
        }
    });

    function _submeterEdicaoAtendimento() {
        var btnSalvar = document.getElementById('btn-salvar-atendimento');
        var errMsg    = document.getElementById('atend-edit-error');

        if (errMsg) errMsg.textContent = '';

        var id          = (document.getElementById('atend-edit-id')        || {}).value || '';
        var categoriaId = (document.getElementById('atend-edit-categoria') || {}).value || '';
        var tipoId      = (document.getElementById('atend-edit-tipo')      || {}).value || '';
        var status      = (document.getElementById('atend-edit-status')    || {}).value || '';
        var detalhes    = ((document.getElementById('atend-edit-detalhes') || {}).value || '').trim();

        if (!id || !categoriaId || !tipoId || !status || !detalhes) {
            if (errMsg) errMsg.textContent = 'Preencha todos os campos obrigatórios.';
            return;
        }

        if (btnSalvar) setButtonLoading(btnSalvar, true);

        var formData = new FormData();
        formData.append('csrfmiddlewaretoken', window.csrfToken);
        formData.append('id', id);
        formData.append('categoria_id', categoriaId);
        formData.append('tipo_id', tipoId);
        formData.append('status', status);
        formData.append('detalhes', detalhes);

        fetch('/atendimento/editar/', {
            method: 'POST',
            body: formData,
            headers: { 'X-CSRFToken': window.csrfToken }
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success_message) {
                var modalEl = document.getElementById('modal-editar-atendimento');
                var modal = bootstrap.Modal.getInstance(modalEl);
                if (modal) modal.hide();

                if (typeof fireAlert === 'function') {
                    fireAlert('success', data.success_message);
                } else if (typeof Swal !== 'undefined') {
                    Swal.fire({ icon: 'success', title: data.success_message, timer: 2500, showConfirmButton: false });
                } else {
                    alert(data.success_message);
                }

                // Recarrega a tabela se a aba estiver ativa
                if (_atendTabIniciada) {
                    window._carregarTabelaAtendimentos(1);
                }
            } else {
                var msg = data.error_message || data.error || 'Ocorreu um erro ao salvar.';
                if (errMsg) errMsg.textContent = msg;
            }
        })
        .catch(function () {
            if (errMsg) errMsg.textContent = 'Erro de conexão. Tente novamente.';
        })
        .finally(function () {
            if (btnSalvar) setButtonLoading(btnSalvar, false);
        });
    }

})();
