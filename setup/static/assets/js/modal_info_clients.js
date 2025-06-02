// ----------------------
// MODAL DE INFORMAÇÕES
// ----------------------

function exibirModalDetalhes(botao) {
    // Dados do cliente vindos do botão/data-attributes
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

    // Atualiza campos no modal
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

    $('#info-cliente-modal').modal('show');

    // AJAX: carregar cards de contas do app, resumo e indicações
    carregarContasApps(clienteId);
    carregarQuantidadeMensalidadesPagas(clienteId);
    carregarIndicacoes(clienteId);
}

// Fecha modal de informações quando necessário
$('#info-cliente-modal').on('click', '.btn-close, .btn-secondary, #add-apps-info', function () {
    $('#info-cliente-modal').modal('hide');
});
window.exibirModalDetalhes = exibirModalDetalhes; 

// Carregar informações de quantidade de mensalidades pagas
function carregarQuantidadeMensalidadesPagas(clienteId) {
    $.ajax({
        url: '/qtds-mensalidades/',
        type: 'GET',
        data: { cliente_id: clienteId },
        success: function(data) {
            document.getElementById('qtd_mensalidades_pagas')?.textContent = data.qtd_mensalidades_pagas;
            document.getElementById('qtd_mensalidades_pendentes')?.textContent = data.qtd_mensalidades_pendentes;
            document.getElementById('qtd_mensalidades_canceladas')?.textContent = data.qtd_mensalidades_canceladas;

            var tbody = document.querySelector('#table-invoice tbody');
            tbody.innerHTML = '';

            // Função única para formatar datas
            function formatarData(data) {
                if (!data) return '-';
                var partes = data.split('-');
                if (partes.length !== 3) return data;
                return partes[2] + '/' + partes[1] + '/' + partes[0];
            }

            const hoje = new Date();
            hoje.setHours(0, 0, 0, 0);

            data.mensalidades_totais.forEach(function(mensalidade) {
                var tr = document.createElement('tr');

                // ID
                var tdId = document.createElement('td');
                tdId.textContent = mensalidade.id;
                tr.appendChild(tdId);

                // Status
                var tdStatus = document.createElement('td');
                var vencimentoJS = new Date(mensalidade.dt_vencimento);
                if (mensalidade.pgto) {
                    tdStatus.innerHTML = '<span class="badge rounded-pill bg-success pill-invoice"><i class="bi bi-check-circle"></i>  Pago</span>';
                } else if (mensalidade.cancelado) {
                    tdStatus.innerHTML = '<span class="badge rounded-pill bg-warning pill-invoice"><i class="bi bi-x-square"></i>  Cancelado</span>';
                } else if (vencimentoJS < hoje) {
                    tdStatus.innerHTML = '<span class="badge rounded-pill bg-danger pill-invoice"><i class="bi bi-exclamation-triangle"></i>  Inadimplente</span>';
                } else {
                    tdStatus.innerHTML = '<span class="badge rounded-pill bg-secondary pill-invoice"><i class="bi bi-clock"></i>  Em aberto</span>';
                }
                tr.appendChild(tdStatus);

                // Vencimento
                var tdVencimento = document.createElement('td');
                tdVencimento.textContent = formatarData(mensalidade.dt_vencimento);
                tr.appendChild(tdVencimento);

                // Valor
                var tdValor = document.createElement('td');
                tdValor.textContent = 'R$ ' + Number(mensalidade.valor).toLocaleString('pt-BR', { minimumFractionDigits: 2 });
                tr.appendChild(tdValor);

                // Pagamento
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

// Carregar informações de indicações do cliente
function carregarIndicacoes(clienteId) {
    $.ajax({
        url: '/indicacoes/',
        type: 'GET',
        data: { cliente_id: clienteId },
        success: function(data) {
            var tbody = document.querySelector('#table-indicados tbody');
            tbody.innerHTML = '';

            // Função única para formatação
            function formatarData(data) {
                if (!data) return '--';
                var partes = data.split('-');
                if (partes.length !== 3) return data;
                return partes[2] + '/' + partes[1] + '/' + partes[0];
            }

            // Garante array
            var indicacoes = Array.isArray(data.indicacoes) ? data.indicacoes : [];

            if (indicacoes.length === 0) {
                // Não há indicações
                var tr = document.createElement('tr');
                var tdMensagem = document.createElement('td');
                tdMensagem.setAttribute('colspan', '3');
                tdMensagem.textContent = 'Não há indicações desse usuário!';
                tdMensagem.style.textAlign = 'center';
                tdMensagem.style.verticalAlign = 'middle';
                tr.appendChild(tdMensagem);
                tbody.appendChild(tr);
            } else {
                indicacoes.forEach(function(indicado) {
                    var tr = document.createElement('tr');

                    var tdId = document.createElement('td');
                    tdId.textContent = indicado.id ?? '--';
                    tr.appendChild(tdId);

                    var tdNome = document.createElement('td');
                    tdNome.textContent = indicado.nome ?? '--';
                    tr.appendChild(tdNome);

                    var tdAdesao = document.createElement('td');
                    tdAdesao.textContent = formatarData(indicado.data_adesao);
                    tr.appendChild(tdAdesao);

                    tbody.appendChild(tr);
                });
            }
        },
        error: function(error) {
            // Exibe erro na tabela
            var tbody = document.querySelector('#table-indicados tbody');
            if (tbody) {
                tbody.innerHTML = '';
                var tr = document.createElement('tr');
                var tdErro = document.createElement('td');
                tdErro.setAttribute('colspan', '3');
                tdErro.textContent = 'Erro ao carregar indicações!';
                tdErro.style.textAlign = 'center';
                tdErro.style.color = 'red';
                tr.appendChild(tdErro);
                tbody.appendChild(tr);
            }
            console.log('Indicacoes: ', error);
        }
    });
}


// ----------------------
// CARDS CONTAS DE APP
// ----------------------

function carregarContasApps(clienteId) {
    $.ajax({
        url: '/contas-apps/',
        type: 'GET',
        data: { cliente_id: clienteId },
        success: function(data) {
            let container = $('.dados-apps');
            let container2 = $('.texto-aqui');
            container.empty();
            container2.empty();

            let contas = Array.isArray(data.conta_app) ? data.conta_app : [];

            if (contas.length === 0) {
                container2.append('<p class="text-muted text-center">Ainda não há contas de aplicativo para esse cliente.</p>');
                return;
            }

            contas.forEach(function(conta) {
                let card = $('<div class="card rounded py-4 px-5 d-flex flex-column align-items-center justify-content-center border mb-3" data-app-id="' + (conta.id ?? '') + '"></div>');
                let badge = $('<span class="badge rounded-pill bg-secondary mb-3">' + (conta.nome_aplicativo ?? '--') + '</span>');
                let infoDiv = $('<div class="my-0 text-center"></div>');
                let btn_exclude = $('<div class="mt-2 mb-0" style="cursor: pointer;" data-app-id="' + (conta.id ?? '') + '"><iconify-icon icon="feather:trash-2" style="color: #dc3545;" width="15" height="15"></iconify-icon></div>');
                btn_exclude.on('click', function() { exibirModalConfirmacaoExclusao(this); });

                // Device ID ou E-mail
                if (conta.device_id) {
                    infoDiv.append('<span>Device ID: </span><span>' + conta.device_id + '</span><br>');
                    if (conta.device_key && conta.device_key !== 'null' && String(conta.device_key).trim() !== "") {
                        infoDiv.append('<span>Device Key: </span><span>' + conta.device_key + '</span>');
                    }
                } else if (conta.email) {
                    infoDiv.append('<span>E-mail: </span><span>' + conta.email + '</span><br>');
                    if (conta.device_key && conta.device_key !== 'null' && String(conta.device_key).trim() !== "") {
                        infoDiv.append('<span>Device Key: </span><span>' + conta.device_key + '</span>');
                    }
                }

                card.append(badge, infoDiv, btn_exclude);
                container.append(card);
            });
        },
        error: function(error) {
            let container2 = $('.texto-aqui');
            container2.html('<p class="text-danger text-center">Erro ao carregar contas de aplicativo.</p>');
            console.log(error);
        }
    });
}


// ----------------------
// MODAL DE CRIAÇÃO DE APP
// ----------------------

function exibirModalCriarApp() {
    // Garante reset e limpeza dos campos/formulário antes de abrir
    const form = document.getElementById('create-app-info-form');
    form.reset();
    form.classList.remove('was-validated'); // Remove estilo de validação anterior

    // Limpa mensagens de erro se houver
    const erroDiv = document.getElementById('erro-criar-app');
    if (erroDiv) erroDiv.textContent = '';

    // Preenche campo oculto com o id do cliente
    const clienteId = document.getElementById('info-cliente-id').textContent;
    document.getElementById('app-info-cliente-id').value = clienteId;

    // Fecha o modal de informações antes de abrir o de criação
    $('#info-cliente-modal').modal('hide');
    $('#create-app-info-modal').modal('show');
    document.getElementById('app-nome').dispatchEvent(new Event('change'));
}

$(function () {
    // Submissão AJAX do cadastro do app
    $('#create-app-info-form').off('submit').on('submit', function (event) {
        event.preventDefault();
        var form = this;
        if (!form.checkValidity()) {
            event.stopPropagation();
            form.classList.add('was-validated');
            return;
        }
        var url = form.action;
        var formData = new FormData(form);
        var clienteId = $('#app-info-cliente-id').val();

        fetch(url, { method: 'POST', body: formData })
            .then(response => {
                if (response.status === 200) {
                    // Fecha o modal de criação
                    $('#create-app-info-modal').modal('hide');
                    // Quando o modal de criação terminar de fechar, atualiza contas e reabre info
                    $('#create-app-info-modal').one('hidden.bs.modal', function () {
                        carregarContasApps(clienteId);
                        $('#info-cliente-modal').modal('show');
                    });
                } else {
                    // Exiba erro (pode adaptar conforme retorno do seu backend)
                    response.json().then(data => {
                        if (data && data.error) {
                            $('#erro-criar-app').text(data.error);
                        }
                    });
                }
            })
            .catch(error => {
                $('#erro-criar-app').text("Erro ao cadastrar conta do app.");
                console.error(error);
            });
    });

    // Fecha o modal de criação e volta para info
    $('#create-app-info-modal').on('click', '.btn-close, .btn-secondary', function () {
        $('#create-app-info-modal').modal('hide');
        $('#info-cliente-modal').modal('show');
    });
});


// ----------------------
// MODAL DE CONFIRMAÇÃO DE EXCLUSÃO
// ----------------------

var abrirInfoClienteAposExcluir = false;
var ultimoAppIdExcluido = null;

$(function() {
    // Submissão AJAX para exclusão
    $('#confirm-delete-app-conta-form').off('submit').on('submit', function(event) {
        event.preventDefault();
        var app_id = $('#app-conta-id').val();
        $.ajax({
            url: '/deletar-app-conta/' + app_id + '/',
            method: 'DELETE',
            beforeSend: function(xhr) {
                xhr.setRequestHeader("X-CSRFToken", "{{ csrf_token }}");
            },
            success: function(response) {
                abrirInfoClienteAposExcluir = true;
                ultimoAppIdExcluido = app_id;
                $('#confirm-delete-app-conta-modal').modal('hide');
            },
            error: function(response) {
                var mensagem_erro = response.responseJSON?.error_delete || "Erro ao excluir.";
                $('#mensagem-erro').text(mensagem_erro);
            }
        });
    });

    // Ao cancelar exclusão, volta para o modal de info
    $('#confirm-delete-app-conta-modal').on('click', '.btn-close, .btn-secondary', function() {
        abrirInfoClienteAposExcluir = false;
        $('#confirm-delete-app-conta-modal').modal('hide');
        $('#info-cliente-modal').modal('show');
    });

    // Após fechar o modal de confirmação, recarrega as contas e reabre o info se exclusão foi confirmada
    $('#confirm-delete-app-conta-modal').on('hidden.bs.modal', function () {
        if (abrirInfoClienteAposExcluir) {
            abrirInfoClienteAposExcluir = false;
            var clienteId = document.getElementById('info-cliente-id').textContent;
            carregarContasApps(clienteId); // Recria a lista de cards no frontend
            $('#info-cliente-modal').modal('show');
            ultimoAppIdExcluido = null;
        }
        // Limpa mensagens de erro ao fechar modal
        $('#mensagem-erro').text('');
    });
});

// Função para exibir o modal de confirmação de exclusão
function exibirModalConfirmacaoExclusao(botao) {
    var app_id = $(botao).data('app-id');
    $('#app-conta-id').val(app_id);
    $('#info-cliente-modal').modal('hide');
    $('#confirm-delete-app-conta-modal').modal('show');
}
