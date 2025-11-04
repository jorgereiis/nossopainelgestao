// FUNÇÕES PARA TRATAR EXIBIÇÃO DE INFORMAÇÕES NO DASHBOARD
// CSRF Token - usa a versão global se já existir, senão cria uma nova
if (typeof window.csrfToken === 'undefined') {
    var csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
    window.csrfToken = csrfTokenMeta ? csrfTokenMeta.getAttribute('content') : '';
}
var csrfToken = window.csrfToken;

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
    console.log('[Dashboard] Inicializando dropdowns da tabela');

    const dropdowns = document.querySelectorAll('.table-actions-visible .table-dropdown-actions');

    dropdowns.forEach((dropdown) => {
        // Evita reinicializar
        if (dropdown.dataset.initialized === 'true') {
            return;
        }

        const button = dropdown.querySelector('[data-bs-toggle="dropdown"]');
        const menu = dropdown.querySelector('.dropdown-menu');

        if (!button || !menu) {
            return;
        }

        // Função para aplicar position: fixed e calcular posição
        const applyFixedPosition = () => {
            const buttonRect = button.getBoundingClientRect();
            const menuRect = menu.getBoundingClientRect();
            const viewportWidth = window.innerWidth;
            const viewportHeight = window.innerHeight;

            // Aplica position: fixed
            menu.style.position = 'fixed';
            menu.style.margin = '0';

            // Posição vertical: abaixo do botão por padrão
            let top = buttonRect.bottom + 4;

            // Se não couber abaixo, posiciona acima
            if (top + menuRect.height > viewportHeight - 10 && buttonRect.top > menuRect.height) {
                top = buttonRect.top - menuRect.height - 4;
            }

            // Posição horizontal: alinha à direita do botão (dropdown-menu-end)
            let left = buttonRect.right - menuRect.width;

            // Ajusta se sair da tela pela esquerda
            if (left < 10) {
                left = 10;
            }

            // Ajusta se sair da tela pela direita
            if (left + menuRect.width > viewportWidth - 10) {
                left = viewportWidth - menuRect.width - 10;
            }

            // Aplica as posições
            menu.style.top = `${top}px`;
            menu.style.left = `${left}px`;
            menu.style.right = 'auto';
            menu.style.bottom = 'auto';
            menu.style.transform = 'none';
        };

        // Função para resetar posição ao fechar
        const resetPosition = () => {
            menu.style.position = '';
            menu.style.top = '';
            menu.style.left = '';
            menu.style.right = '';
            menu.style.bottom = '';
            menu.style.transform = '';
            menu.style.margin = '';
        };

        // Quando o dropdown abre (DEPOIS que o Bootstrap terminou)
        button.addEventListener('shown.bs.dropdown', () => {
            requestAnimationFrame(applyFixedPosition);
        });

        // Quando o dropdown fecha
        button.addEventListener('hidden.bs.dropdown', resetPosition);

        // Atualiza posição ao rolar ou redimensionar (apenas se aberto)
        let scrollTimeout;
        const handleScroll = () => {
            if (button.getAttribute('aria-expanded') === 'true') {
                clearTimeout(scrollTimeout);
                scrollTimeout = setTimeout(() => {
                    requestAnimationFrame(applyFixedPosition);
                }, 10);
            }
        };

        window.addEventListener('scroll', handleScroll, true);
        window.addEventListener('resize', handleScroll);

        dropdown.dataset.initialized = 'true';
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

// NOTA: Funções relacionadas ao modal de informações do cliente (exibirModalDetalhes, carregarContasApps,
// carregarQuantidadeMensalidadesPagas, carregarIndicacoes, exibirModalCriarApp, exibirModalConfirmacaoExclusao)
// foram movidas para setup/static/assets/js/modal_info_clients.js para evitar duplicação

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

// NOTA: window.showToast é agora carregado globalmente via toast-manager.js

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

// ----------------------
// EXPORTAÇÕES GLOBAIS
// ----------------------
// Exporta funções para o escopo global para que possam ser chamadas via onclick no HTML
window.exibirModalEdicao = exibirModalEdicao;
window.exibirModalConfirmacaoPagamento = exibirModalConfirmacaoPagamento;
window.exibirModalConfirmacaoCancelamento = exibirModalConfirmacaoCancelamento;
window.fireAlert = fireAlert;
// window.showToast é carregado globalmente via toast-manager.js
window.initializeTableDropdowns = initializeTableDropdowns;
