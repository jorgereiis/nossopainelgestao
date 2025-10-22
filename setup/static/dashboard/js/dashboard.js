// FUNÇÕES PARA TRATAR EXIBIÇÃO DE INFORMAÇÕES NO DASHBOARD
const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
const csrfToken = csrfTokenMeta ? csrfTokenMeta.getAttribute('content') : '';
const fireAlert = (options) => {
    if (window.Swal && typeof window.Swal.fire === 'function') {
        return window.Swal.fire(options);
    }
    if (window.swal && typeof window.swal.fire === 'function') {
        return window.swal.fire(options);
    }
    if (options && (options.title || options.text || options.html)) {
        const message = options.title || options.text || options.html;
        window.alert(typeof message === 'string' ? message.replace(/<[^>]+>/g, '') : 'Alerta');
    } else {
        window.alert('Ação concluída');
    }
    return Promise.resolve();
};

const eyeIcon = document.getElementById("eye");
const values1_h1 = document.querySelectorAll(".values1_h1");
const values1_span = document.querySelectorAll(".values1_span");
const values2_h1 = document.querySelectorAll(".values2_h1");
const values2_span = document.querySelectorAll(".values2_span");
const values3_h1 = document.querySelectorAll(".values3_h1");
const values3_span = document.querySelectorAll(".values3_span");
const value_tela_span = document.querySelectorAll(".value_tela_span");
const eyeStorageKey = "dashboard-eye-state";


const initializeTableDropdowns = () => {
    const dropdowns = document.querySelectorAll('.table-actions-visible .dropdown');
    dropdowns.forEach((dropdown) => {
        if (dropdown.dataset.dropdownEnhanced === 'true') {
            return;
        }
        const toggle = dropdown.querySelector('[data-bs-toggle="dropdown"]');
        const menu = dropdown.querySelector('.dropdown-menu');
        if (!toggle || !menu) {
            return;
        }
        const resetPosition = () => {
            menu.style.marginTop = '';
            menu.style.marginBottom = '';
            menu.style.marginLeft = '';
        };
        toggle.addEventListener('shown.bs.dropdown', () => {
            requestAnimationFrame(() => {
                resetPosition();
                const menuRect = menu.getBoundingClientRect();
                const toggleRect = toggle.getBoundingClientRect();
                const viewportHeight = window.innerHeight;
                const viewportWidth = window.innerWidth;
                const spaceBelow = viewportHeight - menuRect.bottom;
                const spaceAbove = toggleRect.top;
                if (spaceBelow < 12 && spaceAbove > spaceBelow) {
                    const offset = menuRect.height - toggleRect.height;
                    menu.style.marginTop = `-${offset}px`;
                    menu.style.marginBottom = `${toggleRect.height}px`;
                }
                const menuRectAfter = menu.getBoundingClientRect();
                const spaceRight = viewportWidth - menuRectAfter.right;
                if (spaceRight < 0) {
                    menu.style.marginLeft = `${spaceRight - 8}px`;
                }
            });
        });
        toggle.addEventListener('hidden.bs.dropdown', resetPosition);
        dropdown.dataset.dropdownEnhanced = 'true';
    });
};

const allSensitiveNodes = [
    ...Array.from(values1_h1),
    ...Array.from(values1_span),
    ...Array.from(values2_h1),
    ...Array.from(values2_span),
    ...Array.from(values3_h1),
    ...Array.from(values3_span),
    ...Array.from(value_tela_span),
];
allSensitiveNodes.forEach((node) => {
    if (!node.dataset.value) {
        node.dataset.value = node.textContent.trim();
    }
});

function applyEyeState(masked) {
    const h1Value = masked ? "****" : null;
    const spanValue = masked ? "*" : null;

    values1_h1.forEach((node) => {
        node.style.height = masked ? "43px" : "auto";
        node.textContent = masked ? h1Value : (node.dataset.value || "");
    });
    values2_h1.forEach((node) => {
        node.style.height = masked ? "43px" : "auto";
        node.textContent = masked ? h1Value : (node.dataset.value || "");
    });
    values3_h1.forEach((node) => {
        node.style.height = masked ? "43px" : "auto";
        node.textContent = masked ? h1Value : (node.dataset.value || "");
    });

    values1_span.forEach((node) => {
        node.textContent = masked ? spanValue : (node.dataset.value || "");
    });
    values2_span.forEach((node) => {
        node.textContent = masked ? spanValue : (node.dataset.value || "");
    });
    values3_span.forEach((node) => {
        node.textContent = masked ? spanValue : (node.dataset.value || "");
    });
    value_tela_span.forEach((node) => {
        node.textContent = masked ? spanValue : (node.dataset.value || "");
    });
}

if (eyeIcon) {
    const savedState = localStorage.getItem(eyeStorageKey) || "visible";
    const masked = savedState === "hidden";
    applyEyeState(masked);
    eyeIcon.classList.toggle("bi-eye", !masked);
    eyeIcon.classList.toggle("bi-eye-slash", masked);

    eyeIcon.addEventListener("click", function () {
        const isCurrentlyVisible = eyeIcon.classList.contains("bi-eye");
        const shouldMask = isCurrentlyVisible;
        eyeIcon.classList.toggle("bi-eye", !shouldMask);
        eyeIcon.classList.toggle("bi-eye-slash", shouldMask);
        applyEyeState(shouldMask);
        localStorage.setItem(eyeStorageKey, shouldMask ? "hidden" : "visible");
    });
} else {
    applyEyeState(false);
}

// FUNÇÕES PARA O MODAL DE CANCELAMENTO DO CLIENTE

    function exibirModalConfirmacaoCancelamento(botao) {
        var cliente_id = $(botao).data('cliente');
        var cliente_nome = $(botao).data('nome');
        $('#confirm-cancelamento-modal #cancelamento-cliente-id').val(cliente_id);
        $('#confirm-cancelamento-modal #cancelamento-cliente-nome').text(cliente_nome);
        $('#confirm-cancelamento-modal').modal('show');

        // Ouve o envio do formulário
        $('#cancelamento-form').off('submit').on('submit', function (event) {
            event.preventDefault(); // Impede o envio padrão do formulário
            var $btn = $('.btn-confirmar-acao');
            $btn.prop('disabled', true);

            // Obtém o ID do cliente a ser cancelado
            var cliente_id = $('#cancelamento-cliente-id').val();

            // Faz a solicitação POST para a URL apropriada
            $.ajax({
                url: '/cancelar-cliente/' + cliente_id + '/',
                method: 'POST',
                beforeSend: function (xhr) {
                    if (csrfToken) {
                        xhr.setRequestHeader("X-CSRFToken", csrfToken);
                    }
                },
                success: function (response) {
                    $btn.prop('disabled', false);

                    // Verifica se a resposta contém a chave 'success_message_cancel'
                    if ('success_message_cancel' in response) {
                        // Fecha o modal e exibe mensagem de sucesso
                        $('#confirm-cancelamento-modal').modal('hide');

                        fireAlert({
                            icon: 'info',
                            title: 'Cancelado!',
                            html: '<span style="font-size: 20px">😮</span><br>' + response.success_message_cancel + '<br>Caso queira reativar, basta acessar seus clientes cancelados.',
                        }).then(function() {
                            // Usa novo gerenciador de tabela
                            if (window.dashboardTableManager) {
                                window.dashboardTableManager.refreshTable();
                            }
                        });
                    }

                    if ('error_message' in response) {
                        // Fecha o modal e exibe mensagem de sucesso
                        $('#confirm-cancelamento-modal').modal('hide');

                        fireAlert({
                            icon: 'error',
                            title: 'Oops...',
                            text: response.error_message,
                        });
                    }
                },
                error: function (response) {
                    $btn.prop('disabled', false);

                    // Fecha o modal e exibe mensagem de erro
                    $('#confirm-cancelamento-modal').modal('hide');

                    fireAlert({
                        icon: 'error',
                        title: 'Oops...',
                        text: 'Ocorreu um erro ao tentar cancelar o cliente.',
                    });
                }
            });
        });
    }

    $('#confirm-cancelamento-modal').on('click', '.btn-close, .btn-secondary', function () {
        $('#confirm-cancelamento-modal').modal('hide');
    });

// FUNÇÕES PARA MODAL DE CONFIRMAÇÃO DE PAGAMENTO DA MENSALIDADE DO CLIENTE

    function exibirModalConfirmacaoPagamento(botao) {
        var mensalidade_id = $(botao).data('mensalidade');
        var cliente_nome = $(botao).data('nome');
        $('#confirm-pagamento-modal #pagamento-mensalidade-id').val(mensalidade_id);
        $('#confirm-pagamento-modal #pagamento-cliente-nome').text(cliente_nome);
        $('#confirm-pagamento-modal').modal('show');

        // Ouve o envio do formulário
        $('#pagamento-form').off('submit').on('submit', function (event) {
            event.preventDefault(); // Impede o envio padrão do formulário
            var $btn = $('.btn-confirmar-acao');
            $btn.prop('disabled', true);

            // Obtém o ID do mensalidade a ser cancelado
            var mensalidade_id = $('#pagamento-mensalidade-id').val();

            // Faz a solicitação POST para a URL apropriada
            $.ajax({
                url: '/pagar-mensalidade/' + mensalidade_id + '/',
                method: 'POST',
                beforeSend: function (xhr) {
                    if (csrfToken) {
                        xhr.setRequestHeader("X-CSRFToken", csrfToken);
                    }
                },
                success: function (response) {
                    $btn.prop('disabled', false);

                    // Verifica se a resposta contém a chave 'success_message_invoice'
                    if ('success_message_invoice' in response) {
                        // Fecha o modal e exibe mensagem de sucesso
                        $('#confirm-pagamento-modal').modal('hide');

                        fireAlert({
                            icon: 'success',
                            title: 'Pago!',
                            html: '<span style="font-size: 20px">🤑</span><br>' + response.success_message_invoice + '<br>Consulte as mensalidades desse cliente para mais detalhes.',
                        }).then(function() {
                            // Usa novo gerenciador de tabela
                            if (window.dashboardTableManager) {
                                window.dashboardTableManager.refreshTable();
                            }
                        });
                    }

                    if ('error_message' in response) {
                        // Fecha o modal e exibe mensagem de sucesso
                        $('#confirm-pagamento-modal').modal('hide');

                        fireAlert({
                            icon: 'error',
                            title: 'Ação não permitida!',
                            html: 'Não é permitido pagar uma mensalidade com mais de 8 dias de atraso.<br>Cancele este cliente e o ative novamente, ou ajuste a data de vencimento.',
                        });
                    }
                },
                error: function (response) {
                    $btn.prop('disabled', false);

                    // Fecha o modal e exibe mensagem de erro
                    $('#confirm-pagamento-modal').modal('hide');

                    fireAlert({
                        icon: 'error',
                        title: 'Oops...',
                        text: 'Ocorreu um erro inesperado!',
                    });
                }
            });
        });
    }

    $('#confirm-pagamento-modal').on('click', '.btn-close, .btn-secondary', function () {
        $('#confirm-pagamento-modal').modal('hide');
    });

// FUNÇÃO PARA TRATAR EXIBIÇÃO DO MODAL DE INFORMAÇÕES DO CLIENTE

    function exibirModalDetalhes(botao) {
        const clienteId = botao.dataset.id;
        const clienteNome = botao.dataset.nome;
        const clientePlano = botao.dataset.plano;
        const clienteTelas = botao.dataset.telas;
        const clienteTelefone = botao.dataset.telefone;
        const clienteServidor = botao.dataset.servidor;
        const clienteFormaPgto = botao.dataset.forma_pgto;
        const clienteAplicativo = botao.dataset.aplicativo;
        const clienteDataAdesao = botao.dataset.data_adesao;
        const clienteDispositivo = botao.dataset.dispositivo;
        const clienteDataVencimento = botao.dataset.data_vencimento;
        const clienteContaAplicativo = botao.dataset.conta_aplicativo;

        let clienteUltimoPagamento = botao.dataset.ultimo_pagamento;
        if (clienteUltimoPagamento == 'None' || clienteUltimoPagamento == '' || clienteUltimoPagamento == null){
            clienteUltimoPagamento = '--';
        }
        
        let clienteIndicadoPor = botao.dataset.indicado_por;
        if (clienteIndicadoPor == 'None' || clienteIndicadoPor == '' || clienteIndicadoPor == null){
            clienteIndicadoPor = '--';
        }
        
        let clienteNotas = botao.dataset.notas;
        if (clienteNotas == 'None' || clienteNotas == '' || clienteNotas == null){
            clienteNotas = '--';
        }
        
        const table = document.querySelector("#info-cliente-table");

        document.getElementById('info-cliente-id').textContent = clienteId;
        document.getElementById('info-cliente-tela').textContent = clienteTelas;
        document.getElementById('info-cliente-nome').textContent = clienteNome;
        document.getElementById('info-cliente-notas').textContent =  clienteNotas;
        document.getElementById('info-cliente-plano').textContent =  clientePlano;
        document.getElementById('info-cliente-servidor').textContent =  clienteServidor;
        document.getElementById('info-cliente-forma_pgto').textContent =  clienteFormaPgto;
        document.getElementById('info-cliente-aplicativo').textContent =  clienteAplicativo;
        document.getElementById('info-cliente-dispositivo').textContent =  clienteDispositivo;
        document.getElementById('info-cliente-indicado_por').textContent =  clienteIndicadoPor;
        document.getElementById('info-cliente-ultimo_pgto').textContent =  clienteUltimoPagamento;
        document.getElementById('info-cliente-data_vencimento').textContent =  clienteDataVencimento;
        document.getElementById('info-cliente-telefone').textContent = clienteTelefone;
        document.getElementById('info-cliente-data_adesao').textContent = 'Cliente desde ' + clienteDataAdesao;

        const modal = new bootstrap.Modal(document.querySelector("#info-cliente-modal"));
        modal.show();

        // chamar a função para carregar e inserir as informações das contas dos aplicativos no modal
        carregarContasApps(clienteId);

        // chamar a função para carregar as quantidades das mensalidades para o Resumo das Cobranças
        carregarQuantidadeMensalidadesPagas(clienteId);

        // chamar a função para carregar os dados das indicações do cliente
        carregarIndicacoes(clienteId);
    }

    $('#info-cliente-modal').on('click', '.btn-close, .btn-secondary, #add-apps-info, #btn_exclude', function () {
      $('#info-cliente-modal').modal('hide');
    });

    function formatarTelefone(telefone) {
        const numeros = telefone.replace(/\D/g, '');
      
        if (numeros.length === 12) {
            return `(${numeros.substr(2, 2)}) ${numeros.substr(4, 4)}-${numeros.substr(8)}`;
        } else if (numeros.length === 13) {
            return `(${numeros.substr(2, 2)}) ${numeros.substr(4, 5)}-${numeros.substr(9)}`;
        } else {
            return telefone;
        }
    }

    function carregarQuantidadeMensalidadesPagas(clienteId) {
        $.ajax({
            url: '/qtds-mensalidades/',
            type: 'GET',
            data: { cliente_id: clienteId },
            success: function(data) {
                document.getElementById('qtd_mensalidades_pagas').textContent = data.qtd_mensalidades_pagas;
                document.getElementById('qtd_mensalidades_pendentes').textContent = data.qtd_mensalidades_pendentes;
                document.getElementById('qtd_mensalidades_canceladas').textContent = data.qtd_mensalidades_canceladas;

                var tbody = document.querySelector('#table-invoice tbody');
                tbody.innerHTML = ''; // Limpa o conteúdo atual da tabela

                data.mensalidades_totais.forEach(function(mensalidade) {
                    var tr = document.createElement('tr');
                    var tdId = document.createElement('td');
                    tdId.textContent = mensalidade.id;
                    tr.appendChild(tdId);
                    const hoje = new Date();
                    hoje.setHours(0, 0, 0, 0);
                    const dataVencimento = mensalidade.dt_vencimento.replace(/(\d{4})-(\d{2})-(\d{2})/, '$2/$3/$1');

                    function formatarData(data) {
                        var partes = data.split('-');
                        var dataFormatada = partes[2] + '/' + partes[1] + '/' + partes[0];
                        return dataFormatada;
                    }

                    var tdStatus = document.createElement('td');
                    if (mensalidade.pgto) {
                        tdStatus.innerHTML = '<span class="badge rounded-pill bg-success pill-invoice"><i class="bi bi-check-circle"></i>  Pago</span>';
                    } else if (mensalidade.cancelado) {
                        tdStatus.innerHTML = '<span class="badge rounded-pill bg-warning pill-invoice"><i class="bi bi-x-square"></i>  Cancelado</span>';
                    } else if (new Date(dataVencimento) < hoje) {
                        tdStatus.innerHTML = '<span class="badge rounded-pill bg-danger pill-invoice"><i class="bi bi-exclamation-triangle"></i>  Inadimplente</span>';
                    } else if (new Date(dataVencimento) >= hoje) {
                        tdStatus.innerHTML = '<span class="badge rounded-pill bg-secondary pill-invoice"><i class="bi bi-clock"></i>  Em aberto</span>';
                    }
                    tr.appendChild(tdStatus);

                    var tdVencimento = document.createElement('td');
                    tdVencimento.textContent = formatarData(mensalidade.dt_vencimento);
                    tr.appendChild(tdVencimento);

                    var tdValor = document.createElement('td');
                    tdValor.textContent = 'R$ ' + mensalidade.valor;
                    tr.appendChild(tdValor);

                    var tdPagamento = document.createElement('td');
                    tdPagamento.textContent = mensalidade.dt_pagamento ? formatarData(mensalidade.dt_pagamento) : '-';
                    tr.appendChild(tdPagamento);

                    tbody.appendChild(tr);
                });
            },
            error: function(error) {
                console.log(error);
            }
        });
    }

    function carregarIndicacoes(clienteId) {
        $.ajax({
            url: '/indicacoes/',
            type: 'GET',
            data: { cliente_id: clienteId },
            success: function(data) {
                console.log('Indicacoes: ', data.indicacoes);

                var tbody = document.querySelector('#table-indicados tbody');
                tbody.innerHTML = ''; // Limpa o conteúdo atual da tabela

                if (data.indicacoes.length === 0) {
                    // Se não há indicações, adiciona uma única linha com a mensagem
                    var tr = document.createElement('tr');
                    var tdMensagem = document.createElement('td');
                    tdMensagem.setAttribute('colspan', '4');
                    tdMensagem.textContent = 'Não há indicações desse usuário!';
                    tdMensagem.style.textAlign = 'center';
                    tdMensagem.style.verticalAlign = 'middle';
                    tr.appendChild(tdMensagem);
                    tbody.appendChild(tr);
                } else {
                    // Se houver indicações, adiciona as linhas com informações dos usuários indicados
                    data.indicacoes.forEach(function(indicado) {
                        var tr = document.createElement('tr');
                        var tdId = document.createElement('td');
                        tdId.textContent = indicado.id;
                        tr.appendChild(tdId);

                        const dataAdesao = indicado.data_adesao.replace(/(\d{4})-(\d{2})-(\d{2})/, '$2/$3/$1');
                        function formatarData(data) {
                            var partes = data.split('-');
                            var dataFormatada = partes[2] + '/' + partes[1] + '/' + partes[0];
                            return dataFormatada;
                        }

                        var tdStatus = document.createElement('td');
                        if (indicado.cancelado) {
                            tdStatus.innerHTML = '<span class="badge rounded-pill bg-warning pill-invoice">Cancelado</span>';
                        } else {
                            tdStatus.innerHTML = '<span class="badge rounded-pill bg-info pill-invoice">Ativo</span>';
                        }
                        tr.appendChild(tdStatus);

                        var tdNome = document.createElement('td');
                        tdNome.textContent = indicado.nome;
                        tr.appendChild(tdNome);

                        var tdAdesao = document.createElement('td');
                        tdAdesao.textContent = formatarData(indicado.data_adesao);
                        tr.appendChild(tdAdesao);

                        tbody.appendChild(tr);
                    });
                }
            },
            error: function(error) {
                console.log('Indicacoes: ', error);
            }
        });
    }

    function carregarContasApps(clienteId) {
    $.ajax({
        url: '/contas-apps/',
        type: 'GET',
        data: { cliente_id: clienteId },
        success: function(data) {
            var contas = data.conta_app; // Obtém os dados das contas de aplicativo

            var container = $('.dados-apps');
            var container2 = $('.texto-aqui');

            container.empty(); // Limpa o container antes de adicionar os novos elementos
            container2.empty();

            for (var i = 0; i < contas.length; i++) {
                var conta = contas[i];

                var card = $('<div class="card rounded py-4 px-5 d-flex flex-column align-items-center justify-content-center border" data-app-id="' + conta.id + '"></div>');
                var badge = $('<span class="badge rounded-pill bg-secondary mb-3">' + conta.nome_aplicativo + '</span>');
                var infoDiv = $('<div class="my-0 text-center"></div>');
                var btn_exclude = $('<div class="mt-2 mb-0 btn_exclude" style="cursor: pointer;" data-app-id="' + conta.id + '" onclick="exibirModalConfirmacaoExclusao(this)"><iconify-icon icon="feather:trash-2" style="color: #dc3545;" width="15" height="15"></iconify-icon></div>');
                var AppId = $('<input class="AppId" type="hidden" value="' + conta.id + '">');

                if (conta.device_id) {
                    infoDiv.append('<span>Device ID: </span><span>' + conta.device_id + '</span><br>');
                    if (conta.device_key) {
                        infoDiv.append('<span>Device Key: </span><span>' + conta.device_key + '</span>');
                    }
                }
                else if (conta.email) {
                    infoDiv.append('<span>E-mail: </span><span>' + conta.email + '</span><br>');
                    if (conta.device_key) {
                        infoDiv.append('<span>Device Key: </span><span>' + conta.device_key + '</span>');
                    }
                }

                card.append(badge);
                card.append(infoDiv);
                card.append(btn_exclude);
                card.append(AppId);
                container.append(card);
            }

            // Verificar se não há contas de aplicativo e exibir a mensagem correspondente
            if (contas.length === 0) {
                var message = $('<p class="text-muted text-center">Ainda não há contas de aplicativo para esse cliente.</p>');
                container2.append(message);
            }
        },
        error: function(error) {
            console.log(error);
        }
    });
}

// FUNÇÃO PARA EXIBIR MODAL DE CRIAÇÃO DE CONTA DO APLICATIVO DO CLIENTE
    // Controle global para saber se deve reabrir o modal de informações após criar conta do app
    var abrirInfoClienteAposCriarApp = false;
    var clienteIdCriadoApp = null; // Armazena o id do cliente usado no processo

    // Função para exibir o modal de criação de conta do app
    function exibirModalCriarApp(botao) {
        const clienteId = document.getElementById('info-cliente-id').textContent;
        clienteIdCriadoApp = clienteId;
        document.getElementById('app-info-cliente-id').value = clienteId;

        const form = document.querySelector("#create-app-info-form");
        form.action = "/cadastro-app-conta/";

        // Limpa os campos
        document.getElementById('device-id').value = '';
        document.getElementById('device-key').value = '';
        document.getElementById('app-email').value = '';
        form.classList.remove('was-validated');
        document.getElementById('create-app-error-message').textContent = '';

        // Fecha modal info e abre o de criação
        $('#info-cliente-modal').modal('hide');
        $('#create-app-info-modal').modal('show');

        // Dispara change para atualizar campos conforme app selecionado
        document.getElementById('app-nome').dispatchEvent(new Event('change'));
    }

    $(function () {
        // Lógica para exibir/esconder campos do formulário conforme o app selecionado
        const appNomeSelect = document.getElementById('app-nome');
        appNomeSelect.addEventListener('change', function () {
            const selectedOption = this.options[this.selectedIndex];
            const deviceHasMac = selectedOption.dataset.deviceHasMac === 'true';
            const appName = selectedOption.textContent.trim().toLowerCase();

            const divDeviceId = document.getElementById('div-device-id');
            const divDeviceKey = document.getElementById('div-device-key');
            const divAppEmail = document.getElementById('div-app-email');
            const avisoSemConta = document.getElementById('app-sem-conta');
            const btnSalvar = document.getElementById('btn-salvar-app');

            const deviceId = document.getElementById('device-id');
            const deviceKey = document.getElementById('device-key');
            const email = document.getElementById('app-email');

            // Resetar visibilidade e requisitos
            divDeviceId.style.display = 'none';
            divDeviceKey.style.display = 'none';
            divAppEmail.style.display = 'none';
            avisoSemConta.style.display = 'none';
            btnSalvar.disabled = false;

            deviceId.removeAttribute('required');
            deviceKey.removeAttribute('required');
            email.removeAttribute('required');

            if (deviceHasMac) {
                if (appName === 'clouddy') {
                    divDeviceKey.style.display = 'block';
                    divAppEmail.style.display = 'block';
                    deviceKey.setAttribute('required', 'required');
                    email.setAttribute('required', 'required');
                } else {
                    divDeviceId.style.display = 'block';
                    divDeviceKey.style.display = 'block';
                    deviceId.setAttribute('required', 'required');
                }
            } else {
                avisoSemConta.style.display = 'block';
                btnSalvar.disabled = true;
            }
        });

        // Validação do formulário antes de enviar
        const form = document.getElementById('create-app-info-form');
        form.addEventListener('submit', function (event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
                form.classList.add('was-validated');
            }
        }, false);

        // Validação de tamanho mínimo dos campos
        document.getElementById('device-id').addEventListener('input', function () {
            this.setCustomValidity(this.value.length >= 6 ? '' : 'O mínimo esperado é de 6 caracteres.');
        });
        document.getElementById('device-key').addEventListener('input', function () {
            this.setCustomValidity(this.value.length >= 5 ? '' : 'O mínimo esperado é de 5 caracteres.');
        });

        // Submissão AJAX/fetch para criar a conta do app
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            if (!form.checkValidity()) return;

            var $btn = $('.btn-confirmar-acao');
            $btn.prop('disabled', true);

            const url = form.action;
            const formData = new FormData(form);

            fetch(url, {
                method: 'POST',
                body: formData,
                credentials: 'same-origin',
                headers: csrfToken ? { 'X-CSRFToken': csrfToken } : {}
            })
                .then(response => {
                    if (response.status === 200) {
                        $btn.prop('disabled', false);

                        abrirInfoClienteAposCriarApp = true;
                        clienteIdCriadoApp = document.getElementById('app-info-cliente-id').value;
                        $('#create-app-info-modal').modal('hide');
                    } else {
                        // Exiba erro (pode adaptar conforme retorno do seu backend)
                        response.json().then(data => {
                            document.getElementById('create-app-error-message').textContent = data?.error || "Erro ao cadastrar conta do app.";
                        });
                    }
                })
                .catch(error => {
                    $btn.prop('disabled', false);

                    document.getElementById('create-app-error-message').textContent = "Erro ao cadastrar conta do app.";
                    console.error(error);
                });
        });

        // Ao fechar o modal de criação de app, recarrega cards e reabre modal info se houve criação
        $('#create-app-info-modal').on('hidden.bs.modal', function () {
            if (abrirInfoClienteAposCriarApp && clienteIdCriadoApp) {
                abrirInfoClienteAposCriarApp = false;
                carregarContasApps(clienteIdCriadoApp);
                setTimeout(function () {
                    $('#info-cliente-modal').modal('show');
                }, 250); // Pequeno delay garante atualização dos cards antes do modal abrir
            }
        });

        // Ao cancelar criação, volta para o modal info normalmente
        $('#create-app-info-modal').on('click', '.btn-close, .btn-secondary', function () {
            abrirInfoClienteAposCriarApp = false;
            $('#create-app-info-modal').modal('hide');
            $('#info-cliente-modal').modal('show');
        });
    });

// FUNÇÃO PARA EXIBIR O MODAL DE CONFIRMAÇÃO DE EXCLUSÃO DA CONTA DO APP DO CLIENTE
    var abrirInfoClienteAposExcluir = false;
    var ultimoAppIdExcluido = null; // Controla qual foi excluído

    $(function() {
      $('#confirm-delete-app-conta-form').on('submit', function(event) {
        event.preventDefault();
        var $btn = $('.btn-confirmar-acao');
        $btn.prop('disabled', true);

        var app_id = $('#app-conta-id').val();
        $.ajax({
          url: '/deletar-app-conta/' + app_id + '/',
          method: 'DELETE',
          beforeSend: function(xhr) {
            if (csrfToken) {
                xhr.setRequestHeader("X-CSRFToken", csrfToken);
            }
          },
          success: function(response) {
            $btn.prop('disabled', false);

            abrirInfoClienteAposExcluir = true;
            ultimoAppIdExcluido = app_id;
            $('#confirm-delete-app-conta-modal').modal('hide');
            // Não recarrega a página!
          },
          error: function(response) {
            $btn.prop('disabled', false);

            var mensagem_erro = response.responseJSON?.error_delete || "Erro ao excluir.";
            $('#delete-app-error-message').text(mensagem_erro);
          }
        });
      });

      // Fecha modal de confirmação e reabre o modal anterior se for cancelado
      $('#confirm-delete-app-conta-modal').on('click', '.btn-close, .btn-secondary', function() {
        abrirInfoClienteAposExcluir = false;
        $('#confirm-delete-app-conta-modal').modal('hide');
        $('#info-cliente-modal').modal('show');
      });

      // Após fechar totalmente o modal de confirmação, reabre o info e remove o card excluído
      $('#confirm-delete-app-conta-modal').on('hidden.bs.modal', function () {
        if (abrirInfoClienteAposExcluir) {
          abrirInfoClienteAposExcluir = false;
          // Remove o card visualmente
          if (ultimoAppIdExcluido) {
            $('.card[data-app-id="' + ultimoAppIdExcluido + '"]').remove();
            ultimoAppIdExcluido = null;
          }
          $('#info-cliente-modal').modal('show');
        }
      });
    });

    // Função para abrir o modal de confirmação
    function exibirModalConfirmacaoExclusao(botao) {
      var app_id = $(botao).data('app-id');
      $('#app-conta-id').val(app_id);
      $('#info-cliente-modal').modal('hide');
      $('#confirm-delete-app-conta-modal').modal('show');
    }

// FUNÇÃO PARA EXIBIR/OCULTAR OS CAMPOS DO FORMULÁRIO DE ENVIO DE MENSAGENS DO WHATSAPP
$(document).ready(function () {
    // Ocultar os campos do formulário
    $('#form-envio').hide();
    $('#imagem').hide();
    $('#mensagem').hide();
    $('#telefones').hide();
    $('#console').hide();
    // Ocultar as labels
    $('label[for="imagem"]').hide();
    $('label[for="mensagem"]').hide();
    $('label[for="telefones"]').hide();
    // Alterar as classes de mb-3 para mb-0
    $('#options').removeClass('mb-3').addClass('mb-0');
    $('#div-imagem').removeClass('mb-3').addClass('mb-0');
    $('#div-telefones').removeClass('mb-3').addClass('mb-0');
    // Desabilitar botão "Enviar"
    $('#botao-enviar').prop('disabled', true);

    // Ao mudar o valor do select com id "options"
    $('#options').change(function () {
      // Se o valor selecionado for igual a "avulso"
      if ($(this).val() === 'avulso') {
        // Mostrar os campos do formulário
        $('#form-envio').show();
        $('#imagem').show();
        $('#mensagem').show();
        $('#telefones').show();
        // Mostrar as labels
        $('label[for="imagem"]').show();
        $('label[for="mensagem"]').show();
        $('label[for="telefones"]').show();
        // Alterar as classes de mb-0 para mb-3
        $('#options').removeClass('mb-0').addClass('mb-3');
        $('#div-imagem').removeClass('mb-0').addClass('mb-3');
        $('#div-telefones').removeClass('mb-0').addClass('mb-3');
        // Habilitar o botão "Enviar"
        $('#botao-enviar').prop('disabled', false);

      } else if ($(this).val() === 'ativos' || $(this).val() === 'cancelados') {
        // Mostrar os campos do formulário
        $('#form-envio').show();
        $('#imagem').show();
        $('#mensagem').show();
        $('#telefones').hide();
        // Mostrar as labels
        $('label[for="imagem"]').show();
        $('label[for="mensagem"]').show();
        $('label[for="telefones"]').hide();
        // Alterar as classes de mb-0 para mb-3
        $('#options').removeClass('mb-0').addClass('mb-3');
        $('#div-imagem').removeClass('mb-0').addClass('mb-3');
        $('#div-telefones').removeClass('mb-3').addClass('mb-0');
        // Habilitar o botão "Enviar"
        $('#botao-enviar').prop('disabled', false);

      } else if ($(this).val() === '') {
        // Ocultar os campos do formulário
        $('#form-envio').hide();
        $('#imagem').hide();
        $('#mensagem').hide();
        $('#telefones').hide();
        // Ocultar as labels
        $('label[for="imagem"]').hide();
        $('label[for="mensagem"]').hide();
        $('label[for="telefones"]').hide();
        // Alterar as classe de mb-3 para mb-0
        $('#options').removeClass('mb-3').addClass('mb-0');
        $('#div-imagem').removeClass('mb-3').addClass('mb-0');
        $('#div-telefones').removeClass('mb-3').addClass('mb-0');
        // Desabilitar botão "Enviar"
        $('#botao-enviar').prop('disabled', true);
      }
    });
});

// FUNÇÃO PARA ENVIAR MENSAGENS DO WHATSAPP
document.addEventListener('DOMContentLoaded', function() {
  const form = document.querySelector('form');
  const telefonesInput = document.getElementById('telefones');
  const imagemInput = document.getElementById('imagem');
  const mensagemTextarea = document.getElementById('mensagem');
  const botaoEnviar = document.getElementById('botao-enviar');

  botaoEnviar.addEventListener('click', function() {
    const optionsSelect = document.getElementById('options');
    const tipoEnvio = optionsSelect.value;

    const telefones = telefonesInput.files[0];
    const imagem = imagemInput.files[0];
    const mensagem = mensagemTextarea.value;

    // Verificar se os campos não estão vazios
    if (!tipoEnvio || !mensagem) {
      console.log('Preencha os campos antes de enviar.');
      return;
    }

    const formData = new FormData();
    formData.append('options', tipoEnvio);
    formData.append('imagem', imagem);
    formData.append('mensagem', mensagem);
    formData.append('telefones', telefones);

    fetch('/enviar-mensagem/', {
      method: 'POST',
      headers: csrfToken ? { 'X-CSRFToken': csrfToken } : {},
      credentials: 'same-origin',
      body: formData
    })
    .then(function(response) {
      if (response.ok) {
        return response.json();
      } else {
        throw new Error('Erro na requisição');
      }
    })
    .then(function(data) {
      console.log(data);
      // Lógica para lidar com a resposta da requisição
    })
    .catch(function(error) {
      console.error(error);
      // Lógica para lidar com erros na requisição
    });
  });
});

// FUNÇÃO PARA EXIBIR O CONSOLE DE LOG DAS MENSAGENS ENVIADAS NO WHATSAPP

    $(document).ready(function() {
        function exibirConsole() {
        // Exibir o console
        $('#console').show();
        // Esconder elementos com as classes "parag-wpp", "logo-wpp" e "form-wpp"
        $('.parag-wpp, #logo-wpp, #form-wpp').hide();
      }

        // Função para manter a barra de rolagem na parte inferior
        function manterBarraRolagemAbaixo() {
            var consoleBody = $('#console-body');
            consoleBody.scrollTop(consoleBody[0].scrollHeight);
        }

      // Função para carregar o conteúdo do arquivo de texto
      function carregarConteudoArquivo() {
    
        $.ajax({
          url: '/obter-logs-wpp/',
          headers: Object.assign(
            { 'Content-Type': 'application/json' },
            csrfToken ? { 'X-CSRFToken': csrfToken } : {}
          ),
          method: 'POST', // Definindo o método da requisição como POST
          dataType: 'json',
          success: function(response) {
            // Verifica se o conteúdo foi retornado com sucesso
            if (response && response.logs) {
              // Substitui caracteres de quebra de linha por tags <br> para a quebra de linha na exibição
              var conteudoFormatado = response.logs.replace(/\n/g, "<br>");
              // Atualiza o conteúdo do console com os logs obtidos formatados
              $('#console-body').html(conteudoFormatado);

              // Chama a função para manter a barra de rolagem sempre no final
              manterBarraRolagemAbaixo();
            }
          },
          complete: function() {
            // Chama a função novamente após um intervalo de tempo (1 segundo neste exemplo)
            setTimeout(function() {
              carregarConteudoArquivo();
            }, 1000);
          }
        });
      }
    
      // Adiciona um evento de clique ao botão com ID "botao-enviar"
      $('#botao-enviar').click(function() {
        // Chama a função para carregar o conteúdo do arquivo quando o botão for clicado
        carregarConteudoArquivo();
        exibirConsole();
      });
    });

// FUNÇÃO PARA TRATAR CAMPOS DO FORMULÁRIO DE ENVIO DE MENSAGENS DO WHATSAPP
$(document).ready(function() {
  // Função para exibir os elementos e limpar o conteúdo dos campos
  function exibirElementos() {
    // Exibir elementos com as classes "parag-wpp", "logo-wpp" e "form-wpp"
    $('.parag-wpp, #logo-wpp, #form-wpp').show();
    // Esconder o console
    $('#console').hide();
    // Limpar o conteúdo do textarea com o ID "mensagem"
    $('#mensagem').val('');
    // Limpar o valor dos campos de arquivo
    $('#telefones').val('');
    $('#imagem').val('');
  }

  // Adiciona um evento de clique ao botão com ID "botao-voltar"
  $('#botao-voltar').click(function() {
    // Chama a função para exibir os elementos e limpar o conteúdo dos campos quando o botão for clicado
    exibirElementos();
  });
});

// FUNÇÃO PARA EXIBIR O MODAL DE EDIÇÃO DOS DADOS DO CLIENTE

    function exibirModalEdicao(botao) {
      const clienteId = botao.dataset.id;
      const clienteNome = botao.dataset.nome;
      const clientePlano = botao.dataset.plano;
      const clienteTelefone = botao.dataset.telefone;
      const clienteServidor = botao.dataset.servidor;
      const clienteFormaPgto = botao.dataset.forma_pgto;
      const clienteAplicativo = botao.dataset.aplicativo;
      const clienteDispositivo = botao.dataset.dispositivo;
      
      let clienteNotas = botao.dataset.notas;
      if (clienteNotas == 'None' || clienteNotas == null || clienteNotas == 'undefined'){
        clienteNotas = '';
      }
      
      let clienteIndicadoPor = botao.dataset.indicado_por;
      if (clienteIndicadoPor == 'None' || clienteIndicadoPor == null || clienteIndicadoPor == 'undefined'){
        clienteIndicadoPor = '';
      }
      let clienteDataVencimento = botao.dataset.data_vencimento;
      if (clienteDataVencimento == 'None' || clienteDataVencimento == null || clienteDataVencimento == 'undefined'){
        clienteDataVencimento = '';
      }
  
      const form = document.querySelector("#edit-cliente-form");
      form.action = `/editar-cliente/${clienteId}/`;
      form.querySelector("#edit-cliente-id").value = clienteId;
      form.querySelector("#edit-cliente-nome").value = clienteNome;
      form.querySelector("#edit-cliente-telefone").value = clienteTelefone;
      form.querySelector("#edit-cliente-indicado_por").value = clienteIndicadoPor;
      form.querySelector("#edit-cliente-servidor").value = clienteServidor;
      form.querySelector("#edit-cliente-forma_pgto").value = clienteFormaPgto;
      form.querySelector("#edit-cliente-plano").value = clientePlano;
      form.querySelector("#edit-cliente-dt_pgto").value = clienteDataVencimento;
      form.querySelector("#edit-cliente-dispositivo").value = clienteDispositivo;
      form.querySelector("#edit-cliente-aplicativo").value = clienteAplicativo;
      form.querySelector("#edit-cliente-notas").value = clienteNotas;
  
        $('#edit-cliente-form').off('submit').on('submit', function(event) {
            event.preventDefault();

            var $btn = $('.btn-confirmar-acao');
            $btn.prop('disabled', true);

            var form = this;
            var formData = new FormData(form);

            $.ajax({
                url: form.action,
                method: 'POST',
                data: formData,
                processData: false,
                contentType: false,
                beforeSend: function(xhr) {
                    xhr.setRequestHeader(
                        "X-CSRFToken",
                        form.querySelector('[name=csrfmiddlewaretoken]').value
                    );
                },
                success: function(response) {
                    $btn.prop('disabled', false);

                    if (response.success || response.success_message) {
                        $('#edit-cliente-modal').modal('hide');
                        fireAlert({
                            icon: 'success',
                            title: 'Cliente editado!',
                            html: response.success_message || "Os dados do cliente foram atualizados."
                        }).then(function() {
                            // Usa novo gerenciador de tabela
                            if (window.dashboardTableManager) {
                                window.dashboardTableManager.refreshTable();
                            }
                        });
                    } else if (response.error || response.error_message || response.error_message_edit) {
                        fireAlert({
                            icon: 'error',
                            title: 'Erro!',
                            html: response.error_message || response.error_message_edit || "Erro ao editar cliente."
                        });
                    }
                },
                error: function(xhr) {
                    $btn.prop('disabled', false);

                    fireAlert({
                        icon: 'error',
                        title: 'Oops...',
                        text: 'Erro ao editar cliente!'
                    });
                }
            });
        });
        const modal = new bootstrap.Modal(document.querySelector("#edit-cliente-modal"));
        modal.show();
    }

// TRATAMENTO DOS CAMPOS SELECT DA EDIÇÃO DO CLIENTE (LEGADO)
    const safeAttachInputMirror = (selector) => {
        const field = document.querySelector(selector);
        if (!field) {
            return;
        }
        field.addEventListener('input', (event) => {
            field.value = event.target.value;
        });
    };

    safeAttachInputMirror('input[name="indicado_por"]');
    safeAttachInputMirror('input[name="servidor"]');
    safeAttachInputMirror('input[name="forma_pgto"]');
    safeAttachInputMirror('input[name="plano"]');
    safeAttachInputMirror('input[name="dt_pgto"]');
    safeAttachInputMirror('input[name="dispositivo"]');
    safeAttachInputMirror('input[name="aplicativo"]');
    safeAttachInputMirror('input[name="cliente_id"]');

// NOTA: A busca de clientes agora é gerenciada por DashboardTableManager
// Ver: setup/static/dashboard/js/components/dashboard-table-manager.js

// Função para exibir o toast
    function showToast({ message, icon = "ℹ️", duration = 3000, iconColor = "#624bff", raw = false}) {
        const container = document.getElementById("toast-container");

        // Apaga todos os toasts anteriores
        container.innerHTML = "";

        const toast = document.createElement("div");
        toast.classList.add("toast-message");

        toast.innerHTML = raw
        ? `
            <span class="toast-icon">${icon}</span>
            <span>${message}</span>
            `
        : `
            <span class="toast-icon" style="color: ${iconColor};">${icon}</span>
            <span>${message}</span>
            `;

        container.appendChild(toast);

        // Fade-in
        setTimeout(() => toast.classList.add("show"), 50);

        // Fade-out e remoção
        setTimeout(() => {
            toast.classList.remove("show");
            setTimeout(() => {
                if (toast.parentNode) toast.remove();
            }, 400);
        }, duration);
    }

// NOTA: atualizarTabelaClientes() foi substituída por window.dashboardTableManager.refreshTable()
// A função antiga foi removida. Use o novo gerenciador:
//   window.dashboardTableManager.refreshTable()

let editClienteTelefoneIti = null;
const allowedTelefoneCountries = ["br", "us", "pt"];

function formatTelefoneInputValue(input, countryCode) {
    let numero = input.value.replace(/\D/g, '');

    if (countryCode === "br") {
        numero = numero.substring(0, 11); // 2 DDD + até 9 dígitos locais
        let formatted = '';

        if (numero.length >= 2) {
            formatted += '(' + numero.substring(0, 2) + ') ';

            const local = numero.substring(2);
            if (local.length === 9) {
                formatted += local.substring(0, 5) + '-' + local.substring(5);
            } else if (local.length >= 5) {
                formatted += local.substring(0, 4) + '-' + local.substring(4);
            } else {
                formatted += local;
            }
        } else {
            formatted += numero;
        }

        input.value = formatted;
        return;
    }

    if (countryCode === "us") {
        numero = numero.substring(0, 10);
        let formatted = '';
        if (numero.length >= 3) {
            formatted += '(' + numero.substring(0, 3) + ') ';
            if (numero.length >= 6) {
                formatted += numero.substring(3, 6) + '-' + numero.substring(6);
            } else if (numero.length > 3) {
                formatted += numero.substring(3);
            }
        } else {
            formatted += numero;
        }
        input.value = formatted;
        return;
    }

    if (countryCode === "pt") {
        numero = numero.substring(0, 9);
        let formatted = '';
        if (numero.length >= 3) {
            formatted += numero.substring(0, 3) + ' ';
            if (numero.length >= 6) {
                formatted += numero.substring(3, 6) + ' ' + numero.substring(6);
            } else if (numero.length > 3) {
                formatted += numero.substring(3);
            }
        } else {
            formatted += numero;
        }
        input.value = formatted;
    }
}

function getEditTelefoneInput() {
    return document.getElementById('edit-cliente-telefone');
}

function ensureEditTelefoneITI() {
    const telefoneInput = getEditTelefoneInput();
    if (!telefoneInput || typeof window.intlTelInput !== 'function') {
        return;
    }

    if (telefoneInput.dataset.itiInitialized === "true") {
        return;
    }

    editClienteTelefoneIti = window.intlTelInput(telefoneInput, {
        preferredCountries: ["br", "us", "pt"],
        initialCountry: "br",
        formatOnDisplay: false,
        nationalMode: true,
        utilsScript: "https://cdn.jsdelivr.net/npm/intl-tel-input@18.1.1/build/js/utils.js"
    });
    telefoneInput.dataset.itiInitialized = "true";

    telefoneInput.addEventListener('input', function () {
        if (!editClienteTelefoneIti) {
            return;
        }
        const countryCode = editClienteTelefoneIti.getSelectedCountryData()?.iso2;
        if (!countryCode || !allowedTelefoneCountries.includes(countryCode)) {
            return;
        }
        formatTelefoneInputValue(telefoneInput, countryCode);
    });

    const form = telefoneInput.closest('form');
    if (form && !form.dataset.telefoneSubmitHandlerAttached) {
        form.addEventListener('submit', function () {
            if (!editClienteTelefoneIti) {
                return;
            }
            const countryCode = editClienteTelefoneIti.getSelectedCountryData()?.iso2;
            if (!countryCode) {
                return;
            }
            if (countryCode === 'br') {
                let numero = telefoneInput.value.replace(/\D/g, '');
                if (numero.length >= 10) {
                    telefoneInput.value = '+55' + numero;
                }
            } else {
                telefoneInput.value = editClienteTelefoneIti.getNumber();
            }
        });
        form.dataset.telefoneSubmitHandlerAttached = "true";
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.debug('[Dashboard] DOMContentLoaded triggered for telefone initialization');
    try {
        ensureEditTelefoneITI();
    } catch (error) {
        console.error('[Dashboard] Failed to initialize telefone input on DOMContentLoaded', error);
    }
});

const editClienteModal = document.getElementById('edit-cliente-modal');
if (editClienteModal) {
    editClienteModal.addEventListener('shown.bs.modal', () => {
        console.debug('[Dashboard] edit-cliente-modal shown, ensuring telefone initialization');
        try {
            ensureEditTelefoneITI();
        } catch (error) {
            console.error('[Dashboard] Failed to initialize telefone input on modal show', error);
        }
    });
} else {
    console.debug('[Dashboard] edit-cliente-modal element not found during script evaluation');
}

// FUNÇÃO PARA TRATAR O FILTRO DE GRÁFICOS NA DASHBOARD
    const tipoGraficoSelect = document.getElementById("tipo_grafico");
    const filtroMes = document.getElementById("filtro-mes");
    const filtroAno = document.getElementById("filtro-ano");
    const selectMes = document.getElementById("mes");
    const selectAno = document.getElementById("ano");
    const graficoImg = document.getElementById("grafico");
    const graficoMensalBase = graficoImg ? graficoImg.dataset.urlMensal || "" : "";
    const graficoAnualBase = graficoImg ? graficoImg.dataset.urlAnual || "" : "";

    if (tipoGraficoSelect && filtroMes && filtroAno && selectMes && selectAno && graficoImg && graficoMensalBase && graficoAnualBase) {
        const atualizarGrafico = () => {
            const tipo = tipoGraficoSelect.value;
            if (tipo === "mensal") {
                const mes = selectMes.value;
                graficoImg.src = `${graficoMensalBase}?mes=${mes}`;
            } else {
                const ano = selectAno.value;
                graficoImg.src = `${graficoAnualBase}?ano=${ano}`;
            }
        };

        tipoGraficoSelect.addEventListener("change", () => {
            const tipo = tipoGraficoSelect.value;

            if (tipo === "mensal") {
                filtroMes.style.display = "inline-block";
                filtroAno.style.display = "none";
            } else {
                filtroMes.style.display = "none";
                filtroAno.style.display = "inline-block";
            }

            atualizarGrafico();
        });

        selectMes.addEventListener("change", atualizarGrafico);
        selectAno.addEventListener("change", atualizarGrafico);
    }
