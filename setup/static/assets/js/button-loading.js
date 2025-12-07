/**
 * Button Loading - Efeito de loading (bolinhas ondulares) para botões
 * Este script é carregado globalmente via scripts.html
 */

/**
 * Ativa/desativa efeito de loading em botão
 * @param {HTMLElement} btn - Elemento do botão
 * @param {boolean} loading - true para ativar loading, false para desativar
 * @param {string} originalHTML - HTML original do botão (para restaurar)
 */
function setButtonLoading(btn, loading, originalHTML) {
    if (!btn) return;

    if (loading) {
        btn.disabled = true;
        btn.dataset.originalHtml = btn.innerHTML;
        btn.innerHTML = '<span class="loading-dots"><span></span><span></span><span></span></span>';
    } else {
        btn.disabled = false;
        btn.innerHTML = originalHTML || btn.dataset.originalHtml || 'Salvar';
    }
}

// Expor globalmente
window.setButtonLoading = setButtonLoading;
