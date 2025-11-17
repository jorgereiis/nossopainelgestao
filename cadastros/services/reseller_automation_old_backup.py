"""
Serviço de automação para painéis reseller de aplicativos IPTV.

Este módulo fornece:
- Classe base ResellerAutomationService para automação genérica
- Implementação específica DreamTVAutomation para DreamTV Reseller
- Login automático com reCAPTCHA via CapSolver (extension/API)
- Reutilização de sessão (cookies + localStorage)
- Migração DNS automatizada via Playwright

Arquitetura:
    ResellerAutomationService (base abstrata)
        └── DreamTVAutomation (implementação para DreamTV)
        └── NetFloxAutomation (futura)
        └── MaxStreamAutomation (futura)

Uso:
    from cadastros.services.reseller_automation import DreamTVAutomation

    service = DreamTVAutomation(user=request.user, aplicativo=aplicativo_obj)

    # Login automático (apenas primeira vez ou se sessão expirou)
    if not service.verificar_sessao_valida():
        service.fazer_login_automatico()

    # Executar migração DNS
    service.executar_migracao(tarefa_id=123)
"""

import base64
import json
import os
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    Locator,
    sync_playwright,
)

from cadastros.models import (
    Aplicativo,
    ContaReseller,
    TarefaMigracaoDNS,
    DispositivoMigracaoDNS,
    ConfiguracaoAutomacao,
)
from cadastros.utils import decrypt_password
from cadastros.services.logging_config import get_reseller_logger
from cadastros.services.capsolver_integration import (
    CapSolverException,
    CapSolverService,
)


class ResellerAutomationService(ABC):
    """
    Classe base abstrata para automação de painéis reseller.

    Fornece métodos comuns de login, gerenciamento de sessão e estrutura
    para implementações específicas de cada plataforma.

    Attributes:
        user: Usuário Django proprietário da conta
        aplicativo: Aplicativo/plataforma do reseller
        conta: Instância de ContaReseller com credenciais
        logger: Logger configurado para automação reseller
    """

    def __init__(self, user: User, aplicativo: Aplicativo):
        """
        Inicializa o serviço de automação.

        Args:
            user: Usuário proprietário da conta reseller
            aplicativo: Aplicativo/plataforma a ser automatizado

        Raises:
            ValueError: Se conta reseller não for encontrada
        """
        self.user = user
        self.aplicativo = aplicativo
        self.conta = self._obter_conta()
        self.logger = get_reseller_logger()

    def _obter_conta(self) -> ContaReseller:
        """
        Obtém a conta reseller do usuário para o aplicativo.

        Returns:
            ContaReseller: Conta encontrada

        Raises:
            ValueError: Se conta não existir
        """
        try:
            return ContaReseller.objects.get(
                usuario=self.user,
                aplicativo=self.aplicativo
            )
        except ContaReseller.DoesNotExist:
            raise ValueError(
                f"Conta reseller não encontrada para usuário '{self.user.username}' "
                f"e aplicativo '{self.aplicativo.nome}'"
            )

    # ------------------------------------------------------------------
    # Utilitários CapSolver / Playwright
    # ------------------------------------------------------------------

    def _extrair_anchor_html(self, page: Page) -> Optional[str]:
        """Extrai o HTML completo do iframe anchor (checkbox) e codifica em Base64."""
        try:
            page.wait_for_timeout(1500)
            for frame in page.frames:
                if "google.com/recaptcha/api2/anchor" not in frame.url:
                    continue
                anchor_html = frame.content()
                if anchor_html and len(anchor_html) > 100:
                    encoded = base64.b64encode(anchor_html.encode("utf-8")).decode("utf-8")
                    self.logger.info(
                        f"[USER:{self.user.username}] ✓ HTML anchor extraído ({len(anchor_html)} chars)"
                    )
                    return encoded
            self.logger.warning(
                f"[USER:{self.user.username}] Iframe anchor não encontrado ou muito curto"
            )
            return None
        except Exception as exc:
            self.logger.error(
                f"[USER:{self.user.username}] Erro ao extrair anchor HTML: {str(exc)[:180]}"
            )
            return None

    def _build_playwright_proxy(self, proxy_url: Optional[str]) -> Optional[Dict[str, str]]:
        """Converte a string do proxy para o formato aceito pelo Playwright."""
        if not proxy_url:
            return None
        try:
            parsed = urlparse(proxy_url)
            if not (parsed.scheme and parsed.hostname and parsed.port):
                raise ValueError("Proxy inválido. Formato esperado: protocol://user:pass@host:port")
            proxy_dict: Dict[str, str] = {
                "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
            }
            if parsed.username:
                proxy_dict["username"] = parsed.username
            if parsed.password:
                proxy_dict["password"] = parsed.password
            self.logger.info(
                f"[USER:{self.user.username}] Proxy configurado no Playwright ({parsed.scheme})"
            )
            return proxy_dict
        except Exception as exc:
            self.logger.error(
                f"[USER:{self.user.username}] Proxy inválido para Playwright: {exc}"
            )
            return None

    def _format_cookies_for_capsolver(self, context) -> Optional[str]:
        """
        Serializa cookies do contexto para enviar ao CapSolver.
        Filtra apenas cookies relevantes para Google/reCAPTCHA para melhorar fingerprint matching.
        """
        try:
            all_cookies = context.cookies()

            # Filtrar apenas cookies de domínios Google/reCAPTCHA
            google_cookies = [
                cookie for cookie in all_cookies
                if any(domain in cookie.get('domain', '')
                       for domain in ['google.com', 'recaptcha.net', 'gstatic.com'])
            ]

            cookie_pairs = []
            for cookie in google_cookies:
                name = cookie.get("name")
                value = cookie.get("value")
                if name and value:
                    cookie_pairs.append(f"{name}={value}")

            result = "; ".join(cookie_pairs) if cookie_pairs else None

            if result:
                self.logger.debug(
                    f"[USER:{self.user.username}] Enviando {len(google_cookies)} cookies Google/reCAPTCHA para CapSolver"
                )

            return result
        except Exception as exc:
            self.logger.debug(
                f"[USER:{self.user.username}] Não foi possível coletar cookies para CapSolver: {exc}"
            )
            return None

    def _start_recaptcha_reload_capture(self, page: Page):
        """Registra listener de requests e captura a próxima chamada /recaptcha/api2/reload."""
        captured = {"raw": None}

        def handle_request(request):
            try:
                if captured["raw"]:
                    return
                if "google.com/recaptcha/api2/reload" not in request.url:
                    return
                info = {
                    "method": request.method,
                    "url": request.url,
                    "headers": dict(request.headers),
                    "postData": request.post_data if request.method == "POST" else None,
                }
                fetch_repr = f"""fetch("{info['url']}", {{
    method: "{info['method']}",
    headers: {json.dumps(info['headers'], indent=8)},
    body: {json.dumps(info['postData']) if info['postData'] else 'null'}
}})"""
                captured["raw"] = fetch_repr
                self.logger.info(
                    f"[USER:{self.user.username}] ✓ Requisição /reload capturada"
                )
            except Exception as exc:
                self.logger.debug(
                    f"[USER:{self.user.username}] Erro ao capturar reload request: {exc}"
                )

        try:
            page.on("request", handle_request)
        except Exception as exc:
            self.logger.error(
                f"[USER:{self.user.username}] Falha ao registrar listener /reload: {exc}"
            )
            return None, captured
        return handle_request, captured

    def _finish_recaptcha_reload_capture(
        self,
        page: Page,
        handler,
        captured_request: Dict[str, Optional[str]],
        wait_timeout_ms: int = 4000,
    ) -> Optional[str]:
        """Finaliza listener e retorna payload Base64 da requisição /reload."""
        if not handler:
            return None
        try:
            waited = 0
            interval = 200
            while not captured_request.get("raw") and waited < wait_timeout_ms:
                page.wait_for_timeout(interval)
                waited += interval
        except Exception:
            pass
        finally:
            try:
                page.remove_listener("request", handler)
            except Exception:
                pass

        raw_data = captured_request.get("raw")
        if not raw_data:
            self.logger.warning(
                f"[USER:{self.user.username}] Requisição /reload não foi capturada"
            )
            return None
        encoded = base64.b64encode(raw_data.encode("utf-8")).decode("utf-8")
        self.logger.info(
            f"[USER:{self.user.username}] ✓ Payload reload codificado ({len(encoded)} chars)"
        )
        return encoded

    def _reset_recaptcha_widget(self, page: Page) -> None:
        """Tenta resetar o widget reCAPTCHA para uma nova tentativa."""
        try:
            page.evaluate(
                """
                () => {
                    if (typeof window.grecaptcha !== 'undefined' && typeof window.grecaptcha.reset === 'function') {
                        window.grecaptcha.reset();
                    }
                }
                """
            )
            page.wait_for_timeout(1500)
        except Exception as exc:
            self.logger.debug(
                f"[USER:{self.user.username}] Não foi possível resetar reCAPTCHA: {exc}"
            )

    def _injetar_token_recaptcha(self, page: Page, token: str) -> None:
        """
        Injeta token reCAPTCHA nos contextos corretos e atualiza estado visual do checkbox.

        Realiza a injeção em múltiplos contextos:
        1. Contexto principal (para submissão do formulário)
        2. Contexto do iframe anchor (para validação do Google)
        3. Atualiza estado visual do checkbox (marcado como checked)
        4. Aciona callbacks do reCAPTCHA
        """
        self.logger.debug(f"[USER:{self.user.username}] Injetando token (comprimento: {len(token)})")

        # Log do estado dos iframes reCAPTCHA antes da injeção
        iframe_count = page.evaluate("""
            () => document.querySelectorAll('iframe[src*="recaptcha"]').length
        """)
        self.logger.debug(f"[USER:{self.user.username}] reCAPTCHA iframes presentes: {iframe_count}")

        # PASSO 1: Injetar token no contexto da página principal (para submissão do formulário)
        # IMPORTANTE: NÃO definir display:block - manter textarea oculto
        page.evaluate(
            """
            (token) => {
                const textareas = document.querySelectorAll('[name="g-recaptcha-response"]');
                textareas.forEach((el) => {
                    el.value = token;
                    el.innerHTML = token;
                    // NÃO definir display:block - manter oculto
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                });
            }
            """,
            token,
        )

        # PASSO 2: Encontrar iframe anchor e injetar token no contexto do iframe
        try:
            anchor_frame = None
            for frame in page.frames:
                if "recaptcha/api2/anchor" in frame.url:
                    anchor_frame = frame
                    break

            if anchor_frame:
                # Injetar token dentro do iframe anchor
                anchor_frame.evaluate(
                    """
                    (token) => {
                        const textarea = document.getElementById('g-recaptcha-response');
                        if (textarea) {
                            textarea.value = token;
                            textarea.innerHTML = token;
                        }

                        // PASSO 3: Atualizar estado visual do checkbox
                        const checkbox = document.getElementById('recaptcha-anchor');
                        if (checkbox) {
                            // Remover classe de "não marcado"
                            checkbox.classList.remove('recaptcha-checkbox-unchecked');
                            // Adicionar classe de "marcado"
                            checkbox.classList.add('recaptcha-checkbox-checked');
                            // Atualizar atributo ARIA para acessibilidade
                            checkbox.setAttribute('aria-checked', 'true');
                        }
                    }
                    """,
                    token,
                )
                self.logger.debug(
                    f"[USER:{self.user.username}] Token injetado no contexto do iframe anchor e checkbox marcado"
                )
            else:
                self.logger.warning(
                    f"[USER:{self.user.username}] Iframe anchor não encontrado - injeção apenas no contexto principal"
                )
        except Exception as exc:
            self.logger.warning(
                f"[USER:{self.user.username}] Erro ao injetar no iframe: {exc}"
            )

        # PASSO 4: Acionar callbacks do reCAPTCHA no contexto principal
        page.evaluate(
            """
            (token) => {
                if (typeof ___grecaptcha_cfg !== 'undefined') {
                    Object.keys(___grecaptcha_cfg.clients || {}).forEach((key) => {
                        const client = ___grecaptcha_cfg.clients[key];
                        if (!client) return;

                        // Atualizar resposta do cliente
                        client.response = token;
                        if (client.A) client.A.response = token;

                        // Executar callback se existir
                        if (typeof client.callback === 'function') {
                            try {
                                client.callback(token);
                            } catch (e) {
                                console.log('Erro ao executar callback reCAPTCHA:', e);
                            }
                        }
                    });
                }
            }
            """,
            token,
        )

        # PASSO 5: Atualizar estado do Vue.js (se framework detectado)
        vue_state = page.evaluate(
            """
            (token) => {
                let updated = false;
                let framework = 'Unknown';

                // Detectar e atualizar Vue.js 2
                const appElement = document.querySelector('#app') ||
                                   document.querySelector('[data-v-app]') ||
                                   document.querySelector('.app') ||
                                   document.querySelector('body > div');

                if (appElement && appElement.__vue__) {
                    framework = 'Vue 2';
                    const vueInstance = appElement.__vue__;

                    // Atualizar data do componente
                    if (vueInstance.$data) {
                        vueInstance.$data.recaptchaVerified = true;
                        vueInstance.$data.recaptchaToken = token;
                        updated = true;
                    }

                    // Forçar reatividade
                    if (vueInstance.$forceUpdate) {
                        vueInstance.$forceUpdate();
                    }
                }
                // Detectar e atualizar Vue.js 3
                else if (appElement && appElement.__vueParentComponent) {
                    framework = 'Vue 3';
                    const instance = appElement.__vueParentComponent;

                    if (instance && instance.ctx) {
                        instance.ctx.recaptchaVerified = true;
                        instance.ctx.recaptchaToken = token;
                        updated = true;
                    }
                }

                // Alternativa 1: buscar por formulário com __vue__
                if (!updated) {
                    const form = document.querySelector('form') ||
                                 document.querySelector('.login-form') ||
                                 document.querySelector('[class*="login"]');

                    if (form && form.__vue__) {
                        framework = 'Vue 2 (form)';
                        if (form.__vue__.$data) {
                            form.__vue__.$data.recaptchaVerified = true;
                            form.__vue__.$data.recaptchaToken = token;
                            updated = true;
                        }
                        if (form.__vue__.$forceUpdate) {
                            form.__vue__.$forceUpdate();
                        }
                    }
                }

                // Alternativa 2: buscar em window.app, window.__app, window.vm
                if (!updated) {
                    const globalApps = [window.app, window.__app, window.vm, window._app];
                    for (const app of globalApps) {
                        if (app && typeof app === 'object') {
                            framework = 'Vue (global window)';
                            if (app.$data) {
                                app.$data.recaptchaVerified = true;
                                app.$data.recaptchaToken = token;
                                updated = true;
                                if (app.$forceUpdate) app.$forceUpdate();
                                break;
                            }
                        }
                    }
                }

                // Alternativa 3: varrer todos os elementos com __vue__
                if (!updated) {
                    const allElements = document.querySelectorAll('*');
                    for (const el of allElements) {
                        if (el.__vue__ && el.__vue__.$data) {
                            framework = 'Vue 2 (scan)';
                            el.__vue__.$data.recaptchaVerified = true;
                            el.__vue__.$data.recaptchaToken = token;
                            updated = true;
                            if (el.__vue__.$forceUpdate) el.__vue__.$forceUpdate();
                            break;
                        }
                    }
                }

                // Alternativa 4: detectar React
                if (!updated) {
                    const rootElement = document.getElementById('root') ||
                                        document.getElementById('app') ||
                                        document.querySelector('[data-reactroot]');

                    if (rootElement && (rootElement._reactRootContainer || rootElement._reactRootElement)) {
                        framework = 'React';
                        // React não tem estado global acessível facilmente
                        // Dependeremos da estratégia de forçar botão
                    }
                }

                // Disparar evento customizado que o Vue pode estar escutando
                try {
                    window.dispatchEvent(new CustomEvent('recaptcha-verified', {
                        detail: { token, verified: true }
                    }));
                    document.dispatchEvent(new CustomEvent('recaptcha-success', {
                        detail: { token }
                    }));
                } catch (e) {
                    console.log('Error dispatching custom event:', e);
                }

                return { framework, updated, hasVueDevtools: !!window.__VUE_DEVTOOLS_GLOBAL_HOOK__ };
            }
            """,
            token,
        )

        if vue_state.get('updated'):
            self.logger.info(
                f"[USER:{self.user.username}] ✓ Estado Vue.js atualizado ({vue_state.get('framework')})"
            )

            # Diagnóstico detalhado: verificar valores das propriedades Vue
            vue_values = page.evaluate(
                """
                () => {
                    const appElement = document.querySelector('#app') ||
                                       document.querySelector('[data-v-app]') ||
                                       document.querySelector('.app') ||
                                       document.querySelector('body > div');

                    if (appElement && appElement.__vue__ && appElement.__vue__.$data) {
                        return {
                            recaptchaVerified: appElement.__vue__.$data.recaptchaVerified || false,
                            hasToken: !!appElement.__vue__.$data.recaptchaToken,
                            username: !!appElement.__vue__.$data.username,
                            password: !!appElement.__vue__.$data.password
                        };
                    }
                    return null;
                }
                """
            )

            if vue_values:
                self.logger.debug(
                    f"[USER:{self.user.username}] Vue state após atualização: "
                    f"recaptchaVerified={vue_values.get('recaptchaVerified')}, "
                    f"hasToken={vue_values.get('hasToken')}, "
                    f"username={vue_values.get('username')}, "
                    f"password={vue_values.get('password')}"
                )
        else:
            self.logger.debug(
                f"[USER:{self.user.username}] Vue.js não detectado ou não atualizado - Framework: {vue_state.get('framework')}"
            )

        # PASSO 6: Forçar habilitação do botão (independente do framework)
        self.logger.debug(f"[USER:{self.user.username}] Forçando habilitação do botão de login...")
        button_force_result = page.evaluate(
            """
            () => {
                let buttonsForced = 0;
                let eventsDispatched = 0;

                // Estratégia 1: Forçar habilitação de todos os botões submit
                const buttonSelectors = [
                    'button[type="submit"]',
                    '.ant-btn-primary',
                    'button.ant-btn',
                    'button[class*="submit"]',
                    'button[class*="login"]'
                ];

                buttonSelectors.forEach(selector => {
                    const buttons = document.querySelectorAll(selector);
                    buttons.forEach(btn => {
                        if (btn.disabled || btn.hasAttribute('disabled')) {
                            btn.disabled = false;
                            btn.removeAttribute('disabled');

                            // Remover classes que indicam desabilitado
                            btn.classList.remove('ant-btn-disabled');
                            btn.classList.remove('disabled');

                            // Adicionar classe de habilitado se existir
                            if (!btn.classList.contains('ant-btn-enabled')) {
                                btn.classList.add('ant-btn-enabled');
                            }

                            buttonsForced++;
                        }
                    });
                });

                // Estratégia 2: Disparar eventos de validação no formulário
                const form = document.querySelector('form') ||
                             document.querySelector('.login-form') ||
                             document.querySelector('[class*="login"]');

                if (form) {
                    // Disparar eventos que podem reativar validação
                    ['change', 'input', 'blur', 'focus'].forEach(eventType => {
                        try {
                            form.dispatchEvent(new Event(eventType, { bubbles: true }));
                            eventsDispatched++;
                        } catch (e) {
                            console.log(`Error dispatching ${eventType}:`, e);
                        }
                    });
                }

                // Estratégia 3: Disparar eventos nos campos de input
                const inputs = document.querySelectorAll('input[type="text"], input[type="password"]');
                inputs.forEach(input => {
                    if (input.value) {
                        ['input', 'change', 'blur'].forEach(eventType => {
                            try {
                                input.dispatchEvent(new Event(eventType, { bubbles: true }));
                                eventsDispatched++;
                            } catch (e) {}
                        });
                    }
                });

                // Estratégia 4: Verificar se há objeto global que controla o formulário
                // (React, Vue, Angular podem ter estado global)
                let globalStateUpdated = false;

                // Tentar window.__app, window.app, window.vm
                const possibleGlobalApps = [
                    window.__app,
                    window.app,
                    window.vm,
                    window._app,
                    window.application
                ];

                possibleGlobalApps.forEach(app => {
                    if (app && typeof app === 'object') {
                        try {
                            // Tentar atualizar estado se parecer um objeto Vue/React
                            if (app.setState) {
                                // React
                                app.setState({ recaptchaVerified: true });
                                globalStateUpdated = true;
                            } else if (app.$set || app.$data) {
                                // Vue
                                if (app.$data) {
                                    app.$data.recaptchaVerified = true;
                                }
                                if (app.$forceUpdate) {
                                    app.$forceUpdate();
                                }
                                globalStateUpdated = true;
                            }
                        } catch (e) {
                            console.log('Error updating global app state:', e);
                        }
                    }
                });

                return {
                    buttonsForced,
                    eventsDispatched,
                    globalStateUpdated,
                    formFound: !!form
                };
            }
            """
        )

        self.logger.info(
            f"[USER:{self.user.username}] ✓ Habilitação forçada: {button_force_result.get('buttonsForced')} botões, "
            f"{button_force_result.get('eventsDispatched')} eventos, "
            f"estado global={'atualizado' if button_force_result.get('globalStateUpdated') else 'não encontrado'}"
        )

        # Aguardar para garantir que todas as mudanças foram processadas
        # Tempo maior após forçar habilitação para framework reativo processar
        page.wait_for_timeout(1500)

        # Verificar se token foi injetado com sucesso no contexto principal
        textarea_value_len = page.evaluate("""
            () => {
                const ta = document.querySelector('[name="g-recaptcha-response"]');
                return ta ? ta.value.length : 0;
            }
        """)
        self.logger.debug(
            f"[USER:{self.user.username}] Token injetado no contexto principal. Textarea value.length = {textarea_value_len}"
        )

    def _challenge_visivel(self, page: Page) -> bool:
        """Retorna True se o iframe do desafio visual ainda estiver aberto."""
        return page.evaluate(
            """
            () => {
                const challengeIframes = document.querySelectorAll('iframe[src*="recaptcha"][src*="bframe"]');
                return Array.from(challengeIframes).some((iframe) => {
                    const style = window.getComputedStyle(iframe);
                    return style.display !== 'none' && style.visibility !== 'hidden';
                });
            }
            """
        )

    def _submeter_formulario(self, page: Page) -> bool:
        """
        Executa múltiplas estratégias para submeter o formulário.

        Aguarda até 5 segundos para o botão ser habilitado (polling Vue.js reactivity),
        depois tenta múltiplas estratégias de click/submit.
        """
        import time as time_module

        # Configurar listener de network para capturar requisições de login
        login_requests = []
        login_responses = []
        listener_start_time = time_module.time()

        def handle_request(request):
            """Captura requisições que parecem ser de login/auth."""
            url_lower = request.url.lower()
            if any(keyword in url_lower for keyword in ['/login', '/auth', '/signin', '/api/v1']):
                request_time = time_module.time() - listener_start_time
                try:
                    post_data = request.post_data
                    login_requests.append({
                        'url': request.url,
                        'method': request.method,
                        'post_data': post_data[:500] if post_data else None,  # Limitar tamanho
                        'time': request_time
                    })
                    self.logger.debug(
                        f"[USER:{self.user.username}] ⏱ Request capturado em {request_time:.2f}s: {request.method} {request.url}"
                    )
                except Exception:
                    login_requests.append({
                        'url': request.url,
                        'method': request.method,
                        'post_data': None,
                        'time': request_time
                    })

        def handle_response(response):
            """Captura respostas de requisições de login/auth."""
            url_lower = response.url.lower()
            if any(keyword in url_lower for keyword in ['/login', '/auth', '/signin', '/api/v1']):
                response_time = time_module.time() - listener_start_time
                try:
                    login_responses.append({
                        'url': response.url,
                        'status': response.status,
                        'status_text': response.status_text,
                        'ok': response.ok,
                        'time': response_time
                    })
                    self.logger.debug(
                        f"[USER:{self.user.username}] ⏱ Response capturado em {response_time:.2f}s: "
                        f"{response.status} {response.url}"
                    )
                except Exception:
                    pass

        page.on('request', handle_request)
        page.on('response', handle_response)

        self.logger.debug(
            f"[USER:{self.user.username}] Listeners de network configurados para capturar requisições de login"
        )

        # Capturar erros do console do navegador
        console_errors = []

        def handle_console(msg):
            """Captura mensagens do console, especialmente erros."""
            if msg.type in ['error', 'warning']:
                console_errors.append({
                    'type': msg.type,
                    'text': msg.text,
                    'location': msg.location
                })
                if msg.type == 'error':
                    self.logger.warning(f"[USER:{self.user.username}] Console error: {msg.text}")

        page.on('console', handle_console)

        # NOVA ETAPA: Aguardar botão ser habilitado (polling para Vue.js reactivity)
        self.logger.debug(f"[USER:{self.user.username}] Aguardando botão de login ser habilitado...")
        max_wait = 5000  # 5 segundos
        interval = 200   # Verificar a cada 200ms
        elapsed = 0
        button_enabled = False

        while elapsed < max_wait:
            try:
                button_enabled = page.evaluate(
                    """
                    () => {
                        const selectors = [
                            'button[type="submit"]',
                            '.ant-btn-primary',
                            'button.ant-btn',
                            'button[class*="submit"]',
                            'button[class*="login"]'
                        ];
                        return selectors.some((selector) => {
                            const btn = document.querySelector(selector);
                            return btn && !btn.disabled && !btn.classList.contains('ant-btn-disabled');
                        });
                    }
                    """
                )
                if button_enabled:
                    self.logger.info(
                        f"[USER:{self.user.username}] ✓ Botão habilitado após {elapsed}ms"
                    )
                    break
                page.wait_for_timeout(interval)
                elapsed += interval
            except Exception as exc:
                self.logger.debug(
                    f"[USER:{self.user.username}] Erro ao verificar estado do botão: {exc}"
                )
                break

        if not button_enabled:
            self.logger.warning(
                f"[USER:{self.user.username}] ⚠ Botão permaneceu desabilitado após {max_wait}ms"
            )

            # Diagnóstico: verificar por que botão não foi habilitado
            diagnostic = page.evaluate(
                """
                () => {
                    // Verificar estado do botão
                    const btn = document.querySelector('button[type="submit"]') ||
                                document.querySelector('.ant-btn-primary');

                    const buttonState = btn ? {
                        disabled: btn.disabled,
                        hasDisabledClass: btn.classList.contains('ant-btn-disabled'),
                        classes: Array.from(btn.classList).join(' ')
                    } : { notFound: true };

                    // Verificar estado Vue
                    const appElement = document.querySelector('#app') ||
                                       document.querySelector('[data-v-app]') ||
                                       document.querySelector('.app') ||
                                       document.querySelector('body > div');

                    let vueState = { detected: false };
                    if (appElement && appElement.__vue__ && appElement.__vue__.$data) {
                        const data = appElement.__vue__.$data;
                        vueState = {
                            detected: true,
                            recaptchaVerified: data.recaptchaVerified || false,
                            username: !!data.username,
                            password: !!data.password,
                            hasToken: !!data.recaptchaToken
                        };
                    }

                    // Verificar textarea reCAPTCHA
                    const textarea = document.querySelector('[name="g-recaptcha-response"]');
                    const textareaState = textarea ? {
                        hasValue: !!textarea.value,
                        valueLength: textarea.value.length
                    } : { notFound: true };

                    return { buttonState, vueState, textareaState };
                }
                """
            )

            self.logger.debug(
                f"[USER:{self.user.username}] Diagnóstico completo: {diagnostic}"
            )

        if button_enabled:
            # Tenta clicar no botão submit com Playwright (múltiplos seletores)
            self.logger.debug(f"[USER:{self.user.username}] Tentando clicar no botão com Playwright...")
            selectors = [
                'button[type="submit"]',
                '.ant-btn-primary',
                'button.ant-btn',
                'button[class*="submit"]',
                'button[class*="login"]'
            ]
            for selector in selectors:
                try:
                    self.logger.debug(f"[USER:{self.user.username}] Tentando seletor: {selector}")
                    page.click(selector, timeout=5000)
                    self.logger.info(f"[USER:{self.user.username}] ✓ Click Playwright bem-sucedido com seletor: {selector}")

                    # Aguardar requisição de login completar (timeout inicial)
                    page.wait_for_timeout(3000)

                    # Polling: aguardar até 8s adicionais para requests chegarem
                    max_polling_time = 8000
                    elapsed_polling = 0
                    poll_interval = 500

                    self.logger.debug(
                        f"[USER:{self.user.username}] Iniciando polling para aguardar requests (max {max_polling_time}ms)..."
                    )

                    while elapsed_polling < max_polling_time:
                        if login_responses:  # Se já capturou responses, parar polling
                            self.logger.debug(
                                f"[USER:{self.user.username}] ✓ Responses detectadas após {elapsed_polling}ms de polling"
                            )
                            break
                        page.wait_for_timeout(poll_interval)
                        elapsed_polling += poll_interval

                    # Log timing total
                    total_wait = 3000 + elapsed_polling
                    self.logger.debug(
                        f"[USER:{self.user.username}] Aguardou {total_wait}ms total para capturar responses"
                    )

                    # Log URL após click e polling
                    current_url = page.url
                    self.logger.info(f"[USER:{self.user.username}] URL após click: {current_url}")

                    # Verificar mensagens de erro na página
                    error_message = page.evaluate("""
                        () => {
                            const errorSelectors = [
                                '.ant-message-error',
                                '.error-message',
                                '.login-error',
                                '[class*="error"]',
                                '.ant-notification-notice-message'
                            ];
                            for (const selector of errorSelectors) {
                                const el = document.querySelector(selector);
                                if (el && el.textContent.trim()) {
                                    return el.textContent.trim();
                                }
                            }
                            return null;
                        }
                    """)

                    if error_message:
                        self.logger.error(f"[USER:{self.user.username}] ❌ Erro na página após click: {error_message}")

                    # Log requests/responses capturados
                    if login_requests:
                        self.logger.info(f"[USER:{self.user.username}] Requisições de login capturadas: {len(login_requests)}")
                        for req in login_requests:
                            self.logger.debug(f"[USER:{self.user.username}] Request: {req['method']} {req['url']}")
                            if req['post_data']:
                                self.logger.debug(f"[USER:{self.user.username}] POST data: {req['post_data'][:200]}...")

                    # Verificar respostas ANTES de decidir fazer POST manual
                    if login_responses:
                        self.logger.info(f"[USER:{self.user.username}] Respostas de login capturadas: {len(login_responses)}")
                        for resp in login_responses:
                            self.logger.info(
                                f"[USER:{self.user.username}] Response: {resp['status']} {resp['status_text']} - {resp['url']}"
                            )

                    # Verificar se alguma resposta indica sucesso (status 2xx)
                    success_response = None
                    if login_responses:
                        for resp in login_responses:
                            if 200 <= resp['status'] < 300:
                                success_response = resp
                                break

                    # Se houve resposta de sucesso, aguardar navegação client-side
                    if success_response:
                        self.logger.info(
                            f"[USER:{self.user.username}] ✓ Login bem-sucedido! Status: {success_response['status']} "
                            f"({success_response['status_text']})"
                        )

                        # Aguardar navegação client-side (SPA pode redirecionar via JavaScript)
                        self.logger.debug(f"[USER:{self.user.username}] Aguardando navegação client-side...")
                        page.wait_for_timeout(3000)

                        # Verificar se URL mudou
                        new_url = page.url
                        if new_url != current_url:
                            self.logger.info(f"[USER:{self.user.username}] ✓ Navegação detectada: {new_url}")
                        else:
                            self.logger.debug(f"[USER:{self.user.username}] URL permanece: {new_url}")

                    # Se NÃO houve requisições OU todas as respostas falharam, tentar POST manual
                    elif not login_requests or not success_response:
                        if not login_requests:
                            self.logger.error(
                                f"[USER:{self.user.username}] ❌ CRÍTICO: Nenhuma requisição de login foi capturada - formulário NÃO foi submetido!"
                            )
                        else:
                            self.logger.warning(
                                f"[USER:{self.user.username}] ⚠ Requisições enviadas mas todas falharam (sem status 2xx)"
                            )

                        # Tentar fazer POST manual via fetch
                        self.logger.info(f"[USER:{self.user.username}] Tentando POST manual via fetch...")
                        manual_response = page.evaluate("""
                            async () => {
                                try {
                                    // Tentar múltiplos seletores para os campos
                                    const email = document.querySelector('input[name="email"]')?.value ||
                                                  document.querySelector('input[type="email"]')?.value ||
                                                  document.querySelector('input[type="text"]')?.value ||
                                                  document.querySelector('input[name="username"]')?.value ||
                                                  document.querySelector('input[placeholder*="mail"]')?.value ||
                                                  document.querySelector('input[placeholder*="sername"]')?.value;

                                    const password = document.querySelector('input[type="password"]')?.value ||
                                                     document.querySelector('input[name="password"]')?.value;

                                    const recaptcha = document.querySelector('[name="g-recaptcha-response"]')?.value;

                                    if (!email || !password) {
                                        return { success: false, error: 'Campos de email/senha não encontrados' };
                                    }

                                    if (!recaptcha) {
                                        return { success: false, error: 'Token reCAPTCHA não encontrado' };
                                    }

                                    const url = 'https://api.dreamtv.life/reseller/login';
                                    const headers = {
                                        'Content-Type': 'application/json',
                                        'Accept': 'application/json'
                                    };

                                    // Primeira tentativa: campo "recaptcha"
                                    let response = await fetch(url, {
                                        method: 'POST',
                                        headers: headers,
                                        body: JSON.stringify({
                                            email: email,
                                            password: password,
                                            recaptcha: recaptcha
                                        })
                                    });

                                    let data;
                                    try {
                                        data = await response.json();
                                    } catch (e) {
                                        data = { error: 'Resposta não é JSON' };
                                    }

                                    // Se erro 500 e mensagem menciona "recaptcha", tentar com "recaptcha_token"
                                    if (response.status === 500 &&
                                        data.message &&
                                        data.message.toLowerCase().includes('recaptcha')) {

                                        console.log('Tentando retry com campo "recaptcha_token"...');

                                        response = await fetch(url, {
                                            method: 'POST',
                                            headers: headers,
                                            body: JSON.stringify({
                                                email: email,
                                                password: password,
                                                recaptcha_token: recaptcha
                                            })
                                        });

                                        try {
                                            data = await response.json();
                                        } catch (e) {
                                            data = { error: 'Resposta não é JSON (retry)' };
                                        }
                                    }

                                    return {
                                        success: response.ok,
                                        status: response.status,
                                        statusText: response.statusText,
                                        data: data
                                    };
                                } catch (error) {
                                    return { success: false, error: error.message };
                                }
                            }
                        """)

                        if manual_response.get('success'):
                            self.logger.info(
                                f"[USER:{self.user.username}] ✓ POST manual bem-sucedido! Status: {manual_response.get('status')}"
                            )
                            # Aguardar navegação client-side
                            page.wait_for_timeout(3000)

                            # Verificar se URL mudou
                            new_url = page.url
                            if new_url != current_url:
                                self.logger.info(f"[USER:{self.user.username}] ✓ Navegação detectada: {new_url}")
                            else:
                                self.logger.debug(f"[USER:{self.user.username}] URL permanece: {new_url}")
                        else:
                            self.logger.error(
                                f"[USER:{self.user.username}] ❌ POST manual falhou: {manual_response.get('error')} - "
                                f"Status: {manual_response.get('status')}, Data: {manual_response.get('data')}"
                            )

                    return True
                except Exception as exc:
                    self.logger.debug(f"[USER:{self.user.username}] Falha no seletor {selector}: {exc}")
                    continue

            self.logger.warning(f"[USER:{self.user.username}] Todos os seletores Playwright falharam, tentando JS manual...")

        # Método JS manual (sempre tenta, mesmo se Playwright falhou)
        self.logger.debug(f"[USER:{self.user.username}] Tentando método JS manual (btn.click())...")
        try:
            clicked = page.evaluate(
                """
                () => {
                    const selectors = [
                        '.ant-btn-primary',
                        'button.ant-btn',
                        'button[type="submit"]'
                    ];
                    for (const selector of selectors) {
                        const btn = document.querySelector(selector);
                        if (btn) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }
                """
            )
            if clicked:
                self.logger.info(f"[USER:{self.user.username}] ✓ Click JS manual bem-sucedido")

                # Aguardar requisição de login completar
                page.wait_for_timeout(2000)

                # Log URL após click
                current_url = page.url
                self.logger.info(f"[USER:{self.user.username}] URL após click JS: {current_url}")

                # Verificar mensagens de erro
                error_message = page.evaluate("""
                    () => {
                        const errorSelectors = ['.ant-message-error', '.error-message', '.login-error', '[class*="error"]'];
                        for (const selector of errorSelectors) {
                            const el = document.querySelector(selector);
                            if (el && el.textContent.trim()) return el.textContent.trim();
                        }
                        return null;
                    }
                """)

                if error_message:
                    self.logger.error(f"[USER:{self.user.username}] ❌ Erro na página após click JS: {error_message}")

                # Log requests/responses
                if login_responses:
                    for resp in login_responses:
                        self.logger.info(f"[USER:{self.user.username}] Response JS: {resp['status']} - {resp['url']}")

                return True
            else:
                self.logger.warning(f"[USER:{self.user.username}] Click JS manual falhou - botão não encontrado")
        except Exception as exc:
            self.logger.warning(f"[USER:{self.user.username}] Exceção no click JS manual: {exc}")

        # Submit direto (última tentativa)
        self.logger.debug(f"[USER:{self.user.username}] Tentando form.submit() direto...")
        try:
            submitted = page.evaluate(
                """
                () => {
                    const form = document.querySelector('form#form-login') ||
                                 document.querySelector('form.login-form') ||
                                 document.querySelector('form');
                    if (form) {
                        form.submit();
                        return true;
                    }
                    return false;
                }
                """
            )
            if submitted:
                self.logger.info(f"[USER:{self.user.username}] ✓ Form.submit() direto bem-sucedido")
                return True
            else:
                self.logger.error(f"[USER:{self.user.username}] ❌ Form.submit() falhou - formulário não encontrado")
        except Exception as exc:
            self.logger.error(f"[USER:{self.user.username}] ❌ Exceção no form.submit(): {exc}")

        # Se chegou aqui, todos os métodos falharam
        self.logger.error(f"[USER:{self.user.username}] ❌ ERRO CRÍTICO: Nenhum método de submissão funcionou")
        return False

    def _fazer_login_com_extensao(self, page: Page, timeout: Optional[int] = None) -> Optional[str]:
        """Aguarda a extensão CapSolver injetar o token no textarea."""
        timeout = timeout or getattr(settings, "CAPSOLVER_EXTENSION_TIMEOUT", 60)
        self.logger.info(
            f"[USER:{self.user.username}] Aguardando até {timeout}s para a extensão resolver o reCAPTCHA..."
        )
        start = time.time()
        while time.time() - start < timeout:
            token = page.evaluate(
                """
                () => {
                    const textarea = document.querySelector('[name="g-recaptcha-response"]');
                    return textarea ? textarea.value || '' : '';
                }
                """
            )
            if token and len(token) > 100:
                self.logger.info(
                    f"[USER:{self.user.username}] ✓ Extensão CapSolver injetou o token (len={len(token)})"
                )
                return token
            page.wait_for_timeout(1000)
        self.logger.warning(
            f"[USER:{self.user.username}] Extensão não resolveu o reCAPTCHA dentro de {timeout}s"
        )
        return None

    def fazer_login_automatico(self, capsolver_api_key: Optional[str] = None) -> bool:
        """
        Login automático com resolução de reCAPTCHA via CapSolver
        (prioriza extensão quando disponível, fallback para API com proxy próprio).
        """
        self.logger.info(
            f"[USER:{self.user.username}] Iniciando login automático com CapSolver"
        )

        storage_state = None

        try:
            capsolver = CapSolverService(api_key=capsolver_api_key)
            balance = capsolver.get_balance()
            if balance is not None and balance < 0.01:
                self.logger.error(
                    f"[USER:{self.user.username}] Saldo CapSolver insuficiente: ${balance:.4f}"
                )
                return False

            proxy_config = getattr(settings, "CAPSOLVER_PROXY", None)
            playwright_proxy = self._build_playwright_proxy(proxy_config)
            capsolver_method = getattr(settings, "CAPSOLVER_METHOD", "api").lower()
            extension_path_setting = getattr(settings, "CAPSOLVER_EXTENSION_PATH", None)
            extension_timeout = getattr(settings, "CAPSOLVER_EXTENSION_TIMEOUT", 60)

            usar_extensao = False
            extension_path = None
            if capsolver_method in ("extension", "auto"):
                if extension_path_setting and os.path.exists(extension_path_setting):
                    usar_extensao = True
                    extension_path = extension_path_setting
                else:
                    self.logger.warning(
                        f"[USER:{self.user.username}] Extensão CapSolver não encontrada (CAPSOLVER_EXTENSION_PATH)"
                    )
                    if capsolver_method == "extension":
                        self.logger.error(
                            f"[USER:{self.user.username}] Modo 'extension' exige extensão instalada."
                        )
                        return False

            debug_mode = False
            try:
                config = ConfiguracaoAutomacao.objects.filter(user=self.user).first()
                if config:
                    debug_mode = config.debug_headless_mode
                    self.logger.info(
                        f"[USER:{self.user.username}] ConfiguracaoAutomacao encontrada: debug_mode={debug_mode}"
                    )
                else:
                    self.logger.warning(
                        f"[USER:{self.user.username}] ConfiguracaoAutomacao não encontrada"
                    )
            except Exception as exc:
                self.logger.error(
                    f"[USER:{self.user.username}] Erro ao consultar ConfiguracaoAutomacao: {exc}"
                )

            if usar_extensao and not debug_mode:
                self.logger.info(
                    f"[USER:{self.user.username}] Extensão requer navegador visível - forçando headless=False"
                )
                debug_mode = True

            with sync_playwright() as p:
                browser_args: List[str] = []
                if debug_mode:
                    browser_args.extend(["--start-maximized", "--force-device-scale-factor=0.8"])
                if usar_extensao and extension_path:
                    browser_args.extend([
                        f"--disable-extensions-except={extension_path}",
                        f"--load-extension={extension_path}",
                    ])

                browser = p.chromium.launch(
                    headless=not debug_mode,
                    args=browser_args,
                    proxy=playwright_proxy,
                )

                browser_user_agent = (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                context = browser.new_context(
                    user_agent=browser_user_agent,
                    viewport={"width": 1920, "height": 1080},
                    locale="pt-BR",
                    timezone_id="America/Recife",
                )

                page = context.new_page()

                # Verificar IP real do navegador (se usando proxy)
                if playwright_proxy:
                    try:
                        actual_ip = page.evaluate("""
                            async () => {
                                try {
                                    const response = await fetch('https://api.ipify.org?format=json');
                                    const data = await response.json();
                                    return data.ip;
                                } catch (e) {
                                    return 'erro: ' + e.message;
                                }
                            }
                        """)
                        self.logger.info(
                            f"[USER:{self.user.username}] IP real do navegador Playwright: {actual_ip}"
                        )
                        self.logger.info(
                            f"[USER:{self.user.username}] Proxy configurado: {proxy_config}"
                        )
                    except Exception as e:
                        self.logger.warning(
                            f"[USER:{self.user.username}] Não foi possível verificar IP do navegador: {e}"
                        )

                login_url = self.get_login_url()
                page.goto(login_url, wait_until="domcontentloaded", timeout=60000)

                # Aguarda explicitamente o iframe do reCAPTCHA aparecer com retry e reload
                max_iframe_attempts = 2
                iframe_detected = False

                for iframe_attempt in range(1, max_iframe_attempts + 1):
                    try:
                        page.wait_for_selector('iframe[src*="recaptcha"]', timeout=30000)
                        self.logger.info(f"[USER:{self.user.username}] reCAPTCHA iframe detectado")
                        iframe_detected = True
                        break
                    except PlaywrightTimeoutError:
                        self.logger.warning(
                            f"[USER:{self.user.username}] reCAPTCHA iframe não detectado (tentativa {iframe_attempt}/{max_iframe_attempts})"
                        )
                        if iframe_attempt < max_iframe_attempts:
                            self.logger.info(f"[USER:{self.user.username}] Recarregando página para tentar novamente...")
                            page.reload(wait_until="domcontentloaded", timeout=60000)
                            page.wait_for_timeout(3000)  # Aguarda 3s após reload
                        else:
                            self.logger.error(
                                f"[USER:{self.user.username}] reCAPTCHA iframe não detectado após {max_iframe_attempts} tentativas - abortando login"
                            )
                            browser.close()
                            return False

                if not iframe_detected:
                    self.logger.error(
                        f"[USER:{self.user.username}] Login abortado: reCAPTCHA não carregado"
                    )
                    browser.close()
                    return False

                self.logger.info(f"[USER:{self.user.username}] Página de login carregada com reCAPTCHA")
                senha_descriptografada = decrypt_password(self.conta.senha_login)
                self._preencher_formulario_login(
                    page, self.conta.email_login, senha_descriptografada
                )
                self.logger.info(f"[USER:{self.user.username}] Credenciais preenchidas")

                login_concluido = False

                if usar_extensao:
                    self.logger.info(
                        f"[USER:{self.user.username}] Tentando resolver reCAPTCHA com CapSolver Extension..."
                    )
                    extension_token = self._fazer_login_com_extensao(
                        page, timeout=extension_timeout
                    )
                    if extension_token:
                        self._injetar_token_recaptcha(page, extension_token)
                        if self._challenge_visivel(page):
                            self.logger.warning(
                                f"[USER:{self.user.username}] Desafio visual permaneceu após extensão - fallback API"
                            )
                            self._reset_recaptcha_widget(page)
                        elif self._submeter_formulario(page):
                            login_concluido = True
                        else:
                            self.logger.warning(
                                f"[USER:{self.user.username}] Submit falhou após token da extensão - usando API"
                            )
                    else:
                        if capsolver_method == "extension":
                            self.logger.error(
                                f"[USER:{self.user.username}] Extensão não resolveu o reCAPTCHA no tempo limite"
                            )
                            browser.close()
                            return False
                        self.logger.info(
                            f"[USER:{self.user.username}] Extensão indisponível - usando API CapSolver"
                        )

                max_captcha_attempts = 2
                if not login_concluido:
                    for attempt in range(1, max_captcha_attempts + 1):
                        sitekey = page.evaluate(
                            """
                            () => {
                                let el = document.querySelector('[data-sitekey]');
                                if (el) return el.getAttribute('data-sitekey');

                                el = document.querySelector('.g-recaptcha');
                                if (el) return el.getAttribute('data-sitekey');

                                const scripts = document.querySelectorAll('script');
                                for (const script of scripts) {
                                    const match = script.textContent.match(/sitekey['\":\s]+['\"]([-\w]+)['\"]/);
                                    if (match) return match[1];
                                }

                                const iframes = document.querySelectorAll('iframe[src*="google.com/recaptcha"]');
                                for (const iframe of iframes) {
                                    const match = iframe.src.match(/[?&]k=([^&]+)/);
                                    if (match) return match[1];
                                }
                                return null;
                            }
                            """
                        )

                        if not sitekey:
                            self.logger.error(
                                f"[USER:{self.user.username}] Sitekey do reCAPTCHA não detectado (tentativa {attempt}/{max_captcha_attempts})"
                            )
                            if attempt < max_captcha_attempts:
                                self.logger.info(f"[USER:{self.user.username}] Aguardando 5s antes de nova tentativa...")
                                page.wait_for_timeout(5000)
                                continue
                            else:
                                self.logger.error(
                                    f"[USER:{self.user.username}] Sitekey não detectado após {max_captcha_attempts} tentativas - abortando login"
                                )
                                browser.close()
                                return False

                        if attempt > 1:
                            self.logger.info(
                                f"[USER:{self.user.username}] 🔁 Nova tentativa ({attempt}/{max_captcha_attempts})"
                            )

                        # Verificar se iframe anchor está pronto antes de coletar dados
                        try:
                            page.wait_for_selector(
                                'iframe[src*="recaptcha/api2/anchor"]',
                                timeout=10000,
                                state='attached'
                            )
                            self.logger.debug(
                                f"[USER:{self.user.username}] reCAPTCHA anchor iframe está pronto"
                            )
                        except PlaywrightTimeoutError:
                            self.logger.error(
                                f"[USER:{self.user.username}] reCAPTCHA anchor iframe não está pronto - pulando tentativa"
                            )
                            continue

                        # Clicar no checkbox para disparar a requisição /reload
                        try:
                            checkbox_clicked = False
                            for frame in page.frames:
                                if "recaptcha/api2/anchor" in frame.url:
                                    try:
                                        frame.click("#recaptcha-anchor", timeout=3000)
                                        checkbox_clicked = True
                                        self.logger.debug(
                                            f"[USER:{self.user.username}] Checkbox reCAPTCHA clicado"
                                        )
                                        page.wait_for_timeout(1000)  # Aguardar requisição /reload
                                        break
                                    except Exception as frame_exc:
                                        self.logger.debug(
                                            f"[USER:{self.user.username}] Erro ao clicar checkbox no frame: {frame_exc}"
                                        )

                            if not checkbox_clicked:
                                self.logger.warning(
                                    f"[USER:{self.user.username}] Não foi possível clicar no checkbox"
                                )
                        except Exception as exc:
                            self.logger.warning(
                                f"[USER:{self.user.username}] Erro ao tentar clicar checkbox: {exc}"
                            )

                        reload_handler, reload_state = self._start_recaptcha_reload_capture(page)
                        anchor_base64 = self._extrair_anchor_html(page)
                        page.wait_for_timeout(500)
                        reload_base64 = self._finish_recaptcha_reload_capture(
                            page, reload_handler, reload_state
                        )
                        cookies_header = self._format_cookies_for_capsolver(context)

                        self.logger.info(
                            f"[USER:{self.user.username}] Resolvendo reCAPTCHA com CapSolver..."
                        )
                        token = capsolver.solve_recaptcha_v2(
                            sitekey=sitekey,
                            url=page.url,
                            proxy=proxy_config,
                            anchor=anchor_base64,
                            reload=reload_base64,
                            user_agent=browser_user_agent,
                            cookies=cookies_header,
                            page_action="login",  # Indica que é ação de login para reCAPTCHA Enterprise
                        )
                        self.logger.info(
                            f"[USER:{self.user.username}] Token CapSolver obtido: {token[:50]}... (comprimento: {len(token)})"
                        )

                        # Verificar se textarea reCAPTCHA existe antes de injetar
                        textarea_exists = page.evaluate("""
                            () => {
                                const textarea = document.querySelector('[name="g-recaptcha-response"]');
                                return textarea !== null;
                            }
                        """)

                        if not textarea_exists:
                            self.logger.error(
                                f"[USER:{self.user.username}] Textarea g-recaptcha-response não encontrada - pulando injeção"
                            )
                            continue

                        self._injetar_token_recaptcha(page, token)
                        page.wait_for_timeout(1500)

                        # Validar se checkbox foi marcado como checked após injeção
                        checkbox_checked = False
                        try:
                            for frame in page.frames:
                                if "recaptcha/api2/anchor" in frame.url:
                                    checkbox_checked = frame.evaluate("""
                                        () => {
                                            const checkbox = document.getElementById('recaptcha-anchor');
                                            if (!checkbox) return false;
                                            return checkbox.classList.contains('recaptcha-checkbox-checked') &&
                                                   checkbox.getAttribute('aria-checked') === 'true';
                                        }
                                    """)
                                    break

                            if checkbox_checked:
                                self.logger.debug(
                                    f"[USER:{self.user.username}] ✓ Checkbox validado como marcado após injeção"
                                )
                            else:
                                self.logger.warning(
                                    f"[USER:{self.user.username}] ⚠ Checkbox NÃO está marcado - token pode não validar"
                                )
                        except Exception as exc:
                            self.logger.warning(
                                f"[USER:{self.user.username}] Erro ao validar estado do checkbox: {exc}"
                            )

                        # Pausar para permitir teste manual de login (se configurado)
                        manual_test_timeout = getattr(settings, "MANUAL_LOGIN_TEST_TIMEOUT", 0)
                        if manual_test_timeout > 0:
                            self.logger.warning(
                                f"[USER:{self.user.username}] "
                                f"⏸ PAUSADO para teste manual por {manual_test_timeout} segundos. "
                                f"Clique no botão de login MANUALMENTE agora!"
                            )

                            # Logar progresso a cada 5 segundos
                            elapsed = 0
                            interval = 5000  # 5 segundos
                            total_ms = manual_test_timeout * 1000

                            while elapsed < total_ms:
                                wait_time = min(interval, total_ms - elapsed)
                                page.wait_for_timeout(wait_time)
                                elapsed += wait_time

                                if elapsed < total_ms:
                                    remaining = (total_ms - elapsed) / 1000
                                    self.logger.info(
                                        f"[USER:{self.user.username}] ⏳ Aguardando click manual... {remaining:.0f}s restantes"
                                    )

                            self.logger.info(
                                f"[USER:{self.user.username}] ✓ Timeout de teste manual concluído. "
                                f"Continuando automação..."
                            )

                        if self._challenge_visivel(page):
                            self.logger.warning(
                                f"[USER:{self.user.username}] Google abriu desafio visual - repetindo fluxo..."
                            )
                            self._reset_recaptcha_widget(page)
                            continue

                        if self._submeter_formulario(page):
                            login_concluido = True
                            break

                if not login_concluido:
                    self.logger.error(
                        f"[USER:{self.user.username}] Não foi possível concluir login automático."
                    )
                    browser.close()
                    return False

                # Tentar aguardar navegação para dashboard
                dashboard_reached = False
                try:
                    page.wait_for_url(
                        self.get_dashboard_url_pattern(),
                        timeout=30000,
                    )
                    self.logger.info(
                        f"[USER:{self.user.username}] ✓ Dashboard alcançado via wait_for_url!"
                    )
                    dashboard_reached = True
                except PlaywrightTimeoutError:
                    final_url = page.url
                    self.logger.debug(
                        f"[USER:{self.user.username}] Timeout em wait_for_url (URL final: {final_url})"
                    )

                    # Verificar se URL mudou da página de login (indicando possível sucesso)
                    login_url = self.get_login_url()
                    if final_url != login_url and "#/login" not in final_url.lower():
                        self.logger.info(
                            f"[USER:{self.user.username}] ✓ URL mudou da página de login para: {final_url}"
                        )

                        # Verificar se há elementos do dashboard na página
                        dashboard_elements = page.evaluate("""
                            () => {
                                // Procurar indicadores comuns de dashboard
                                const indicators = [
                                    document.querySelector('[class*="dashboard"]'),
                                    document.querySelector('[class*="home"]'),
                                    document.querySelector('[class*="main-content"]'),
                                    document.querySelector('nav'),
                                    document.querySelector('.ant-layout'),
                                    document.querySelector('[role="main"]'),
                                ];
                                return indicators.filter(el => el !== null).length;
                            }
                        """)

                        if dashboard_elements > 0:
                            self.logger.info(
                                f"[USER:{self.user.username}] ✓ {dashboard_elements} elementos de dashboard detectados - login bem-sucedido!"
                            )
                            dashboard_reached = True
                        else:
                            self.logger.warning(
                                f"[USER:{self.user.username}] ⚠ URL mudou mas nenhum elemento de dashboard detectado"
                            )
                    else:
                        self.logger.error(
                            f"[USER:{self.user.username}] ❌ URL permaneceu na página de login: {final_url}"
                        )

                if not dashboard_reached:
                    self.logger.error(
                        f"[USER:{self.user.username}] ❌ Login automático falhou - dashboard não foi alcançado"
                    )
                    browser.close()
                    return False

                # Login bem-sucedido - salvar sessão
                self.logger.info(
                    f"[USER:{self.user.username}] Login automático bem-sucedido!"
                )
                storage_state = context.storage_state()

                browser.close()

            if storage_state:
                self.conta.session_data = json.dumps(storage_state)
                self.conta.sessao_valida = True
                self.conta.ultimo_login = timezone.now()
                self.conta.save()
                self.logger.info(
                    f"[USER:{self.user.username}] Sessão automática salva com sucesso"
                )
                return True

            self.logger.error(
                f"[USER:{self.user.username}] Falha ao capturar storage_state após login automático"
            )
            return False

        except CapSolverException as exc:
            self.logger.error(f"[USER:{self.user.username}] Erro no CapSolver: {exc}")
            return False
        except Exception as exc:
            self.logger.exception(
                f"[USER:{self.user.username}] Erro no login automático: {exc}"
            )
            return False
    def verificar_sessao_valida(self) -> bool:
        """
        Testa se a sessão salva ainda está ativa.

        Carrega os cookies salvos e tenta acessar o dashboard.
        Se redirecionar para login, a sessão expirou.

        Returns:
            bool: True se sessão válida, False se expirada/inválida

        Example:
            >>> if not service.verificar_sessao_valida():
            ...     service.fazer_login_automatico()
        """
        if not self.conta.session_data:
            self.logger.info(
                f"[USER:{self.user.username}] Nenhuma sessão salva encontrada"
            )
            return False

        self.logger.info(
            f"[USER:{self.user.username}] Verificando validade da sessão..."
        )

        is_valid = False  # Variável para capturar resultado

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)

                # Carrega sessão salva
                session_state = json.loads(self.conta.session_data)
                context = browser.new_context(storage_state=session_state)
                page = context.new_page()

                # Tenta acessar dashboard
                dashboard_url = self.get_dashboard_url()
                page.goto(dashboard_url, wait_until='domcontentloaded', timeout=30000)

                # Verifica se está no dashboard ou foi redirecionado para login
                current_url = page.url
                is_valid = self._is_dashboard_url(current_url)

                browser.close()

            # FORA do contexto Playwright (sem event loop ativo),
            # atualiza banco de dados
            if is_valid:
                self.logger.info(
                    f"[USER:{self.user.username}] Sessão válida ✓"
                )
                self.conta.sessao_valida = True
                self.conta.save(update_fields=['sessao_valida'])
            else:
                self.logger.warning(
                    f"[USER:{self.user.username}] Sessão expirada (redirecionado para login)"
                )
                self.conta.sessao_valida = False
                self.conta.save(update_fields=['sessao_valida'])

            return is_valid

        except Exception as e:
            self.logger.error(
                f"[USER:{self.user.username}] Erro ao verificar sessão: {e}"
            )
            # FORA do contexto Playwright
            self.conta.sessao_valida = False
            self.conta.save(update_fields=['sessao_valida'])
            return False

    def executar_migracao(self, tarefa_id: int) -> None:
        """
        Executa migração DNS de dispositivos (método principal).

        Este método deve ser chamado em uma thread separada, pois pode
        demorar vários minutos dependendo da quantidade de dispositivos.

        Fluxo:
        1. Carrega tarefa do banco
        2. Verifica sessão (faz login se necessário)
        3. Abre navegador headless
        4. Navega até lista de dispositivos
        5. Para cada dispositivo:
           - Atualiza DNS (apenas automação, sem DB)
           - Armazena resultado em lista
        6. Fecha navegador
        7. Salva TODOS os resultados no banco (fora do contexto Playwright)
        8. Atualiza status final da tarefa

        Args:
            tarefa_id: ID da TarefaMigracaoDNS

        Example:
            >>> # Em view:
            >>> def executar_migracao_thread():
            ...     service.executar_migracao(tarefa.id)
            >>> threading.Thread(target=executar_migracao_thread).start()
        """
        self.logger.info(f"[TAREFA:{tarefa_id}] Iniciando execução da migração DNS")

        try:
            # Carrega tarefa
            tarefa = TarefaMigracaoDNS.objects.get(id=tarefa_id)
            tarefa.status = TarefaMigracaoDNS.STATUS_EM_ANDAMENTO
            tarefa.iniciada_em = timezone.now()
            tarefa.save()

            # Verifica sessão
            if not self.verificar_sessao_valida():
                self.logger.error(
                    f"[TAREFA:{tarefa_id}] Sessão inválida. Não é possível executar em headless."
                )
                tarefa.status = TarefaMigracaoDNS.STATUS_ERRO_LOGIN
                tarefa.erro_geral = "Sessão expirada. Faça login manualmente primeiro."
                tarefa.concluida_em = timezone.now()
                tarefa.save()
                return

            # Lista para armazenar resultados (processamento dentro do Playwright)
            resultados_dispositivos = []

            # Verificar se admin ativou modo debug headless (ANTES do Playwright)
            debug_mode = False
            try:
                config = ConfiguracaoAutomacao.objects.filter(user=self.user).first()
                if config:
                    debug_mode = config.debug_headless_mode
                    self.logger.info(
                        f"[TAREFA:{tarefa_id}] ConfiguracaoAutomacao encontrada: "
                        f"debug_mode={debug_mode}"
                    )
                else:
                    self.logger.warning(
                        f"[TAREFA:{tarefa_id}] ConfiguracaoAutomacao não encontrada para "
                        f"user={self.user.username}"
                    )
            except Exception as e:
                self.logger.error(
                    f"[TAREFA:{tarefa_id}] Erro ao consultar ConfiguracaoAutomacao: {e}"
                )

            # Checkpoint 1: ANTES do Playwright (não pode save() dentro do contexto async)
            tarefa.etapa_atual = 'analisando'
            tarefa.mensagem_progresso = 'Iniciando automação do painel reseller...'
            tarefa.progresso_percentual = 10
            tarefa.save(update_fields=['etapa_atual', 'mensagem_progresso', 'progresso_percentual'])
            self.logger.info(f"[TAREFA:{tarefa_id}] Checkpoint 1: Análise iniciada (10%)")

            # Inicia automação
            with sync_playwright() as p:
                if debug_mode:
                    # Modo debug: navegador visível, maximizado, zoom 80%
                    self.logger.info(f"[TAREFA:{tarefa_id}] 🐛 MODO DEBUG: Navegador visível")
                    browser = p.chromium.launch(
                        headless=False,
                        args=['--start-maximized', '--force-device-scale-factor=0.8']
                    )
                else:
                    # Modo produção: navegador headless (invisível)
                    browser = p.chromium.launch(headless=True)

                # Carrega sessão
                session_state = json.loads(self.conta.session_data)
                context = browser.new_context(storage_state=session_state)
                page = context.new_page()

                try:
                    # Navega até dispositivos
                    self._navegar_ate_dispositivos(page)
                    self.logger.info(f"[TAREFA:{tarefa_id}] Página de dispositivos carregada")

                    # Obtém lista de dispositivos alvo (com progresso incluído no método)
                    dispositivos_alvo = self._obter_dispositivos_alvo(page, tarefa)

                    self.logger.info(
                        f"[TAREFA:{tarefa_id}] Encontrados {len(dispositivos_alvo)} dispositivos"
                    )

                    # CAMADA 1.2: Garantir que navegador está na página 1 antes de processar
                    # (Garantia dupla - pode ter mudado após extração)
                    if len(dispositivos_alvo) > 0:
                        self._go_to_first_page(page)
                        page.wait_for_timeout(500)
                        current_page = self._get_current_page_number(page)
                        self.logger.info(
                            f"[TAREFA:{tarefa_id}] Navegador resetado para página {current_page} "
                            "antes do processamento ✓"
                        )

                    # Verificar se MAC específico não foi encontrado
                    # NÃO salva agora - apenas armazena em variável para salvar depois
                    if tarefa.tipo_migracao == TarefaMigracaoDNS.TIPO_ESPECIFICO and len(dispositivos_alvo) == 0:
                        self.logger.error(
                            f"[TAREFA:{tarefa_id}] MAC '{tarefa.mac_alvo}' não encontrado. "
                            "Tarefa será cancelada após fechar navegador."
                        )
                        # Flags para salvar após fechar navegador
                        dispositivo_nao_encontrado = True
                    else:
                        dispositivo_nao_encontrado = False

                    # Processa cada dispositivo (SEM salvar no banco - estamos em contexto Playwright)
                    total_dispositivos = len(dispositivos_alvo)
                    for idx, device_info in enumerate(dispositivos_alvo, 1):
                        mac = device_info['mac']

                        # Apenas log (sem save)
                        self.logger.info(
                            f"[TAREFA:{tarefa_id}] [{idx}/{total_dispositivos}] "
                            f"Processando {mac}"
                        )

                        resultado = self._processar_dispositivo(
                            page=page,
                            tarefa=tarefa,
                            device_info=device_info,
                            dominio_origem=tarefa.dominio_origem,
                            dominio_destino=tarefa.dominio_destino
                        )

                        # Armazena resultado para salvar DEPOIS (fora do Playwright)
                        resultados_dispositivos.append(resultado)

                finally:
                    browser.close()

            # Checkpoint 2: APÓS Playwright (agora pode fazer save)
            # Verifica se dispositivo específico não foi encontrado
            if 'dispositivo_nao_encontrado' in locals() and dispositivo_nao_encontrado:
                tarefa.status = TarefaMigracaoDNS.STATUS_CANCELADA
                tarefa.erro_geral = f"Dispositivo com MAC '{tarefa.mac_alvo}' não encontrado no painel reseller"
                tarefa.etapa_atual = 'cancelada'
                tarefa.mensagem_progresso = f"Dispositivo {tarefa.mac_alvo} não encontrado no painel."
                tarefa.progresso_percentual = 0
                tarefa.concluida_em = timezone.now()
                tarefa.save()
                self.logger.error(f"[TAREFA:{tarefa_id}] MAC não encontrado. Tarefa cancelada.")
                return  # Encerra execução

            # FORA do contexto Playwright (sem event loop ativo),
            # salva TODOS os resultados no banco
            tarefa.total_dispositivos = len(resultados_dispositivos)
            tarefa.etapa_atual = 'processando'
            tarefa.mensagem_progresso = f'{tarefa.total_dispositivos} dispositivo(s) encontrado(s). Salvando resultados...'
            tarefa.progresso_percentual = 30
            tarefa.save(update_fields=['total_dispositivos', 'etapa_atual', 'mensagem_progresso', 'progresso_percentual'])
            self.logger.info(f"[TAREFA:{tarefa_id}] Checkpoint 2: Processamento iniciado (30%)")

            for idx, resultado in enumerate(resultados_dispositivos, 1):
                # Cria registro de dispositivo no banco
                DispositivoMigracaoDNS.objects.create(
                    tarefa=tarefa,
                    device_id=resultado['device_id'],
                    nome_dispositivo=resultado.get('nome_dispositivo', ''),
                    status=resultado['status'],
                    dns_encontrado=resultado.get('dns_encontrado', ''),
                    dns_atualizado=resultado.get('dns_atualizado', ''),
                    mensagem_erro=resultado.get('erro', ''),
                    processado_em=timezone.now()
                )

                # Atualiza contadores
                tarefa.processados += 1
                if resultado['status'] == 'sucesso':
                    tarefa.sucessos += 1
                elif resultado['status'] == 'erro':
                    tarefa.falhas += 1
                elif resultado['status'] == 'pulado':
                    tarefa.pulados += 1

                # Batch update: salva progresso a cada 10 dispositivos OU no último
                if idx % 10 == 0 or idx == tarefa.total_dispositivos:
                    # Progresso: 30% base + 70% proporcional
                    progress_pct = 30 + int((idx / tarefa.total_dispositivos) * 70)
                    tarefa.mensagem_progresso = f'Processando dispositivo {idx}/{tarefa.total_dispositivos}...'
                    tarefa.progresso_percentual = min(progress_pct, 100)
                    tarefa.save(update_fields=['processados', 'sucessos', 'falhas', 'pulados', 'mensagem_progresso', 'progresso_percentual'])
                    self.logger.debug(f"[TAREFA:{tarefa_id}] Progresso: {idx}/{tarefa.total_dispositivos} ({progress_pct}%)")

            # Finaliza tarefa com status baseado nos resultados
            if tarefa.total_dispositivos == 0:
                # Nenhum dispositivo encontrado (defesa adicional)
                tarefa.status = TarefaMigracaoDNS.STATUS_CANCELADA
                tarefa.etapa_atual = 'cancelada'
                tarefa.mensagem_progresso = 'Nenhum dispositivo encontrado no painel.'
                tarefa.progresso_percentual = 0
                if not tarefa.erro_geral:
                    tarefa.erro_geral = "Nenhum dispositivo encontrado no painel reseller"
            elif tarefa.sucessos == 0 and tarefa.falhas > 0:
                # Todos os dispositivos falharam
                tarefa.status = TarefaMigracaoDNS.STATUS_CANCELADA
                tarefa.etapa_atual = 'cancelada'
                tarefa.mensagem_progresso = f'Todos os {tarefa.falhas} dispositivos falharam.'
                tarefa.progresso_percentual = 100
                if not tarefa.erro_geral:
                    tarefa.erro_geral = f"Todos os {tarefa.falhas} dispositivos falharam"
            elif tarefa.falhas > 0:
                # Parcialmente bem-sucedida (alguns sucessos, alguns erros)
                tarefa.status = TarefaMigracaoDNS.STATUS_CONCLUIDA
                tarefa.etapa_atual = 'concluida'
                tarefa.mensagem_progresso = f'Migração concluída: {tarefa.sucessos} sucesso(s), {tarefa.falhas} erro(s), {tarefa.pulados} pulado(s).'
                tarefa.progresso_percentual = 100
                if not tarefa.erro_geral:
                    tarefa.erro_geral = f"{tarefa.sucessos} sucesso(s), {tarefa.falhas} erro(s)"
            else:
                # 100% sucesso
                tarefa.status = TarefaMigracaoDNS.STATUS_CONCLUIDA
                tarefa.etapa_atual = 'concluida'
                tarefa.mensagem_progresso = f'Migração concluída com sucesso! {tarefa.sucessos} dispositivo(s) atualizado(s).'
                tarefa.progresso_percentual = 100

            tarefa.concluida_em = timezone.now()
            tarefa.save()

            self.logger.info(
                f"[TAREFA:{tarefa_id}] Concluída | "
                f"Total: {tarefa.total_dispositivos} | "
                f"Sucessos: {tarefa.sucessos} | "
                f"Falhas: {tarefa.falhas}"
            )

        except TarefaMigracaoDNS.DoesNotExist:
            self.logger.error(f"[TAREFA:{tarefa_id}] Tarefa não encontrada no banco")
        except Exception as e:
            self.logger.exception(f"[TAREFA:{tarefa_id}] Erro fatal na execução: {e}")

            # Marca tarefa como erro
            try:
                tarefa = TarefaMigracaoDNS.objects.get(id=tarefa_id)
                tarefa.status = TarefaMigracaoDNS.STATUS_CANCELADA
                tarefa.erro_geral = str(e)
                tarefa.concluida_em = timezone.now()
                tarefa.save()
            except:
                pass

    def _obter_dispositivos_alvo(
        self,
        page: Page,
        tarefa: TarefaMigracaoDNS
    ) -> List[Dict]:
        """
        Obtém lista de dispositivos a serem migrados.

        IMPORTANTE: Este método NÃO salva no banco de dados (roda dentro do Playwright).
        Apenas retorna a lista de dispositivos. O salvamento é feito pelo método chamador.

        Args:
            page: Página do Playwright
            tarefa: Tarefa de migração

        Returns:
            Lista de dicts com informações dos dispositivos
        """
        if tarefa.tipo_migracao == TarefaMigracaoDNS.TIPO_TODOS:
            # Extrai MACs de todos dispositivos (sem salvar progresso durante)
            return self._extrair_todos_dispositivos_simplificado(page)
        else:
            # Apenas dispositivo específico
            return self._extrair_dispositivo_especifico(page, tarefa.mac_alvo)

    def _processar_dispositivo(
        self,
        page: Page,
        tarefa: TarefaMigracaoDNS,
        device_info: Dict,
        dominio_origem: str,
        dominio_destino: str
    ) -> Dict:
        """
        Processa um dispositivo individual (atualiza DNS via substituição de domínio).

        IMPORTANTE: Este método NÃO salva no banco de dados.
        Apenas realiza a automação Playwright e retorna o resultado.
        O salvamento no banco é responsabilidade do método chamador.

        Args:
            page: Página do Playwright
            tarefa: Tarefa de migração
            device_info: Dict com informações do dispositivo
            dominio_origem: Domínio origem (protocolo+host+porta, ex: http://old.com:8080)
            dominio_destino: Domínio destino (protocolo+host+porta)

        Returns:
            Dict com status, device_id, nome_dispositivo, dns_encontrado,
            dns_atualizado, mensagem_erro
        """
        try:
            # Chama método específico da plataforma
            resultado = self._atualizar_dns_dispositivo(
                page=page,
                device_id=device_info['mac'],
                dominio_origem=dominio_origem,
                dominio_destino=dominio_destino,
                device_info=device_info
            )

            # Adiciona informações do dispositivo ao resultado
            resultado['device_id'] = device_info['mac']
            resultado['nome_dispositivo'] = device_info.get('nome', '')

            return resultado

        except Exception as e:
            self.logger.exception(
                f"[TAREFA:{tarefa.id}] [DEVICE:{device_info['mac']}] Erro: {e}"
            )

            return {
                'status': 'erro',
                'erro': str(e),
                'device_id': device_info['mac'],
                'nome_dispositivo': device_info.get('nome', '')
            }

    # ==================== MÉTODOS ABSTRATOS (cada plataforma implementa) ====================

    @abstractmethod
    def get_login_url(self) -> str:
        """Retorna URL da página de login da plataforma."""
        pass

    @abstractmethod
    def get_dashboard_url(self) -> str:
        """Retorna URL do dashboard da plataforma."""
        pass

    @abstractmethod
    def get_dashboard_url_pattern(self) -> str:
        """Retorna padrão regex da URL do dashboard (para wait_for_url)."""
        pass

    @abstractmethod
    def _is_dashboard_url(self, url: str) -> bool:
        """Verifica se URL é do dashboard (não login)."""
        pass

    @abstractmethod
    def _preencher_formulario_login(self, page: Page, email: str, senha: str) -> None:
        """Preenche formulário de login (implementação específica de cada plataforma)."""
        pass

    @abstractmethod
    def _navegar_ate_dispositivos(self, page: Page) -> None:
        """Navega até página de listagem de dispositivos."""
        pass

    @abstractmethod
    def _extrair_todos_dispositivos(self, page: Page) -> List[Dict]:
        """Extrai informações de todos os dispositivos da tabela."""
        pass

    @abstractmethod
    def _extrair_dispositivo_especifico(self, page: Page, mac: str) -> List[Dict]:
        """Extrai informações de um dispositivo específico pelo MAC."""
        pass

    @abstractmethod
    def _atualizar_dns_dispositivo(
        self,
        page: Page,
        device_id: str,
        dominio_origem: str,
        dominio_destino: str,
        device_info: Optional[Dict] = None
    ) -> Dict:
        """
        Atualiza DNS de um dispositivo específico via automação Playwright.
        """
        pass


# ==================== IMPLEMENTAÇÃO ESPECÍFICA: DREAMTV ====================

class DreamTVAutomation(ResellerAutomationService):
    """Implementação específica para DreamTV Reseller."""

    BASE_URL = "https://reseller.dreamtv.life"

    # -------------------- Helpers internos --------------------

    def _get_visible_drawers(self, page: Page) -> List[Locator]:
        """Retorna drawers (Ant Design) atualmente visíveis."""
        drawers = page.locator('.ant-drawer-content-wrapper')
        total = drawers.count()
        visibles: List[Locator] = []
        for idx in range(total):
            drawer = drawers.nth(idx)
            try:
                if drawer.is_visible():
                    visibles.append(drawer)
            except Exception:
                continue
        return visibles

    def _wait_for_top_drawer(
        self,
        page: Page,
        min_visible: int = 1,
        timeout: int = 30000,
    ) -> Locator:
        """Aguarda até que haja pelo menos `min_visible` drawers e retorna o mais recente."""
        deadline = time.time() + (timeout / 1000)
        last_error: Optional[Exception] = None

        while time.time() < deadline:
            remaining_ms = max(int((deadline - time.time()) * 1000), 0)

            if remaining_ms <= 0:
                break

            # Tenta sincronizar com o drawer mais recente renderizado pelo Ant Design
            try:
                page.locator('.ant-drawer-content-wrapper').last.wait_for(
                    state='visible',
                    timeout=max(300, min(2000, remaining_ms)),
                )
            except PlaywrightTimeoutError as e:
                last_error = e

            visibles = self._get_visible_drawers(page)
            if len(visibles) >= min_visible:
                return visibles[-1]

            page.wait_for_timeout(200)

        raise PlaywrightTimeoutError("Timeout aguardando drawer visível.") from last_error

    def _wait_for_drawer_close(
        self,
        page: Page,
        expected_visible: int,
        timeout: int = 15000,
    ) -> None:
        """Aguarda até que o número de drawers visíveis seja <= expected_visible."""
        deadline = time.time() + (timeout / 1000)
        last_error: Optional[Exception] = None

        while time.time() < deadline:
            visibles = self._get_visible_drawers(page)
            if len(visibles) <= expected_visible:
                return
            try:
                page.locator('.ant-drawer-content-wrapper').last.wait_for(
                    state='hidden',
                    timeout=500,
                )
            except PlaywrightTimeoutError as e:
                last_error = e
            page.wait_for_timeout(200)

        raise PlaywrightTimeoutError("Timeout aguardando fechamento do drawer.") from last_error

    def _close_drawer(self, page: Page, drawer: Locator) -> None:
        """Fecha drawer informado (botão X ou tecla ESC) e aguarda encerramento."""
        visibles = self._get_visible_drawers(page)
        expected_visible = max(len(visibles) - 1, 0)
        try:
            close_button = drawer.locator('.ant-drawer-close').first
            if close_button.count() and close_button.is_visible():
                close_button.click()
            else:
                page.keyboard.press('Escape')
        except Exception:
            page.keyboard.press('Escape')
        try:
            self._wait_for_drawer_close(page, expected_visible)
        except PlaywrightTimeoutError:
            self.logger.warning("Timeout aguardando drawer fechar completamente.")

    def _close_all_drawers(self, page: Page) -> None:
        """Fecha todos os drawers abertos em ordem reversa."""
        safety = 0
        while self._get_visible_drawers(page) and safety < 5:
            drawer = self._get_visible_drawers(page)[-1]
            self._close_drawer(page, drawer)
            safety += 1

    def _get_current_page_number(self, page: Page) -> int:
        """Retorna número da página ativa na tabela principal."""
        try:
            active = page.locator('.ant-table-pagination .ant-pagination-item-active')
            if active.count():
                text = active.first.inner_text().strip()
                digits = ''.join(ch for ch in text if ch.isdigit())
                if digits:
                    return int(digits)
        except Exception:
            pass
        return 1

    def _wait_for_page_change(
        self,
        page: Page,
        previous_page: int,
        timeout: int = 10000,
    ) -> None:
        """Aguarda mudança no número da página de listagem principal."""
        page.wait_for_function(
            """(args) => {
                const el = document.querySelector(args.selector);
                if (!el) { return false; }
                const text = (el.textContent || '').trim();
                return text && text !== args.previous;
            }""",
            arg={
                'selector': '.ant-table-pagination .ant-pagination-item-active',
                'previous': str(previous_page)
            },
            timeout=timeout,
        )

    def _go_to_page(self, page: Page, target_page: int, timeout: int = 10000) -> bool:
        """Navega até a página desejada da tabela principal."""
        current = self._get_current_page_number(page)
        if current == target_page:
            return True

        pagination = page.locator('.ant-table-pagination')
        target_locator = pagination.locator('.ant-pagination-item').filter(
            has_text=str(target_page)
        )

        if target_locator.count():
            previous = current
            clickable = target_locator.first.locator('a')
            if clickable.count():
                clickable.first.click()
            else:
                target_locator.first.click()
            try:
                self._wait_for_page_change(page, previous, timeout=timeout)
                page.wait_for_selector('table tbody tr.ant-table-row', timeout=timeout)
                return True
            except PlaywrightTimeoutError:
                return False

        direction = 1 if target_page > current else -1
        button_selector = '.ant-pagination-next' if direction == 1 else '.ant-pagination-prev'

        for _ in range(50):
            button = pagination.locator(button_selector)
            if button.count() == 0:
                break
            class_attr = button.first.get_attribute('class') or ''
            if 'ant-pagination-disabled' in class_attr:
                break
            previous = self._get_current_page_number(page)
            button.first.click()
            try:
                self._wait_for_page_change(page, previous, timeout=timeout)
                page.wait_for_selector('table tbody tr.ant-table-row', timeout=timeout)
            except PlaywrightTimeoutError:
                break
            current = self._get_current_page_number(page)
            if current == target_page:
                return True

        return False

    def _go_to_first_page(self, page: Page) -> None:
        """Garante que a tabela principal esteja na primeira página."""
        try:
            self._go_to_page(page, 1)
        except Exception:
            pass

    def _localizar_linha_dispositivo(
        self,
        page: Page,
        device_id: str,
    ) -> Optional[Locator]:
        """Localiza a linha do dispositivo (MAC) mesmo em tabelas paginadas."""
        # CAMADA 3: Robustez melhorada - timeouts maiores, logging detalhado

        # TENTATIVA 1: Procura na página atual
        locator = page.locator(
            f'table tbody tr.ant-table-row:has-text("{device_id}")'
        ).first
        try:
            if locator.is_visible(timeout=5000):  # Aumentado de 2s → 5s
                self.logger.debug(f"[DEVICE:{device_id}] Encontrado na página atual")
                return locator
        except Exception as e:
            self.logger.debug(f"[DEVICE:{device_id}] Não encontrado na página atual: {e}")

        # TENTATIVA 2: Busca completa desde a primeira página
        self.logger.debug(f"[DEVICE:{device_id}] Iniciando busca completa desde página 1")
        self._go_to_first_page(page)
        page.wait_for_timeout(500)  # Aguarda navegação estabilizar

        visited_pages: Set[int] = set()
        max_iterations = 20  # Prevenir loop infinito

        for iteration in range(max_iterations):
            current_page = self._get_current_page_number(page)

            # Evita loop infinito
            if current_page in visited_pages:
                self.logger.debug(
                    f"[DEVICE:{device_id}] Página {current_page} já visitada. Encerrando busca."
                )
                break
            visited_pages.add(current_page)

            self.logger.debug(
                f"[DEVICE:{device_id}] Procurando na página {current_page} "
                f"(iteração {iteration + 1}/{max_iterations})"
            )

            # Aguarda tabela estar pronta
            try:
                page.wait_for_selector('table tbody tr.ant-table-row', timeout=5000)
            except PlaywrightTimeoutError:
                self.logger.warning(f"[DEVICE:{device_id}] Timeout aguardando tabela na página {current_page}")
                break

            # Busca dispositivo
            locator = page.locator(
                f'table tbody tr.ant-table-row:has-text("{device_id}")'
            ).first

            if locator.count():
                try:
                    if locator.is_visible(timeout=5000):  # Aumentado de 2s → 5s
                        self.logger.info(
                            f"[DEVICE:{device_id}] ✓ Encontrado na página {current_page} "
                            f"após {iteration + 1} tentativa(s)"
                        )
                        return locator
                except Exception as e:
                    self.logger.debug(
                        f"[DEVICE:{device_id}] Locator existe mas não visível na página {current_page}: {e}"
                    )

            # Tenta avançar para próxima página
            next_button = page.locator('.ant-table-pagination .ant-pagination-next')
            if next_button.count() == 0:
                self.logger.debug(f"[DEVICE:{device_id}] Botão 'próxima página' não encontrado")
                break

            class_attr = next_button.first.get_attribute('class') or ''
            if 'ant-pagination-disabled' in class_attr:
                self.logger.debug(f"[DEVICE:{device_id}] Última página alcançada")
                break

            previous = current_page
            next_button.first.click()

            try:
                self._wait_for_page_change(page, previous)
                page.wait_for_timeout(500)  # Aguarda estabilizar após navegação
            except PlaywrightTimeoutError:
                self.logger.warning(f"[DEVICE:{device_id}] Timeout aguardando mudança de página")
                break

        self.logger.error(
            f"[DEVICE:{device_id}] ✗ Não encontrado após busca completa "
            f"({len(visited_pages)} página(s) visitadas)"
        )
        return None

    def _get_active_page_number_from_drawer(self, drawer: Locator) -> int:
        """Retorna a página ativa dentro de um drawer paginado."""
        try:
            active = drawer.locator('.ant-pagination .ant-pagination-item-active')
            if active.count():
                text = active.first.inner_text().strip()
                digits = ''.join(ch for ch in text if ch.isdigit())
                if digits:
                    return int(digits)
        except Exception:
            pass
        return 1

    # -------------------- Implementações abstratas --------------------

    def get_login_url(self) -> str:
        return f"{self.BASE_URL}/#/login"

    def get_dashboard_url(self) -> str:
        return f"{self.BASE_URL}/#/dashboard"

    def get_dashboard_url_pattern(self) -> str:
        return "**/dashboard**"

    def _is_dashboard_url(self, url: str) -> bool:
        return '#/login' not in url and '#/dashboard' in url

    def _preencher_formulario_login(self, page: Page, email: str, senha: str) -> None:
        try:
            page.wait_for_selector('input[type="email"], input[type="text"]', timeout=10000)
            email_input = page.locator('input[type="email"], input[type="text"]').first
            email_input.fill(email)
            senha_input = page.locator('input[type="password"]').first
            senha_input.fill(senha)
            self.logger.info(f"[USER:{self.user.username}] Formulário preenchido")
        except Exception as e:
            self.logger.warning(
                f"[USER:{self.user.username}] Não foi possível pré-preencher formulário: {e}"
            )

    def _garantir_idioma_portugues(self, page: Page) -> None:
        """Garante que a interface esteja em português clicando na bandeira do Brasil."""
        try:
            self.logger.info(f"[USER:{self.user.username}] Alterando idioma para Português...")

            # Clicar no dropdown da bandeira (seletor específico do DreamTV)
            language_selector = page.locator('.languageBlock_select__fxWxd').first
            if language_selector.is_visible(timeout=3000):
                language_selector.click()
                page.wait_for_timeout(500)

                # Selecionar bandeira do Brasil (item que contém imagem com flag/br.png)
                br_item = page.locator('.ant-select-item:has(img[src*="flag/br.png"])').first
                if br_item.is_visible(timeout=2000):
                    br_item.click()
                    page.wait_for_timeout(1000)  # Aguarda UI atualizar
                    self.logger.info(f"[USER:{self.user.username}] Idioma alterado para Português ✓")
                    return

            self.logger.warning(f"[USER:{self.user.username}] Dropdown de idioma não encontrado")
        except Exception as e:
            self.logger.warning(f"[USER:{self.user.username}] Erro ao alterar idioma: {e}")

    def _navegar_ate_dispositivos(self, page: Page) -> int:
        """
        Navega até página de dispositivos e retorna quantidade de itens por página.

        Returns:
            int: Quantidade de itens por página (10, 50, ou 100)
        """
        devices_url = f"{self.BASE_URL}/#/dashboard/activated"
        page.goto(devices_url, wait_until='domcontentloaded', timeout=60000)

        # Garantir que interface esteja em português
        self._garantir_idioma_portugues(page)

        # Aguardar 2s para efeitos da página carregar
        page.wait_for_timeout(2000)
        try:
            page.wait_for_selector('table tbody tr.ant-table-row', timeout=30000)
        except PlaywrightTimeoutError:
            self.logger.warning("Tabela de dispositivos não carregou dentro do tempo limite.")
        self._go_to_first_page(page)

        # MELHORIA 1 & 2: Tentar alterar paginação para 100 itens (com retry)
        MAX_ATTEMPTS = 3
        items_per_page = 10  # default

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                self.logger.info(f"[Tentativa {attempt}/{MAX_ATTEMPTS}] Alterando paginação para 100 itens...")

                # Usar seletores corretos do HTML fornecido pelo usuário
                pagination_selector = page.locator('.ant-select-sm.ant-pagination-options-size-changer').first
                if pagination_selector.is_visible(timeout=5000):
                    pagination_selector.click()
                    page.wait_for_timeout(800)  # Aumentado de 500ms para 800ms

                    # Selecionar "100 / page"
                    option_100 = page.locator('.ant-select-item[title="100 / page"]').first
                    if option_100.is_visible(timeout=3000):
                        option_100.click()
                        page.wait_for_timeout(2000)  # Aumentado de 1s para 2s para garantir renderização

                        # VALIDAR se realmente mudou (multi-estratégia)
                        pag_value = self._verificar_valor_paginacao(page)

                        if pag_value == 100:
                            self.logger.info(f"✓ Paginação confirmada em 100 itens/página (tentativa {attempt})")
                            items_per_page = 100
                            break  # Sucesso! Sair do loop
                        elif pag_value in [50, 10]:
                            self.logger.warning(f"⚠ Paginação está em {pag_value} itens/página (esperado: 100)")
                            items_per_page = pag_value
                            # Continuar tentando se não for a última tentativa
                            if attempt < MAX_ATTEMPTS:
                                self.logger.info("Tentando novamente...")
                                page.wait_for_timeout(1000)
                                continue
                        else:
                            self.logger.warning(f"⚠ Valor de paginação não reconhecido: {pag_value}")
                            if attempt < MAX_ATTEMPTS:
                                page.wait_for_timeout(1000)
                                continue
                    else:
                        self.logger.warning("Opção '100 / page' não encontrada no dropdown")
                else:
                    self.logger.debug("Seletor de paginação não encontrado; usando configuração padrão.")

            except Exception as e:
                self.logger.warning(f"Tentativa {attempt} falhou: {e}")
                if attempt < MAX_ATTEMPTS:
                    page.wait_for_timeout(1000)
                    continue

        # Se após todas as tentativas não conseguiu configurar 100, logar e capturar screenshot
        if items_per_page != 100:
            self.logger.warning(f"⚠ Após {MAX_ATTEMPTS} tentativas, paginação está em {items_per_page}/página")

            # MELHORIA 6: Capturar screenshot para debug
            try:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = f"logs/Reseller/paginacao_falha_{timestamp}.png"
                page.screenshot(path=screenshot_path, full_page=True)
                self.logger.info(f"Screenshot salvo em: {screenshot_path}")
            except Exception as e:
                self.logger.debug(f"Falha ao capturar screenshot: {e}")

        return items_per_page

    def _verificar_valor_paginacao(self, page: Page) -> int:
        """
        Verifica o valor atual da paginação usando múltiplas estratégias.

        Returns:
            int: Valor da paginação (10, 50, 100) ou 0 se não conseguiu ler
        """
        # ESTRATÉGIA 1: Seletor mais específico (.ant-select-selection-item-content)
        try:
            pag_text_locator = page.locator('.ant-pagination-options-size-changer .ant-select-selection-item').first
            if pag_text_locator.is_visible(timeout=2000):
                pag_text = pag_text_locator.text_content(timeout=2000).strip()
                self.logger.debug(f"[Estratégia 1] Texto extraído: '{pag_text}'")

                if '100' in pag_text:
                    return 100
                elif '50' in pag_text:
                    return 50
                elif '10' in pag_text:
                    return 10
        except Exception as e:
            self.logger.debug(f"[Estratégia 1] Falhou: {e}")

        # ESTRATÉGIA 2: JavaScript direto
        try:
            pag_text = page.evaluate("""
                () => {
                    const el = document.querySelector('.ant-pagination-options-size-changer .ant-select-selection-item');
                    return el ? el.textContent.trim() : '';
                }
            """)
            self.logger.debug(f"[Estratégia 2 - JS] Texto extraído: '{pag_text}'")

            if '100' in pag_text:
                return 100
            elif '50' in pag_text:
                return 50
            elif '10' in pag_text:
                return 10
        except Exception as e:
            self.logger.debug(f"[Estratégia 2] Falhou: {e}")

        # ESTRATÉGIA 3: Fallback genérico
        try:
            pag_text_locator = page.locator('.ant-select-selection-item').first
            if pag_text_locator.is_visible(timeout=2000):
                pag_text = pag_text_locator.text_content(timeout=2000).strip()
                self.logger.debug(f"[Estratégia 3 - Fallback] Texto extraído: '{pag_text}'")

                if '100' in pag_text:
                    return 100
                elif '50' in pag_text:
                    return 50
                elif '10' in pag_text:
                    return 10
        except Exception as e:
            self.logger.debug(f"[Estratégia 3] Falhou: {e}")

        # Se nenhuma estratégia funcionou, retornar 0 (não conseguiu ler)
        self.logger.warning("⚠ Nenhuma estratégia conseguiu ler o valor da paginação")
        return 0

    def _contar_total_paginas(self, page: Page) -> int:
        """
        Conta o número total de páginas navegando até a última.

        Estratégia SIMPLIFICADA e ROBUSTA:
        1. Clica em "Next" repetidamente
        2. Após cada clique, lê número da página ativa
        3. Quando "Next" fica desabilitado, retorna o número atual
        4. Não tenta ler botões de paginação (fonte não confiável)

        Returns:
            int: Número total de páginas (mínimo 1)
        """
        self.logger.info("=== INICIANDO CONTAGEM DE PÁGINAS ===")

        try:
            # Aguarda paginação estar visível
            page.wait_for_selector('.ant-table-pagination', timeout=5000)
            page.wait_for_timeout(1000)  # Aguarda paginação carregar completamente

            # Lê página inicial
            pagina_inicial = self._get_current_page_number(page)
            self.logger.info(f"[CONTAGEM] Página inicial: {pagina_inicial}")

            # Se não há paginação, retorna 1
            next_button = page.locator('.ant-pagination-next')
            if next_button.count() == 0:
                self.logger.info("[CONTAGEM] Botão 'Next' não encontrado → 1 página")
                return 1

            # Verifica se botão já está desabilitado (página única)
            class_attr = next_button.first.get_attribute('class') or ''
            if 'ant-pagination-disabled' in class_attr:
                self.logger.info("[CONTAGEM] Botão 'Next' desabilitado → 1 página")
                return 1

            # Navega clicando "Next" até desabilitar
            self.logger.info("[CONTAGEM] Navegando até última página...")
            visited_pages = []
            max_iterations = 50

            for iteration in range(max_iterations):
                # Lê página atual ANTES de clicar
                current_page = self._get_current_page_number(page)
                visited_pages.append(current_page)

                self.logger.debug(
                    f"[CONTAGEM] Iteração {iteration + 1}: "
                    f"Página atual = {current_page} | "
                    f"Páginas visitadas = {visited_pages}"
                )

                # Verifica se botão "Next" existe
                next_button = page.locator('.ant-pagination-next')
                if next_button.count() == 0:
                    self.logger.warning(f"[CONTAGEM] Botão 'Next' desapareceu na iteração {iteration + 1}")
                    break

                # Verifica se botão está desabilitado
                class_attr = next_button.first.get_attribute('class') or ''
                self.logger.debug(f"[CONTAGEM] Classe do botão 'Next': {class_attr}")

                if 'ant-pagination-disabled' in class_attr:
                    # Chegamos na última página!
                    final_page = self._get_current_page_number(page)
                    self.logger.info(
                        f"[CONTAGEM] ✓ Botão 'Next' desabilitado! Última página = {final_page} | "
                        f"Páginas visitadas = {visited_pages}"
                    )

                    # Volta para página inicial
                    if final_page != pagina_inicial:
                        self.logger.debug(f"[CONTAGEM] Voltando para página {pagina_inicial}...")
                        self._go_to_page(page, pagina_inicial)
                        page.wait_for_timeout(500)

                    self.logger.info(f"[CONTAGEM] === TOTAL: {final_page} PÁGINAS ===")
                    return final_page

                # Clica em "Next"
                self.logger.debug(f"[CONTAGEM] Clicando em 'Next'...")
                page_before_click = current_page

                try:
                    next_button.first.click()
                    page.wait_for_timeout(500)  # Aguarda navegação

                    # Verifica se página mudou
                    page_after_click = self._get_current_page_number(page)
                    self.logger.debug(
                        f"[CONTAGEM] Após click: página mudou de {page_before_click} → {page_after_click}"
                    )

                    if page_after_click == page_before_click:
                        # Página não mudou! Pode estar travado
                        self.logger.warning(
                            f"[CONTAGEM] ⚠ Página não mudou após click! "
                            f"Permaneceu em {page_before_click}. Tentando aguardar mais..."
                        )
                        page.wait_for_timeout(1000)  # Aguarda mais tempo

                        # Verifica novamente
                        page_after_wait = self._get_current_page_number(page)
                        if page_after_wait == page_before_click:
                            self.logger.error(
                                f"[CONTAGEM] ✗ Página ainda em {page_before_click} após 1.5s. "
                                "Parando navegação."
                            )
                            break

                except Exception as e:
                    self.logger.error(f"[CONTAGEM] Erro ao clicar em 'Next': {e}")
                    break

                # Proteção contra loop infinito
                if current_page in visited_pages[:-1]:  # Exclui última adição
                    self.logger.warning(
                        f"[CONTAGEM] Loop detectado! Página {current_page} já visitada antes. "
                        f"Páginas: {visited_pages}"
                    )
                    break

            # Se chegou aqui sem encontrar última página, usa maior página visitada
            if visited_pages:
                max_page = max(visited_pages)
                self.logger.warning(
                    f"[CONTAGEM] Navegação não completou normalmente. "
                    f"Usando maior página visitada: {max_page} | "
                    f"Todas páginas: {visited_pages}"
                )

                # Volta para página inicial
                current = self._get_current_page_number(page)
                if current != pagina_inicial:
                    self._go_to_page(page, pagina_inicial)
                    page.wait_for_timeout(500)

                self.logger.info(f"[CONTAGEM] === TOTAL (parcial): {max_page} PÁGINAS ===")
                return max_page

            # Fallback: assume 1 página
            self.logger.error("[CONTAGEM] Nenhuma página visitada! Assumindo 1 página.")
            return 1

        except Exception as e:
            self.logger.error(f"[CONTAGEM] EXCEÇÃO: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            self.logger.warning("[CONTAGEM] Assumindo 1 página devido a erro.")
            return 1

    def _extrair_todos_dispositivos_simplificado(
        self,
        page: Page
    ) -> List[Dict]:
        """
        Extrai apenas os MACs de todos os dispositivos (extração robusta com virtualização).

        Este método:
        1. Conta o total de páginas dinamicamente
        2. Navega TODAS as páginas com estratégias de fallback
        3. Extrai apenas linhas visíveis (20-30 primeiras) para lidar com virtualização

        IMPORTANTE: Este método roda DENTRO do contexto Playwright (async),
        portanto NÃO pode fazer chamadas save() ao banco.

        Args:
            page: Página do Playwright

        Returns:
            Lista de dicts com MACs encontrados: [{'mac': 'XX:XX:XX', 'nome': '', 'page': N}, ...]
        """
        macs_encontrados: List[Dict] = []  # CAMADA 2.1: Agora armazena dicts com página
        macs_set: Set[str] = set()  # Para checagem rápida de duplicação
        visited_pages: Set[int] = set()
        duplicados_count = 0  # MUDANÇA 1: Contador de MACs duplicados

        # SOLUÇÃO VIRTUALIZAÇÃO: Aumentar limite para cobrir 100/page com margem
        # Combinado com zoom out e scroll, garante extração completa
        MAX_ROWS_PER_PAGE = 150  # Aumentado de 30 para 150

        self.logger.info("Iniciando extração completa de dispositivos...")

        # SOLUÇÃO VIRTUALIZAÇÃO: Zoom out AGRESSIVO para renderizar todas as linhas
        # Zoom 20% = viewport 5x maior → garante que 100+ linhas sejam visíveis simultaneamente
        try:
            page.evaluate("document.body.style.zoom = '0.2'")  # Zoom 20% (5x viewport)
            page.wait_for_timeout(800)  # Aguarda rendering (mais tempo por ser zoom extremo)
            self.logger.info("Zoom reduzido para 20% para viewport 5x maior ✓")
        except Exception as e:
            self.logger.warning(f"Falha ao aplicar zoom out: {e}. Continuando sem zoom...")

        # Contar total de páginas
        total_pages = self._contar_total_paginas(page)
        self.logger.info(f"Total de {total_pages} página(s) detectadas")

        # Fase 2: EXTRAÇÃO - Navegar todas as páginas (20-100% do progresso para extração)
        page_num = 0
        consecutive_empty_pages = 0
        MAX_CONSECUTIVE_EMPTY = 3

        while page_num < total_pages or consecutive_empty_pages < MAX_CONSECUTIVE_EMPTY:
            try:
                # Aguarda tabela carregar
                page.wait_for_selector('table tbody tr.ant-table-row', timeout=15000)
            except PlaywrightTimeoutError:
                self.logger.warning(f"Timeout aguardando tabela na página {page_num + 1}. Tentando continuar...")
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= MAX_CONSECUTIVE_EMPTY:
                    break
                continue

            current_page = self._get_current_page_number(page)

            # Evita loop infinito
            if current_page in visited_pages:
                self.logger.info(f"Página {current_page} já foi visitada. Tentando avançar...")

                # Tenta avançar mesmo assim (pode estar travado)
                if not self._tentar_avancar_pagina(page, current_page, total_pages):
                    self.logger.info("Não foi possível avançar. Encerrando extração.")
                    break
                continue

            visited_pages.add(current_page)
            page_num += 1

            # Log de progresso (sem save - estamos em contexto Playwright)
            self.logger.info(f"Página {page_num}/{total_pages}: extraindo primeiras {MAX_ROWS_PER_PAGE} linhas visíveis")

            # MUDANÇA 2: Scroll até o final da tabela ANTES de extrair
            # Isso força a virtualização a renderizar TODAS as linhas antes de começarmos a extração
            try:
                # Scroll até o final da tabela
                page.evaluate("""
                    const table = document.querySelector('.ant-table-body');
                    if (table) {
                        table.scrollTo(0, table.scrollHeight);
                    }
                """)
                page.wait_for_timeout(800)  # Aguarda rendering completo
                self.logger.debug("Scroll até final da tabela executado - forçando rendering de todas as linhas ✓")

                # Volta para o topo
                page.evaluate("""
                    const table = document.querySelector('.ant-table-body');
                    if (table) {
                        table.scrollTo(0, 0);
                    }
                """)
                page.wait_for_timeout(400)
                self.logger.debug("Scroll retornado ao topo ✓")
            except Exception as e:
                self.logger.warning(f"Falha ao executar scroll pré-extração: {e}")

            # MELHORIA 5: Validar quantas linhas estão visíveis antes de extrair
            try:
                total_rows_visible = page.evaluate("""
                    () => document.querySelectorAll('table tbody tr.ant-table-row:not(.ant-table-placeholder)').length
                """)
                self.logger.info(f"Total de linhas visíveis na página {current_page}: {total_rows_visible}")
            except Exception as e:
                self.logger.debug(f"Falha ao contar linhas visíveis: {e}")

            # Extrai apenas primeiras linhas (sempre renderizadas, mesmo com virtualização)
            rows_extracted = 0
            for idx in range(MAX_ROWS_PER_PAGE):
                try:
                    # SOLUÇÃO VIRTUALIZAÇÃO: Scroll a cada 40 linhas para forçar rendering
                    if idx > 0 and idx % 40 == 0:
                        try:
                            # Scroll para a linha atual para forçar virtualização renderizar mais linhas
                            page.evaluate(f"""
                                const row = document.querySelector('table tbody tr.ant-table-row:nth-child({idx})');
                                if (row) row.scrollIntoView({{block: 'center'}});
                            """)
                            page.wait_for_timeout(400)  # MUDANÇA 3: Aumentado de 200ms para 400ms
                            self.logger.debug(f"Scroll executado na linha {idx} para forçar rendering")
                        except Exception:
                            pass  # Não crítico se scroll falhar

                    # Fresh locator para cada linha (evita stale references)
                    row = page.locator('table tbody tr.ant-table-row').nth(idx)

                    # Verifica se linha existe e está visível (timeout curto: 500ms)
                    try:
                        is_visible = row.is_visible(timeout=500)
                    except PlaywrightTimeoutError:
                        # Linha não existe = acabaram as linhas da página
                        break

                    if not is_visible:
                        # Linha existe mas não está visível (fim das linhas renderizadas)
                        break

                    # Verifica se é linha placeholder (vazia)
                    try:
                        class_attr = row.get_attribute('class', timeout=500) or ''
                        if 'ant-table-placeholder' in class_attr:
                            continue
                    except PlaywrightTimeoutError:
                        continue

                    # Busca célula com padrão de MAC address
                    cells = row.locator('td')
                    cell_count = cells.count()
                    mac_encontrado = None
                    nome_dispositivo = ''

                    # Procura MAC nas primeiras 5 colunas (otimização)
                    for cell_idx in range(min(5, cell_count)):
                        try:
                            cell_text = cells.nth(cell_idx).inner_text(timeout=500).strip()
                            # Valida formato MAC: XX:XX:XX:XX:XX:XX
                            if re.match(r'^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$', cell_text):
                                mac_encontrado = cell_text
                                break
                        except PlaywrightTimeoutError:
                            continue

                    # Se encontrou MAC, tenta capturar o nome/comentário (colunas subsequentes)
                    if mac_encontrado:
                        # Busca "Comentário"/"Comment" nas colunas restantes
                        # Geralmente está após o MAC (colunas 1-10)
                        for cell_idx in range(min(10, cell_count)):
                            try:
                                cell_text = cells.nth(cell_idx).inner_text(timeout=500).strip()
                                # Se não for o MAC e não for vazio, pode ser o comentário
                                if cell_text and cell_text != mac_encontrado and not re.match(r'^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$', cell_text):
                                    # Ignora células com valores típicos de status, números puros (IDs), ou símbolos
                                    is_status = cell_text.lower() in ['ativo', 'inativo', 'online', 'offline', '-', '—']
                                    is_pure_number = re.match(r'^\d+(\.\d+)?$', cell_text)  # Números puros (ex: "1", "22", "144")

                                    if len(cell_text) > 1 and not is_status and not is_pure_number:
                                        nome_dispositivo = cell_text
                                        break
                            except PlaywrightTimeoutError:
                                continue

                    # Adiciona MAC se encontrado e não duplicado
                    # CAMADA 2.1: Armazena página onde foi encontrado
                    if mac_encontrado and mac_encontrado not in macs_set:
                        macs_set.add(mac_encontrado)
                        macs_encontrados.append({
                            'mac': mac_encontrado,
                            'nome': nome_dispositivo,  # Nome/Comentário capturado
                            'page': current_page  # Rastreia página correta
                        })
                        rows_extracted += 1
                        # MELHORIA 3: Log INFO para cada MAC extraído (rastreabilidade total)
                        nome_log = f' - "{nome_dispositivo}"' if nome_dispositivo else ''
                        self.logger.info(f"✓ MAC extraído: {mac_encontrado}{nome_log} (página {current_page}, linha {idx+1})")
                    elif mac_encontrado:  # MUDANÇA 1: MAC duplicado - agora logamos
                        duplicados_count += 1
                        self.logger.debug(f"MAC duplicado ignorado: {mac_encontrado} (já encontrado anteriormente)")

                except PlaywrightTimeoutError:
                    # Timeout = linha não existe mais (fim das linhas)
                    break
                except Exception as e:
                    # Outros erros: loga mas continua
                    self.logger.debug(f"Erro ao extrair linha {idx}: {e}")
                    continue

            self.logger.info(f"Página {page_num}/{total_pages}: {rows_extracted} MACs extraídos ({len(macs_encontrados)} total)")

            # Controle de páginas vazias consecutivas
            if rows_extracted == 0:
                consecutive_empty_pages += 1
                self.logger.warning(f"Página vazia detectada ({consecutive_empty_pages}/{MAX_CONSECUTIVE_EMPTY})")
            else:
                consecutive_empty_pages = 0  # Resetar contador

            # Se já visitamos todas as páginas esperadas, encerrar
            if page_num >= total_pages:
                self.logger.info(f"Todas as {total_pages} páginas foram visitadas.")
                break

            # Tentar avançar para próxima página
            if not self._tentar_avancar_pagina(page, current_page, total_pages):
                self.logger.info("Não foi possível avançar para próxima página. Encerrando extração.")
                break

        # Volta para primeira página antes de processar dispositivos
        self._go_to_first_page(page)

        # Aguarda navegação completar e tabela estabilizar
        page.wait_for_timeout(800)
        try:
            page.wait_for_selector('table tbody tr.ant-table-row', timeout=5000)
            self.logger.info("Navegador resetado para página 1 após extração ✓")
        except PlaywrightTimeoutError:
            self.logger.warning("Timeout aguardando tabela após reset para página 1")

        # MUDANÇA 4: Log final com resumo detalhado (incluindo duplicados)
        total_processados = len(macs_encontrados) + duplicados_count
        self.logger.info("=" * 60)
        self.logger.info("=== RESUMO DA EXTRAÇÃO ===")
        self.logger.info(f"MACs únicos encontrados: {len(macs_encontrados)}")
        self.logger.info(f"MACs duplicados ignorados: {duplicados_count}")
        self.logger.info(f"Total de linhas processadas: {total_processados}")
        self.logger.info(f"Páginas visitadas: {page_num}")
        self.logger.info("=" * 60)

        # MELHORIA 4: Lista completa de MACs encontrados (rastreabilidade total)
        self.logger.info("")
        self.logger.info("=== LISTA COMPLETA DE MACs EXTRAÍDOS ===")
        for i, device_info in enumerate(macs_encontrados, 1):
            mac = device_info['mac']
            page_found = device_info['page']
            self.logger.info(f"{i:3d}. {mac} (página {page_found})")
        self.logger.info("=" * 60)

        # SOLUÇÃO VIRTUALIZAÇÃO: Restaurar zoom para 100%
        try:
            page.evaluate("document.body.style.zoom = '1.0'")
            page.wait_for_timeout(300)
            self.logger.info("Zoom restaurado para 100% ✓")
        except Exception as e:
            self.logger.warning(f"Falha ao restaurar zoom: {e}")

        # CAMADA 2.1: Retorna lista com páginas rastreadas corretamente
        return macs_encontrados

    def _tentar_avancar_pagina(self, page: Page, current_page: int, total_pages: int) -> bool:
        """
        Tenta avançar para próxima página usando múltiplas estratégias de fallback.

        Args:
            page: Página do Playwright
            current_page: Número da página atual
            total_pages: Total de páginas esperado

        Returns:
            bool: True se conseguiu avançar, False caso contrário
        """
        # Estratégia 1: Botão "próxima página"
        try:
            next_button = page.locator('.ant-table-pagination .ant-pagination-next')

            if next_button.count() > 0:
                button_class = next_button.first.get_attribute('class') or ''

                # Se não está desabilitado OU se ainda temos páginas para visitar
                if 'ant-pagination-disabled' not in button_class:
                    self.logger.debug(f"Estratégia 1: Clicando em 'próxima página'")
                    previous_page = current_page
                    next_button.first.click()

                    try:
                        self._wait_for_page_change(page, previous_page, timeout=10000)
                        page.wait_for_selector('table tbody tr.ant-table-row', timeout=5000)
                        return True
                    except PlaywrightTimeoutError:
                        self.logger.warning("Timeout após clicar em 'próxima página'. Tentando fallback...")
                        # Não retornar False ainda, tentar outras estratégias

        except Exception as e:
            self.logger.debug(f"Estratégia 1 falhou: {e}")

        # Estratégia 2: Clicar diretamente no número da próxima página
        if current_page < total_pages:
            try:
                next_page_num = current_page + 1
                self.logger.debug(f"Estratégia 2: Clicando diretamente na página {next_page_num}")

                page_button = page.locator(f'.ant-pagination-item[title="{next_page_num}"]')
                if page_button.count() > 0 and page_button.first.is_visible(timeout=2000):
                    previous_page = current_page
                    page_button.first.click()

                    try:
                        self._wait_for_page_change(page, previous_page, timeout=10000)
                        page.wait_for_selector('table tbody tr.ant-table-row', timeout=5000)
                        return True
                    except PlaywrightTimeoutError:
                        self.logger.warning(f"Timeout após clicar na página {next_page_num}")

            except Exception as e:
                self.logger.debug(f"Estratégia 2 falhou: {e}")

        # Estratégia 3: Force click no botão "próxima página" (mesmo se desabilitado)
        try:
            next_button = page.locator('.ant-table-pagination .ant-pagination-next')
            if next_button.count() > 0 and current_page < total_pages:
                self.logger.debug(f"Estratégia 3: Force click em 'próxima página'")
                previous_page = current_page
                next_button.first.click(force=True)

                page.wait_for_timeout(1000)  # Aguardar processamento

                new_page = self._get_current_page_number(page)
                if new_page != previous_page:
                    self.logger.info(f"Force click funcionou! Avançou para página {new_page}")
                    return True

        except Exception as e:
            self.logger.debug(f"Estratégia 3 falhou: {e}")

        # Se chegou aqui, nenhuma estratégia funcionou
        self.logger.warning(f"Todas as estratégias de navegação falharam na página {current_page}")
        return False

    def _extrair_todos_dispositivos(self, page: Page) -> List[Dict]:
        dispositivos: List[Dict] = []
        seen_macs: Set[str] = set()
        visited_pages: Set[int] = set()

        while True:
            try:
                page.wait_for_selector('table tbody tr.ant-table-row', timeout=15000)
            except PlaywrightTimeoutError:
                self.logger.warning("Timeout aguardando linhas da tabela de dispositivos.")
                break

            rows_locator = page.locator('table tbody tr.ant-table-row')
            row_count = rows_locator.count()
            current_page = self._get_current_page_number(page)
            visited_pages.add(current_page)

            if row_count == 0:
                self.logger.debug("Tabela de dispositivos está vazia na página atual.")

            for idx in range(row_count):
                row = rows_locator.nth(idx)
                try:
                    class_attr = row.get_attribute('class') or ''
                    if 'ant-table-placeholder' in class_attr:
                        continue
                    cells = row.locator('td')
                    cell_count = cells.count()
                    if cell_count == 0:
                        continue
                    mac = ''
                    nome = ''
                    for cell_idx in range(cell_count):
                        cell_text = cells.nth(cell_idx).inner_text().strip()
                        if not mac and re.match(r'^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$', cell_text):
                            mac = cell_text
                            continue
                        if mac and not nome:
                            nome = cell_text
                            break
                    if not mac:
                        if cell_count >= 2:
                            mac = cells.nth(1).inner_text().strip()
                        if cell_count > 2:
                            nome = cells.nth(2).inner_text().strip()
                    if not mac or mac in seen_macs:
                        continue
                    seen_macs.add(mac)
                    dispositivos.append({
                        'mac': mac,
                        'nome': nome,
                        'page': current_page,
                    })
                except Exception as e:
                    self.logger.warning(f"Erro ao extrair linha da tabela de dispositivos: {e}")
                    continue

            next_button = page.locator('.ant-table-pagination .ant-pagination-next')
            if next_button.count() == 0:
                break
            class_attr = next_button.first.get_attribute('class') or ''
            if 'ant-pagination-disabled' in class_attr:
                break
            previous_page = current_page
            next_button.first.click()
            try:
                self._wait_for_page_change(page, previous_page, timeout=10000)
                page.wait_for_selector('table tbody tr.ant-table-row', timeout=15000)
            except PlaywrightTimeoutError:
                self.logger.warning("Timeout aguardando mudança de página na listagem de dispositivos.")
                break
            new_page = self._get_current_page_number(page)
            if new_page in visited_pages:
                break

        self._go_to_first_page(page)
        return dispositivos

    def _extrair_dispositivo_especifico(self, page: Page, mac: str) -> List[Dict]:
        linha = self._localizar_linha_dispositivo(page, mac)
        if not linha:
            self.logger.warning(f"Dispositivo {mac} não encontrado na listagem.")
            return []
        nome = ''
        try:
            cells = linha.locator('td')
            if cells.count() > 2:
                nome = cells.nth(2).inner_text().strip()
        except Exception:
            pass
        current_page = self._get_current_page_number(page)
        return [{
            'mac': mac,
            'nome': nome,
            'page': current_page,
        }]

    def _atualizar_dns_dispositivo(
        self,
        page: Page,
        device_id: str,
        dominio_origem: str,
        dominio_destino: str,
        device_info: Optional[Dict] = None,
    ) -> Dict:
        from pathlib import Path
        from cadastros.utils import substituir_dominio_em_url, extrair_dominio_de_url

        debug_dir = Path('logs/Reseller/debug_screenshots')
        debug_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"[DEVICE:{device_id}] Iniciando atualização DNS...")

        playlist_drawer: Optional[Locator] = None
        playlist_results: List[Dict] = []
        urls_encontradas: List[str] = []
        urls_atualizadas: List[str] = []
        mensagens_erro: List[str] = []

        try:
            self._close_all_drawers(page)

            # CAMADA 2.2: Corrigir bug falsy - navegação deve funcionar para página 0 ou 1
            if device_info:
                target_page = device_info.get('page')
                if target_page is not None and target_page >= 1:
                    self.logger.debug(
                        f"[DEVICE:{device_id}] Navegando para página {target_page} "
                        "onde dispositivo foi encontrado"
                    )
                    self._go_to_page(page, target_page)
                    page.wait_for_timeout(300)  # Aguarda estabilizar

            row = self._localizar_linha_dispositivo(page, device_id)
            if not row:
                return {
                    'status': 'erro',
                    'erro': f'Dispositivo {device_id} não encontrado na tabela'
                }

            try:
                page.screenshot(path=str(debug_dir / f'{device_id}_1_row_found.png'))
            except Exception:
                pass

            action_button = None
            action_selectors = [
                'button[aria-label="more"]',
                'button.ant-dropdown-trigger',
                '.ant-dropdown-link',
                'button:has(svg)',
                'td:last-child button',
            ]
            for selector in action_selectors:
                try:
                    candidate = row.locator(selector).first
                    if candidate.count() and candidate.is_visible(timeout=1000):
                        action_button = candidate
                        self.logger.debug(
                            f"[DEVICE:{device_id}] Botão de ações encontrado: {selector}"
                        )
                        break
                except Exception:
                    continue
            if not action_button:
                return {
                    'status': 'erro',
                    'erro': 'Botão de ações não encontrado na linha do dispositivo'
                }

            action_button.click()
            page.wait_for_timeout(400)
            try:
                page.screenshot(path=str(debug_dir / f'{device_id}_2_action_menu_opened.png'))
            except Exception:
                pass

            menu_selectors = [
                'text=Playlist',
                'text="Playlist"',
                '.ant-dropdown-menu-item:has-text("Playlist")',
                '[role="menuitem"]:has-text("Playlist")',
                'li:has-text("Playlist")',
                'text=Lista de reprodução',
                '.ant-dropdown-menu-item:has-text("Lista")',
            ]

            playlist_menu_clicked = False
            visible_before_playlist = len(self._get_visible_drawers(page)) or 0
            for menu_selector in menu_selectors:
                try:
                    menu_item = page.locator(menu_selector).first
                    if menu_item.count() and menu_item.is_visible(timeout=2000):
                        menu_item.click()
                        playlist_menu_clicked = True
                        self.logger.debug(
                            f"[DEVICE:{device_id}] Menu 'Playlist' selecionado via {menu_selector}"
                        )

                        # Aguardar dropdown do dispositivo fechar completamente
                        page.wait_for_timeout(300)
                        try:
                            page.wait_for_selector('.ant-dropdown-menu:visible', state='hidden', timeout=2000)
                            self.logger.debug(f"[DEVICE:{device_id}] Dropdown do dispositivo fechado ✓")
                        except Exception:
                            pass  # Não crítico se já fechou
                        page.wait_for_timeout(200)

                        break
                except Exception:
                    continue
            if not playlist_menu_clicked:
                return {
                    'status': 'erro',
                    'erro': 'Item "Playlist" não encontrado no menu de ações do dispositivo'
                }

            playlist_drawer = self._wait_for_top_drawer(
                page,
                min_visible=max(visible_before_playlist + 1, 1)
            )
            page.wait_for_timeout(300)

            try:
                playlist_drawer.locator('table tbody tr.ant-table-row').first.wait_for(
                    state='visible',
                    timeout=5000
                )
            except PlaywrightTimeoutError:
                pass

            try:
                page.screenshot(path=str(debug_dir / f'{device_id}_3_playlist_drawer.png'))
            except Exception:
                pass

            rows_locator = playlist_drawer.locator('table tbody tr.ant-table-row')
            if rows_locator.count() == 0:
                return {
                    'status': 'pulado',
                    'erro': 'Dispositivo não possui playlist cadastrada'
                }

            visited_playlist_pages: Set[int] = set()

            def process_playlist_row(row_index: int) -> Dict:
                nonlocal playlist_drawer

                row_locator = playlist_drawer.locator('table tbody tr.ant-table-row').nth(row_index)
                try:
                    class_attr = row_locator.get_attribute('class') or ''
                    if 'ant-table-placeholder' in class_attr:
                        return {'status': 'pulado', 'erro': 'Linha placeholder'}
                except Exception:
                    pass

                playlist_name = ''
                try:
                    cells = row_locator.locator('td')
                    if cells.count() > 1:
                        playlist_name = cells.nth(1).inner_text().strip()
                except Exception:
                    pass

                action_button_playlist = None
                playlist_action_selectors = [
                    'button.ant-dropdown-trigger',
                    'button:has([aria-label="ellipsis"])',
                    'td:last-child button',
                ]
                for selector in playlist_action_selectors:
                    try:
                        candidate = row_locator.locator(selector).first
                        if candidate.count() and candidate.is_visible(timeout=1000):
                            action_button_playlist = candidate
                            break
                    except Exception:
                        continue
                if not action_button_playlist:
                    return {
                        'status': 'erro',
                        'erro': 'Botão de ações da playlist não encontrado'
                    }

                action_button_playlist.click()
                page.wait_for_timeout(800)  # Aumentado de 400ms para 800ms
                try:
                    # Aguardar dropdown da playlist estabilizar
                    page.locator('.ant-dropdown-menu:visible').last.wait_for(state='visible', timeout=2000)
                    self.logger.debug(f"[DEVICE:{device_id}] Dropdown da playlist estabilizado ✓")
                except Exception:
                    pass
                try:
                    page.screenshot(path=str(debug_dir / f'{device_id}_3a_playlist_actions_opened.png'))
                except Exception:
                    pass

                edit_selectors = [
                    '[role="menuitem"]:has-text("Editar")',
                    '[role="menuitem"]:has-text("Edit")',
                    'li.ant-dropdown-menu-item:has-text("Editar")',
                    'li.ant-dropdown-menu-item:has-text("Edit")',
                    '[data-menu-id*="edit"]',
                ]
                edit_menu_item = None

                # Localizar o dropdown visível MAIS RECENTE (último aberto)
                try:
                    dropdown_menu = page.locator('.ant-dropdown-menu:visible').last
                    self.logger.debug(f"[DEVICE:{device_id}] Dropdown menu localizado")
                except Exception as e:
                    self.logger.error(f"[DEVICE:{device_id}] Erro ao localizar dropdown: {e}")
                    dropdown_menu = page  # Fallback para página inteira

                for selector in edit_selectors:
                    try:
                        # Buscar DENTRO do dropdown específico, não na página inteira
                        candidate = dropdown_menu.locator(selector).first
                        if candidate.count() and candidate.is_visible(timeout=2000):
                            edit_menu_item = candidate
                            page.wait_for_timeout(500)
                            self.logger.info(f"[DEVICE:{device_id}] Item 'Editar/Edit' encontrado: {selector}")
                            break
                    except Exception:
                        continue
                if not edit_menu_item:
                    return {
                        'status': 'erro',
                        'erro': 'Item "Editar/Edit" não encontrado no dropdown da playlist'
                    }

                visible_before_edit = len(self._get_visible_drawers(page))
                edit_drawer: Optional[Locator] = None
                try:
                    # Screenshot antes de clicar em "Editar/Edit"
                    try:
                        page.screenshot(path=str(debug_dir / f'{device_id}_3b_before_edit_click.png'))
                        self.logger.debug(f"[DEVICE:{device_id}] Preparando para clicar em 'Editar/Edit'")
                    except Exception:
                        pass

                    edit_menu_item.click(force=True)

                    # Screenshot logo após click
                    try:
                        page.screenshot(path=str(debug_dir / f'{device_id}_3c_after_edit_click.png'))
                    except Exception:
                        pass
                    edit_drawer = self._wait_for_top_drawer(
                        page,
                        min_visible=max(visible_before_edit + 1, 1)
                    )
                    page.wait_for_timeout(300)

                    form_locator = edit_drawer.locator('form#add-playlist')
                    form_locator.wait_for(state='visible', timeout=5000)

                    all_inputs: List[Locator] = []
                    try:
                        all_inputs = form_locator.locator('input').all()
                    except Exception:
                        all_inputs = []

                    url_field: Optional[Locator] = None
                    url_selectors = [
                        'input#add-playlist_url',
                        'input[name="url"]',
                        'input[name="playlist_url"]',
                        'input[name="playlistUrl"]',
                        'input[placeholder*="URL"]',
                        'input[placeholder*="url"]',
                        'input[placeholder*="http"]',
                        'input[type="url"]',
                        'input[type="text"]',
                    ]
                    for url_selector in url_selectors:
                        try:
                            candidate = form_locator.locator(url_selector).first
                            if candidate.count() and candidate.is_visible(timeout=2000):
                                url_field = candidate
                                break
                        except Exception:
                            continue
                    if not url_field and all_inputs:
                        for input_candidate in all_inputs:
                            try:
                                if input_candidate.is_visible():
                                    value = (input_candidate.input_value() or '').strip()
                                    if value.startswith('http://') or value.startswith('https://'):
                                        url_field = input_candidate
                                        break
                            except Exception:
                                continue
                    if not url_field:
                        self.logger.warning(
                            f"[DEVICE:{device_id}] Campo de URL não encontrado na playlist '{playlist_name}'."
                        )
                        return {
                            'status': 'erro',
                            'erro': 'Campo de URL não encontrado durante a edição da playlist'
                        }

                    url_field.wait_for(state='visible', timeout=3000)
                    url_atual = (url_field.input_value() or '').strip()
                    if not url_atual:
                        return {
                            'status': 'erro',
                            'erro': 'Campo de URL está vazio'
                        }

                    dominio_atual = extrair_dominio_de_url(url_atual)
                    if not dominio_atual:
                        return {
                            'status': 'erro',
                            'dns_encontrado': url_atual,
                            'erro': 'Não foi possível extrair domínio da URL atual'
                        }
                    if dominio_atual != dominio_origem:
                        self.logger.warning(
                            f"[DEVICE:{device_id}] Playlist '{playlist_name}' com domínio {dominio_atual} diferente do esperado {dominio_origem}."
                        )
                        return {
                            'status': 'pulado',
                            'dns_encontrado': url_atual,
                            'erro': f'Domínio atual ({dominio_atual}) diferente do domínio origem informado ({dominio_origem})'
                        }

                    try:
                        url_nova = substituir_dominio_em_url(url_atual, dominio_origem, dominio_destino)
                    except ValueError as exc:
                        return {
                            'status': 'erro',
                            'dns_encontrado': url_atual,
                            'erro': f'Erro ao substituir domínio: {exc}'
                        }

                    self.logger.info(
                        f"[DEVICE:{device_id}] Playlist '{playlist_name}' atualizando URL para {url_nova}"
                    )

                    url_field.click()
                    url_field.fill('')
                    page.wait_for_timeout(200)
                    url_field.fill(url_nova)
                    page.wait_for_timeout(200)
                    try:
                        page.screenshot(path=str(debug_dir / f'{device_id}_5_url_updated.png'))
                    except Exception:
                        pass

                    save_button = form_locator.locator(
                        'button[type="submit"], button:has-text("Save"), button:has-text("Salvar"), button.ant-btn-primary'
                    ).first
                    if not (save_button.count() and save_button.is_visible()):
                        return {
                            'status': 'erro',
                            'dns_encontrado': url_atual,
                            'dns_atualizado': url_nova,
                            'erro': 'Botão de salvar não encontrado no formulário de edição'
                        }

                    save_button.click()
                    try:
                        self._wait_for_drawer_close(page, expected_visible=visible_before_edit)
                    except PlaywrightTimeoutError:
                        return {
                            'status': 'erro',
                            'dns_encontrado': url_atual,
                            'dns_atualizado': url_nova,
                            'erro': 'Timeout aguardando fechamento do drawer de edição'
                        }

                    page.wait_for_timeout(400)

                    return {
                        'status': 'sucesso',
                        'dns_encontrado': url_atual,
                        'dns_atualizado': url_nova,
                        'playlist': playlist_name or ''
                    }

                finally:
                    if edit_drawer and len(self._get_visible_drawers(page)) > visible_before_edit:
                        try:
                            self._close_drawer(page, edit_drawer)
                        except Exception:
                            pass

            while True:
                current_playlist_page = self._get_active_page_number_from_drawer(playlist_drawer)
                if current_playlist_page in visited_playlist_pages:
                    break
                visited_playlist_pages.add(current_playlist_page)

                rows_locator = playlist_drawer.locator('table tbody tr.ant-table-row')
                row_count = rows_locator.count()
                for idx in range(row_count):
                    result = process_playlist_row(idx)
                    playlist_results.append(result)
                    if result.get('dns_encontrado'):
                        urls_encontradas.append(result['dns_encontrado'])
                    if result.get('dns_atualizado'):
                        urls_atualizadas.append(result['dns_atualizado'])
                    if result.get('erro'):
                        mensagens_erro.append(result['erro'])

                next_button = playlist_drawer.locator('.ant-pagination-next:not(.ant-pagination-disabled)')
                if next_button.count() == 0:
                    break
                previous_page = current_playlist_page
                next_button.first.click()
                page.wait_for_timeout(400)
                for _ in range(20):
                    new_page = self._get_active_page_number_from_drawer(playlist_drawer)
                    if new_page != previous_page:
                        break
                    page.wait_for_timeout(200)
                try:
                    playlist_drawer.locator('table tbody tr.ant-table-row').first.wait_for(
                        state='visible',
                        timeout=5000
                    )
                except Exception:
                    pass

            if not playlist_results:
                return {
                    'status': 'pulado',
                    'erro': 'Nenhuma playlist processada'
                }

            if any(result['status'] == 'erro' for result in playlist_results):
                return {
                    'status': 'erro',
                    'dns_encontrado': ' | '.join(urls_encontradas),
                    'dns_atualizado': ' | '.join(urls_atualizadas),
                    'erro': ' | '.join(mensagens_erro) or 'Erro ao atualizar ao menos uma playlist'
                }

            if all(result['status'] == 'pulado' for result in playlist_results):
                return {
                    'status': 'pulado',
                    'dns_encontrado': ' | '.join(urls_encontradas),
                    'erro': ' | '.join(mensagens_erro) or 'Todas as playlists foram puladas'
                }

            return {
                'status': 'sucesso',
                'dns_encontrado': ' | '.join(urls_encontradas),
                'dns_atualizado': ' | '.join(urls_atualizadas),
            }

        except PlaywrightTimeoutError as e:
            try:
                page.screenshot(path=str(debug_dir / f'{device_id}_ERROR_timeout.png'))
            except Exception:
                pass
            return {
                'status': 'erro',
                'erro': f'Timeout: {str(e)}'
            }
        except Exception as e:
            try:
                page.screenshot(path=str(debug_dir / f'{device_id}_ERROR_exception.png'))
            except Exception:
                pass
            self.logger.exception(f"[DEVICE:{device_id}] Erro durante atualização DNS")
            return {
                'status': 'erro',
                'erro': str(e)
            }
        finally:
            if playlist_drawer:
                try:
                    self._close_drawer(page, playlist_drawer)
                except Exception:
                    pass
            self._close_all_drawers(page)
