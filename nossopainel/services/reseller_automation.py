"""
Automação de Reseller com Selenium + CapSolver

Implementação 100% funcional baseada no projeto de referência.
Usa Selenium para login automático e API Dream TV para operações de dispositivos.

Fluxo:
1. Login automático com Selenium + CapSolver (bypass de reCAPTCHA)
2. Extração do JWT do localStorage
3. Uso da API Dream TV para listar/atualizar dispositivos
"""

import os
import time
import json
from typing import Optional, Dict, List, Any
from datetime import datetime

# Django imports
from django.contrib.auth.models import User
from django.utils import timezone

# Selenium imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Local imports
from nossopainel.models import (
    Aplicativo, ContaReseller, TarefaMigracaoDNS,
    DispositivoMigracaoDNS, ConfiguracaoAutomacao
)
from nossopainel.utils import decrypt_password, validar_formato_dominio, substituir_dominio_em_url, extrair_dominio_de_url
from nossopainel.services.capsolver_integration import CapSolver, CapSolverException
from nossopainel.services.lib import logger, jwt_utils, api_client, credentials_manager, dream_tv_api


class DreamTVSeleniumAutomation:
    """
    Automação completa do painel DreamTV usando Selenium + CapSolver API

    Baseado na implementação 100% funcional do projeto de referência.
    """

    LOGIN_URL = 'https://reseller.dreamtv.life/#/login'
    DASHBOARD_URL = 'https://reseller.dreamtv.life/#/dashboard'

    def __init__(self, user: User, aplicativo: Aplicativo):
        """
        Inicializa a automação

        Args:
            user: Usuário Django que está executando a automação
            aplicativo: Aplicativo (DreamTV) para o qual a automação será executada
        """
        self.user = user
        self.aplicativo = aplicativo
        self.driver = None
        self.jwt = None
        self.conta_reseller = None
        self.capsolver_used = False

        # Logger contextual
        self.log = logger.get_automation_logger(user=user)
        self.log.info("=" * 80)
        self.log.info(f"DreamTVSeleniumAutomation inicializado para user={user.username}, app={aplicativo.nome}")
        self.log.info("=" * 80)

        # Obter/criar conta reseller
        self._obter_conta()

        # Configurações de debug
        self.debug_mode = self._get_debug_mode()
        self.log.info(f"🔧 Modo Debug: {self.debug_mode} - Browser será {'VISÍVEL' if self.debug_mode else 'OCULTO (headless)'}")

    def _obter_conta(self) -> None:
        """Obtém ou cria conta reseller para o usuário"""
        self.log.debug(f"Obtendo conta reseller para app={self.aplicativo.nome}")

        self.conta_reseller, created = credentials_manager.get_or_create_conta_reseller(
            aplicativo=self.aplicativo,
            usuario=self.user
        )

        if created:
            self.log.warning("Conta reseller criada mas sem credenciais. Configure antes de usar.")

        # Validar conta
        is_valid, error = credentials_manager.validate_conta_reseller(self.conta_reseller)
        if not is_valid:
            self.log.error(f"Conta reseller inválida: {error}")
            raise ValueError(f"Conta reseller inválida: {error}")

    def _get_debug_mode(self) -> bool:
        """Verifica se modo debug está ativado para o usuário"""
        try:
            config = ConfiguracaoAutomacao.objects.filter(user=self.user).first()
            if config:
                self.log.debug(f"ConfiguracaoAutomacao encontrada: debug_headless_mode={config.debug_headless_mode}")
                return config.debug_headless_mode
            else:
                self.log.debug("ConfiguracaoAutomacao não encontrada, usando debug_mode=False por padrão")
            return False
        except Exception as e:
            self.log.warning(f"Erro ao buscar configuração de debug: {e}, usando debug_mode=False por padrão")
            return False

    def setup_driver(self):
        """Configura o driver do Chrome com Selenium"""
        self.log.info(f"Configurando navegador Chrome (headless={not self.debug_mode})")
        logger.log_browser_action(self.log, 'setup', f'headless={not self.debug_mode}')

        # Verificar disponibilidade de display em modo visível (Linux)
        if self.debug_mode:
            display = os.environ.get('DISPLAY')
            if display:
                self.log.info(f"✓ Display encontrado: DISPLAY={display}")
            else:
                self.log.warning("⚠ DISPLAY environment não configurado! Browser pode não aparecer em sistemas Linux.")

        chrome_options = Options()

        # Configurar caminho do Chrome baseado no sistema operacional
        import platform
        system = platform.system()

        # Detectar WSL (Windows Subsystem for Linux)
        is_wsl = False
        if system == 'Linux':
            # Método 1: Verificar se /mnt/c existe (típico do WSL)
            if os.path.exists('/mnt/c'):
                is_wsl = True
            # Método 2: Verificar /proc/version contém "microsoft"
            elif os.path.exists('/proc/version'):
                try:
                    with open('/proc/version', 'r') as f:
                        if 'microsoft' in f.read().lower():
                            is_wsl = True
                except Exception:
                    pass

        if is_wsl:
            # WSL: PRIORIZAR Chrome do Linux (mais compatível e estável)
            self.log.info("WSL detectado - priorizando Chrome nativo do Linux")

            linux_chrome_paths = [
                '/usr/bin/google-chrome',
                '/usr/bin/google-chrome-stable',
                '/usr/bin/chromium',
                '/usr/bin/chromium-browser',
                '/snap/bin/chromium'
            ]

            chrome_found = False
            for chrome_path in linux_chrome_paths:
                if os.path.exists(chrome_path):
                    chrome_options.binary_location = chrome_path
                    self.log.info(f"✓ Chrome do Linux encontrado no WSL: {chrome_path}")
                    chrome_found = True
                    break

            # Fallback: Chrome do Windows (menos recomendado, pode ser instável)
            if not chrome_found:
                self.log.warning("Chrome do Linux não encontrado, tentando Chrome do Windows via /mnt/c/")
                chrome_binary = "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"

                if os.path.exists(chrome_binary):
                    chrome_options.binary_location = chrome_binary
                    self.log.warning(f"⚠ Usando Chrome do Windows via WSL: {chrome_binary} (pode ser instável)")
                    self.log.warning("⚠ RECOMENDAÇÃO: Instale Chrome do Linux com: sudo apt install google-chrome-stable")
                else:
                    # Tentar x86
                    chrome_binary_x86 = "/mnt/c/Program Files (x86)/Google/Chrome/Application/chrome.exe"
                    if os.path.exists(chrome_binary_x86):
                        chrome_options.binary_location = chrome_binary_x86
                        self.log.warning(f"⚠ Usando Chrome do Windows (x86) via WSL: {chrome_binary_x86} (pode ser instável)")
                    else:
                        self.log.error("Chrome não encontrado. Instale Chrome do Linux: sudo apt install google-chrome-stable")
                        raise FileNotFoundError("Chrome não encontrado no WSL. Execute: sudo apt install google-chrome-stable")

        elif system == 'Windows' or 'MINGW' in platform.platform() or 'MSYS' in platform.platform():
            # Windows nativo/Git Bash - usar Chrome do Windows
            chrome_binary = "C:/Program Files/Google/Chrome/Application/chrome.exe"

            if os.path.exists(chrome_binary):
                chrome_options.binary_location = chrome_binary
                self.log.info(f"Chrome encontrado: {chrome_binary}")
            else:
                # Tentar path alternativo (32-bit)
                chrome_binary_x86 = "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"

                if os.path.exists(chrome_binary_x86):
                    chrome_options.binary_location = chrome_binary_x86
                    self.log.info(f"Chrome encontrado (x86): {chrome_binary_x86}")
                else:
                    self.log.error("Chrome não encontrado no Windows. Instale o Google Chrome em: https://www.google.com/chrome/")
                    raise FileNotFoundError("Chrome binary não encontrado. Instale o Google Chrome.")
        else:
            # Linux nativo - buscar Chrome instalado
            possible_chrome_paths = [
                '/usr/bin/google-chrome',
                '/usr/bin/google-chrome-stable',
                '/usr/bin/chromium',
                '/usr/bin/chromium-browser',
                '/snap/bin/chromium'
            ]

            chrome_found = False
            for chrome_path in possible_chrome_paths:
                if os.path.exists(chrome_path):
                    chrome_options.binary_location = chrome_path
                    self.log.info(f"Chrome encontrado (Linux): {chrome_path}")
                    chrome_found = True
                    break

            if not chrome_found:
                self.log.error("Chrome não encontrado no Linux. Instale com: sudo apt-get install chromium-browser")
                raise FileNotFoundError("Chrome binary não encontrado. Execute: sudo apt-get install chromium-browser")

        # Headless mode (desativado se debug_mode=True)
        if not self.debug_mode:
            chrome_options.add_argument('--headless=new')  # Novo modo headless (Chrome 112+)
            chrome_options.add_argument('--disable-gpu')  # GPU apenas em headless
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--remote-debugging-pipe')  # CRÍTICO para WSL headless
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')  # Previne crashes no WSL
            chrome_options.add_argument('--window-size=1920,1080')
        else:
            # Configurações para modo visível
            self.log.debug("Modo visível: mantendo aceleração GPU ativa")
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--start-maximized')

        # Anti-detecção
        chrome_options.add_argument('--no-sandbox')
        if self.debug_mode:
            # Adicionar --disable-dev-shm-usage apenas em modo visível (já adicionado em headless)
            chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')

        # User-Agent apropriado para o sistema operacional
        if system == 'Windows' or 'MINGW' in platform.platform() or 'MSYS' in platform.platform():
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        else:
            user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

        chrome_options.add_argument(f'--user-agent={user_agent}')

        # Opções experimentais
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        # ===== FIX: Argumentos específicos para WSL =====
        # Chrome do Windows executado via WSL precisa de argumentos específicos
        if is_wsl:
            chrome_options.add_argument('--disable-software-rasterizer')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-setuid-sandbox')
            chrome_options.add_argument('--enable-features=NetworkService,NetworkServiceInProcess')
            chrome_options.add_argument('--disable-crash-reporter')
            self.log.info("✓ Argumentos WSL adicionados para compatibilidade Chrome/Windows")

        # ===== FIX: Configurar user-data-dir para WSL/Git Bash =====
        # Chrome do Windows não consegue escrever em /tmp/ do WSL
        # Solução: usar diretório do Windows acessível
        import tempfile
        if system == 'Windows' or 'MINGW' in platform.platform() or 'MSYS' in platform.platform() or is_wsl:
            # Ambientes Windows/Git Bash/WSL: usar diretório do Windows
            try:
                if is_wsl:
                    # WSL: usar /tmp/ do WSL (Chrome do Windows pode acessar)
                    windows_temp = tempfile.mkdtemp(prefix='chrome-selenium-', dir='/tmp')
                else:
                    # Git Bash/Windows: usar C:/Users/.../AppData/Local/Temp/
                    localappdata = os.environ.get('LOCALAPPDATA', os.path.expanduser('~/AppData/Local'))
                    windows_temp = os.path.join(localappdata, 'Temp', 'chrome-selenium-data')
                    # Criar diretório se não existir
                    os.makedirs(windows_temp, exist_ok=True)

                chrome_options.add_argument(f'--user-data-dir={windows_temp}')
                self.log.info(f"✓ user-data-dir configurado (WSL/Windows fix): {windows_temp}")
            except Exception as e:
                self.log.warning(f"⚠ Erro ao configurar user-data-dir: {e}, Chrome usará diretório padrão")
        else:
            # Linux nativo: /tmp/ funciona normalmente
            try:
                linux_temp = tempfile.mkdtemp(prefix='chrome-selenium-')
                chrome_options.add_argument(f'--user-data-dir={linux_temp}')
                self.log.info(f"✓ user-data-dir configurado (Linux): {linux_temp}")
            except Exception as e:
                self.log.warning(f"⚠ Erro ao configurar user-data-dir: {e}, Chrome usará diretório padrão")

        # Instalar ChromeDriver automaticamente
        self.log.debug("Instalando ChromeDriver via webdriver-manager")
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

        # Remover propriedade webdriver do navigator
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        self.log.info("Navegador Chrome configurado com sucesso")
        logger.log_browser_action(self.log, 'setup', 'Chrome WebDriver pronto')

    def _atualizar_progresso_login(self, etapa: str):
        """
        Atualiza campo login_progresso para feedback visual em tempo real

        Args:
            etapa: Etapa atual ('conectando', 'pagina_carregada', etc.)
        """
        try:
            self.conta_reseller.login_progresso = etapa
            self.conta_reseller.save(update_fields=['login_progresso'])
            self.log.debug(f"Progresso atualizado: {etapa}")
        except Exception as e:
            self.log.warning(f"Erro ao atualizar progresso (não crítico): {e}")

    def fazer_login_automatico(self, force_new_login: bool = False) -> bool:
        """
        Realiza login automático com Selenium + CapSolver

        Args:
            force_new_login: Se True, força novo login mesmo se JWT existir

        Returns:
            True se login foi bem-sucedido
        """
        self.log.info("=" * 80)
        self.log.info("Iniciando processo de login automático")
        self.log.info("=" * 80)

        # Verificar se já tem JWT válido (exceto se force_new_login=True)
        if not force_new_login:
            self.log.debug("Verificando JWT existente...")
            jwt_existente = credentials_manager.get_jwt_from_conta(self.conta_reseller)

            if jwt_existente:
                self.log.debug("JWT encontrado, validando com API...")
                if api_client.validate_jwt(jwt_existente):
                    self.log.info("JWT existente válido! Login não necessário.")
                    self.jwt = jwt_existente
                    self._atualizar_progresso_login('concluido')
                    return True
                else:
                    self.log.warning("JWT existente inválido, realizando novo login...")
                    credentials_manager.invalidate_session(self.conta_reseller)

        try:
            # Obter credenciais
            email, senha = credentials_manager.get_reseller_credentials(self.conta_reseller)
            self.log.info(f"Credenciais obtidas: email={email}")

            # ETAPA 1: Conectando ao painel
            self._atualizar_progresso_login('conectando')

            # Configurar navegador se ainda não foi
            if not self.driver:
                self.setup_driver()

            # Verificar API Key do CapSolver
            capsolver_api_key = credentials_manager.get_capsolver_api_key()
            self.log.info("CapSolver API Key configurada")

            # Navegar para página de login
            self.log.info(f"Navegando para {self.LOGIN_URL}...")
            logger.log_browser_action(self.log, 'navigate', self.LOGIN_URL)
            self.driver.get(self.LOGIN_URL)

            # Aguardar React carregar
            self.log.debug("Aguardando React montar...")
            WebDriverWait(self.driver, 120).until(
                lambda driver: driver.execute_script(
                    "const root = document.getElementById('root'); return root && root.children.length > 0;"
                )
            )

            # ETAPA 1 CONCLUÍDA: Página carregada
            self._atualizar_progresso_login('pagina_carregada')

            # Aguardar formulário de login
            self.log.debug("Aguardando formulário de login...")
            email_input = self._find_email_input()
            password_input = self._find_password_input()

            # Preencher credenciais
            self.log.info("Preenchendo credenciais...")
            self._fill_input_slowly(email_input, email)
            self._fill_input_slowly(password_input, senha)

            # Detectar e resolver reCAPTCHA
            recaptcha_info = self._detectar_recaptcha()

            if recaptcha_info['hasRecaptcha'] and recaptcha_info['siteKey']:
                self.log.warning("reCAPTCHA detectado!")
                self.log.info(f"Site Key: {recaptcha_info['siteKey']}")

                # ETAPA 2: Resolvendo reCAPTCHA
                self._atualizar_progresso_login('resolvendo_captcha')

                # Resolver com CapSolver
                token = self._resolver_recaptcha(recaptcha_info['siteKey'], capsolver_api_key)
                self.capsolver_used = True

                # Injetar solução
                self._injetar_token_recaptcha(token)

                # ETAPA 2 CONCLUÍDA: reCAPTCHA resolvido
                self._atualizar_progresso_login('captcha_resolvido')

                # Aguardar validação
                self.log.debug("Aguardando validação do reCAPTCHA...")
                time.sleep(3)
            else:
                self.log.info("Nenhum reCAPTCHA detectado")
                # Se não há CAPTCHA, pula etapa 2
                self._atualizar_progresso_login('captcha_resolvido')

            # ETAPA 3: Validando credenciais
            self._atualizar_progresso_login('validando')

            # Clicar no botão de login
            self._clicar_botao_login()

            # Aguardar redirecionamento para dashboard
            self.log.info("Aguardando redirecionamento para dashboard...")
            WebDriverWait(self.driver, 120).until(
                lambda driver: '/dashboard' in driver.current_url or '#/dashboard' in driver.current_url
            )

            self.log.info("Login bem-sucedido!")

            # Extrair JWT do localStorage
            self._extrair_jwt()

            # Salvar JWT na conta
            credentials_manager.save_jwt_to_conta(self.conta_reseller, self.jwt)

            # Atualizar último login
            self.conta_reseller.ultimo_login = timezone.now()
            self.conta_reseller.save()

            self.log.info("JWT salvo com sucesso na conta reseller")

            # ETAPA 3 CONCLUÍDA: Login concluído
            self._atualizar_progresso_login('concluido')

            if self.capsolver_used:
                self.log.info("CapSolver foi utilizado - custo: ~$0.003")

            return True

        except Exception as e:
            self.log.error(f"Erro durante login automático: {e}")
            logger.log_exception(self.log, e, "fazer_login_automatico")

            # Marcar erro no progresso
            self._atualizar_progresso_login('erro')

            # Screenshot de erro
            if self.driver:
                try:
                    screenshot_path = f'/tmp/dreamtv_login_error_{int(time.time())}.png'
                    self.driver.save_screenshot(screenshot_path)
                    self.log.debug(f"Screenshot de erro salvo: {screenshot_path}")
                except:
                    pass

            raise

    def _find_email_input(self):
        """Encontra campo de email"""
        email_selectors = [
            'input[type="email"]',
            'input[id*="username" i]',
            'input[name*="email" i]',
            '.ant-input[type="text"]'
        ]

        for selector in email_selectors:
            try:
                elem = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                self.log.debug(f"Campo de email encontrado: {selector}")
                return elem
            except:
                continue

        raise Exception("Campo de email não encontrado")

    def _find_password_input(self):
        """Encontra campo de senha"""
        try:
            elem = self.driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
            self.log.debug("Campo de senha encontrado")
            return elem
        except:
            raise Exception("Campo de senha não encontrado")

    def _fill_input_slowly(self, element, text: str):
        """Preenche input lentamente (simula digitação humana)"""
        element.click()
        element.clear()
        for char in text:
            element.send_keys(char)
            time.sleep(0.05)

    def _detectar_recaptcha(self) -> Dict[str, Any]:
        """Detecta presença de reCAPTCHA na página"""
        self.log.debug("Verificando presença de reCAPTCHA...")

        recaptcha_info = self.driver.execute_script("""
            const siteKeyElement = document.querySelector('[data-sitekey]');
            const recaptchaFrame = document.querySelector('iframe[src*="recaptcha"]');

            let siteKey = null;
            if (siteKeyElement) {
                siteKey = siteKeyElement.getAttribute('data-sitekey');
            } else if (recaptchaFrame) {
                const src = recaptchaFrame.src;
                const match = src.match(/k=([^&]+)/);
                if (match) siteKey = match[1];
            }

            return {
                hasRecaptcha: !!(siteKeyElement || recaptchaFrame),
                siteKey: siteKey
            };
        """)

        return recaptcha_info

    def _resolver_recaptcha(self, sitekey: str, api_key: str) -> str:
        """Resolve reCAPTCHA usando CapSolver"""
        self.log.info("Iniciando resolução de reCAPTCHA com CapSolver...")

        capsolver = CapSolver(api_key=api_key)
        token = capsolver.solve_recaptcha(self.LOGIN_URL, sitekey)

        self.log.info(f"reCAPTCHA resolvido! Token: {token[:50]}...")
        return token

    def _injetar_token_recaptcha(self, token: str):
        """Injeta token do reCAPTCHA na página (implementação multi-camada 100% funcional)"""
        self.log.info("Injetando solução do reCAPTCHA na página...")

        callback_result = self.driver.execute_script(f"""
            const results = {{
                responseFieldSet: false,
                callbackFound: false,
                callbackTriggered: false,
                method: null
            }};

            // Step 1: Set response field (MANTER HIDDEN!)
            let responseField = document.querySelector('#g-recaptcha-response');
            if (!responseField) {{
                responseField = document.querySelector('[name="g-recaptcha-response"]');
            }}
            if (!responseField) {{
                responseField = document.querySelector('textarea[name="g-recaptcha-response"]');
            }}

            if (responseField) {{
                responseField.value = '{token}';
                responseField.innerHTML = '{token}';
                // NÃO MUDAR DISPLAY! Deve permanecer hidden
                results.responseFieldSet = true;
                console.log('✓ Response field set (kept hidden)');
            }}

            // Step 2: Method A - Try data-callback attribute (MOST RELIABLE)
            const recaptchaElement = document.querySelector('[data-callback]');
            if (recaptchaElement) {{
                const callbackName = recaptchaElement.getAttribute('data-callback');
                if (callbackName && typeof window[callbackName] === 'function') {{
                    console.log(`✓ Found named callback: ${{callbackName}}`);
                    try {{
                        window[callbackName]('{token}');
                        results.callbackFound = true;
                        results.callbackTriggered = true;
                        results.method = 'data-callback';
                        console.log('✓ Callback triggered via data-callback');
                        return results;
                    }} catch (e) {{
                        console.log('✗ Error calling data-callback:', e.message);
                    }}
                }}
            }}

            // Step 3: Method B - Search ___grecaptcha_cfg for callback
            if (typeof window.___grecaptcha_cfg !== 'undefined' && window.___grecaptcha_cfg.clients) {{
                const clients = window.___grecaptcha_cfg.clients;

                for (let clientId in clients) {{
                    const client = clients[clientId];
                    if (!client) continue;

                    results.callbackFound = true;

                    // Try multiple callback path patterns
                    const tryPaths = [
                        // Pattern 1: Search all nested objects for callback
                        () => {{
                            const searchCallback = (obj, depth = 0) => {{
                                if (depth > 5) return null;
                                for (let key in obj) {{
                                    if (obj[key] && typeof obj[key] === 'object') {{
                                        if (typeof obj[key].callback === 'function') {{
                                            return obj[key].callback;
                                        }}
                                        const found = searchCallback(obj[key], depth + 1);
                                        if (found) return found;
                                    }}
                                }}
                                return null;
                            }};
                            return searchCallback(client);
                        }},
                        // Pattern 2: Common property names
                        () => client.L?.L?.callback || client.D?.D?.callback ||
                              client.o?.o?.callback || client.aa?.l?.callback,
                        // Pattern 3: First indexed property array
                        () => {{
                            const keys = Object.keys(client);
                            for (let key of keys) {{
                                if (Array.isArray(client[key]) && client[key][0]?.callback) {{
                                    return client[key][0].callback;
                                }}
                            }}
                            return null;
                        }}
                    ];

                    for (let i = 0; i < tryPaths.length; i++) {{
                        try {{
                            const callback = tryPaths[i]();
                            if (typeof callback === 'function') {{
                                console.log(`✓ Found callback using pattern ${{i + 1}}`);
                                callback('{token}');
                                results.callbackTriggered = true;
                                results.method = `grecaptcha_cfg_pattern_${{i + 1}}`;
                                console.log('✓ Callback triggered successfully');
                                return results;
                            }}
                        }} catch (e) {{
                            console.log(`✗ Pattern ${{i + 1}} failed:`, e.message);
                        }}
                    }}
                }}
            }}

            // Step 4: Method C - Dispatch events as fallback
            if (responseField && !results.callbackTriggered) {{
                console.log('⚠ Callback not found, trying event dispatch...');
                try {{
                    const events = ['input', 'change', 'blur'];
                    events.forEach(eventType => {{
                        const event = new Event(eventType, {{ bubbles: true, cancelable: true }});
                        responseField.dispatchEvent(event);
                    }});
                    results.method = 'event_dispatch';
                    console.log('✓ Events dispatched');
                }} catch (e) {{
                    console.log('✗ Event dispatch failed:', e.message);
                }}
            }}

            return results;
        """)

        self.log.debug(f"Resultado da injeção: {callback_result}")

        if not callback_result.get('callbackTriggered'):
            self.log.warning("Callback pode não ter sido acionado corretamente")
        else:
            self.log.info(f"Callback acionado com sucesso via {callback_result.get('method')}")

    def _clicar_botao_login(self):
        """Clica no botão de login"""
        self.log.info("Procurando botão de login...")

        button_selectors = [
            'button[type="submit"]',
            'button.ant-btn-primary',
            'form button'
        ]

        login_button = None
        for selector in button_selectors:
            try:
                login_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                self.log.debug(f"Botão encontrado: {selector}")
                break
            except:
                continue

        if not login_button:
            raise Exception("Botão de login não encontrado")

        self.log.info("Clicando no botão de login...")
        logger.log_browser_action(self.log, 'click', 'Login button')
        login_button.click()

    def _extrair_jwt(self):
        """Extrai JWT do localStorage"""
        self.log.info("Extraindo JWT do localStorage...")
        time.sleep(2)  # Aguardar JWT estar disponível

        self.jwt = self.driver.execute_script("return localStorage.getItem('JWT');")

        if not self.jwt:
            raise Exception("JWT não encontrado no localStorage")

        self.log.info("JWT obtido com sucesso!")
        self.log.debug(f"JWT: {self.jwt[:50]}...")

        # Decodificar JWT para log
        payload = jwt_utils.decode_jwt(self.jwt)
        if payload:
            self.log.debug(f"JWT payload: user_id={payload.get('id')}, type={payload.get('type')}")

    def verificar_sessao_valida(self) -> bool:
        """
        Verifica se sessão atual é válida

        Returns:
            True se sessão válida, False caso contrário
        """
        self.log.info("Verificando validade da sessão...")

        # Obter JWT da conta
        jwt = credentials_manager.get_jwt_from_conta(self.conta_reseller)

        if not jwt:
            self.log.warning("Nenhum JWT encontrado na conta")
            return False

        # Validar JWT com API
        is_valid = api_client.validate_jwt(jwt)

        if is_valid:
            self.log.info("Sessão válida!")
            self.jwt = jwt
        else:
            self.log.warning("Sessão inválida")
            credentials_manager.invalidate_session(self.conta_reseller)

        return is_valid

    def executar_migracao(self, tarefa_id: int) -> None:
        """
        Executa migração DNS usando API Dream TV

        Args:
            tarefa_id: ID da tarefa de migração
        """
        self.log.info("=" * 80)
        self.log.info(f"Iniciando execução de migração DNS - Tarefa ID: {tarefa_id}")
        self.log.info("=" * 80)

        try:
            # Obter tarefa
            tarefa = TarefaMigracaoDNS.objects.get(id=tarefa_id)
            tarefa.status = 'processando'
            tarefa.data_inicio = timezone.now()
            tarefa.save()

            self.log.info(f"Tarefa: {tarefa}")
            self.log.info(f"Origem: {tarefa.dominio_origem}")
            self.log.info(f"Destino: {tarefa.dominio_destino}")
            self.log.info(f"Escopo: {'Todos os dispositivos' if not tarefa.mac_alvo else f'MAC: {tarefa.mac_alvo}'}")

            # Verificar/obter JWT válido
            if not self.jwt:
                self.log.info("Nenhum JWT em memória, verificando sessão...")
                if not self.verificar_sessao_valida():
                    self.log.info("Sessão inválida, realizando novo login...")
                    if not self.fazer_login_automatico():
                        raise Exception("Falha no login automático")

            # Criar cliente API
            self.log.info("Criando cliente API Dream TV...")
            api = dream_tv_api.DreamTVAPI(jwt=self.jwt, logger=self.log)

            # Obter dispositivos via API
            self.log.info("Listando dispositivos via API...")
            dispositivos = self._obter_dispositivos_alvo(api, tarefa)

            if not dispositivos:
                self.log.warning("Nenhum dispositivo encontrado para migração")
                tarefa.status = 'concluido'
                tarefa.mensagem_erro = 'Nenhum dispositivo encontrado'
                tarefa.data_fim = timezone.now()
                tarefa.save()
                return

            self.log.info(f"Total de dispositivos a processar: {len(dispositivos)}")
            tarefa.total_dispositivos = len(dispositivos)
            tarefa.save()

            # Processar cada dispositivo
            dispositivos_processados = 0
            dispositivos_sucesso = 0
            dispositivos_erro = 0
            dispositivos_pulados = 0

            # Atualizar etapa inicial
            tarefa.etapa_atual = 'processando'
            tarefa.mensagem_progresso = f'Processando {len(dispositivos)} dispositivo(s)...'
            tarefa.save(update_fields=['etapa_atual', 'mensagem_progresso'])

            for idx, dispositivo in enumerate(dispositivos, 1):
                self.log.info(f"[{idx}/{len(dispositivos)}] Processando dispositivo MAC: {dispositivo['mac']}")

                mac = dispositivo['mac']
                self._processar_dispositivo(
                    api=api,
                    dispositivo=dispositivo,
                    tarefa=tarefa
                )

                # Obter status real do dispositivo processado
                disp_migracao = DispositivoMigracaoDNS.objects.filter(
                    tarefa=tarefa,
                    device_id=mac
                ).last()

                dispositivos_processados += 1
                if disp_migracao:
                    if disp_migracao.status == 'sucesso':
                        dispositivos_sucesso += 1
                    elif disp_migracao.status == 'pulado':
                        dispositivos_pulados += 1
                    elif disp_migracao.status == 'erro':
                        dispositivos_erro += 1

                # Atualizar progresso em tempo real
                tarefa.processados = dispositivos_processados
                tarefa.sucessos = dispositivos_sucesso
                tarefa.falhas = dispositivos_erro
                tarefa.pulados = dispositivos_pulados
                tarefa.progresso_percentual = int((dispositivos_processados / len(dispositivos)) * 100)
                tarefa.mensagem_progresso = f'Processando {dispositivos_processados}/{len(dispositivos)} dispositivos...'
                tarefa.save(update_fields=['processados', 'sucessos', 'falhas', 'pulados', 'progresso_percentual', 'mensagem_progresso'])

                self.log.info(f"Progresso: {tarefa.progresso_percentual}% ({dispositivos_processados}/{len(dispositivos)})")

            # Finalizar tarefa
            tarefa.status = 'concluida'
            tarefa.etapa_atual = 'concluida'
            tarefa.mensagem_progresso = f'Migração concluída! Total: {dispositivos_processados} | Sucesso: {dispositivos_sucesso} | Erro: {dispositivos_erro} | Pulados: {dispositivos_pulados}'
            tarefa.concluida_em = timezone.now()
            tarefa.save(update_fields=['status', 'etapa_atual', 'mensagem_progresso', 'concluida_em'])

            self.log.info("=" * 80)
            self.log.info(f"Migração DNS concluída!")
            self.log.info(f"Total: {dispositivos_processados} | Sucesso: {dispositivos_sucesso} | Erro: {dispositivos_erro}")
            self.log.info("=" * 80)

        except Exception as e:
            self.log.error(f"Erro durante migração DNS: {e}")
            logger.log_exception(self.log, e, "executar_migracao")

            # Atualizar tarefa com erro
            try:
                tarefa.status = 'erro'
                tarefa.etapa_atual = 'erro'
                tarefa.mensagem_progresso = f'Erro durante migração: {str(e)}'
                tarefa.erro_geral = str(e)
                tarefa.concluida_em = timezone.now()
                tarefa.save(update_fields=['status', 'etapa_atual', 'mensagem_progresso', 'erro_geral', 'concluida_em'])
            except:
                pass

            raise

    def _normalizar_device_do_cache(self, cached_device: Dict) -> Dict:
        """
        Transforma device do cache (frontend) para estrutura da API

        Cache: {device_id: MAC, nome_dispositivo, playlists}
        API:   {id: MAC, mac: MAC, reseller_activation: {comment}, playlists}

        Nota: device_id no cache contém o MAC real (ex: 00:1A:79:XX:XX:XX)
        IMPORTANTE: Preserva playlists do cache para evitar chamadas desnecessárias à API
        """
        return {
            'id': cached_device.get('device_id'),  # MAC address
            'mac': cached_device.get('device_id'),  # MAC address
            'reseller_activation': {
                'comment': cached_device.get('nome_dispositivo', '')
            },
            'playlists': cached_device.get('playlists', [])  # Preservar playlists do cache
        }

    def _obter_dispositivos_alvo(self, api: dream_tv_api.DreamTVAPI, tarefa: TarefaMigracaoDNS) -> List[Dict]:
        """Obtém lista de dispositivos a serem processados (prioriza cache, fallback para API)"""

        # ===== OTIMIZAÇÃO v2.0: TENTAR USAR CACHE PRIMEIRO =====
        if tarefa.cached_devices:
            try:
                import json
                cached_devices = json.loads(tarefa.cached_devices)

                self.log.info(f"[Cache] Usando {len(cached_devices)} devices do cache (0 chamadas à API)")

                # Se MAC específico, filtrar pelo MAC
                if tarefa.mac_alvo:
                    dispositivos_filtrados = [
                        device for device in cached_devices
                        if device.get('device_id') == tarefa.mac_alvo
                    ]
                    self.log.info(f"[Cache] {len(dispositivos_filtrados)} device(s) com MAC={tarefa.mac_alvo}")
                    return [self._normalizar_device_do_cache(d) for d in dispositivos_filtrados]

                # Filtrar devices pelo domínio origem
                dispositivos_filtrados = []
                for device in cached_devices:
                    for playlist in device.get('playlists', []):
                        if playlist.get('dominio', '').lower() == tarefa.dominio_origem.lower():
                            dispositivos_filtrados.append(device)
                            break

                self.log.info(f"[Cache] {len(dispositivos_filtrados)} devices com domínio '{tarefa.dominio_origem}'")

                # Limpar cache após uso para economizar espaço no banco
                tarefa.cached_devices = None
                tarefa.save(update_fields=['cached_devices'])

                return [self._normalizar_device_do_cache(d) for d in dispositivos_filtrados]

            except Exception as e:
                self.log.warning(f"[Cache] Erro ao usar cache: {e}, buscando da API")

        # ===== FALLBACK: BUSCAR DA API (comportamento original) =====
        self.log.info("[API] Cache não disponível, obtendo dispositivos via API...")

        dispositivos = []
        page = 1
        limit = 100

        try:
            # Se MAC específico, buscar apenas ele
            if tarefa.mac_alvo:
                self.log.info(f"Buscando dispositivo específico: MAC={tarefa.mac_alvo}")
                result = api.list_devices(
                    page=1,
                    limit=1,
                    search={'mac': tarefa.mac_alvo}
                )

                if result.get('rows'):
                    dispositivos = result['rows']
                    self.log.info(f"Dispositivo encontrado: {dispositivos[0]['mac']}")
                else:
                    self.log.warning(f"Dispositivo MAC={tarefa.mac_alvo} não encontrado")

                return dispositivos

            # Listar todos os dispositivos e filtrar por domínio origem
            self.log.info(f"Listando dispositivos com domínio origem: {tarefa.dominio_origem}")

            dispositivos_filtrados = []
            total_listados = 0

            while True:
                self.log.debug(f"Buscando página {page} (limit={limit})...")
                result = api.list_devices(page=page, limit=limit)

                if not result.get('rows'):
                    break

                total_listados += len(result['rows'])

                # Filtrar: Verificar se dispositivo possui playlist com dominio_origem
                for device in result['rows']:
                    device_id = device.get('id')
                    device_mac = device.get('mac', 'N/A')

                    try:
                        # Listar playlists do dispositivo
                        playlists = api.list_playlists(device_id=device_id)

                        # Verificar se alguma playlist possui o dominio_origem
                        tem_dominio_origem = False
                        for playlist in playlists:
                            url = playlist.get('url', '')
                            if url:
                                dominio = extrair_dominio_de_url(url)
                                if dominio and dominio.lower() == tarefa.dominio_origem.lower():
                                    tem_dominio_origem = True
                                    break

                        # Adicionar dispositivo apenas se tiver domínio origem
                        if tem_dominio_origem:
                            dispositivos_filtrados.append(device)
                            self.log.debug(f"✓ Dispositivo {device_mac} possui domínio origem, adicionado")
                        else:
                            self.log.debug(f"✗ Dispositivo {device_mac} não possui domínio origem, ignorado")

                    except Exception as e:
                        self.log.warning(f"Erro ao verificar playlists do dispositivo {device_mac}: {e}")
                        # Em caso de erro, incluir dispositivo (será tratado no processamento)
                        dispositivos_filtrados.append(device)

                    # Rate limiting entre verificações (reduzido de 0.2 para 0.05)
                    time.sleep(0.05)

                # Verificar se há mais páginas
                total_count = result.get('count', 0)
                if total_listados >= total_count:
                    break

                page += 1
                time.sleep(0.1)  # Rate limiting entre páginas (reduzido de 0.5 para 0.1)

            self.log.info(f"Total de dispositivos listados: {total_listados}")
            self.log.info(f"Dispositivos com domínio origem '{tarefa.dominio_origem}': {len(dispositivos_filtrados)}")
            return dispositivos_filtrados

        except Exception as e:
            self.log.error(f"Erro ao obter dispositivos via API: {e}")
            logger.log_exception(self.log, e, "_obter_dispositivos_alvo")
            raise

    def _processar_dispositivo(
        self,
        api: dream_tv_api.DreamTVAPI,
        dispositivo: Dict,
        tarefa: TarefaMigracaoDNS
    ) -> bool:
        """
        Processa um dispositivo individual (atualiza DNS via API)

        Args:
            api: Cliente API Dream TV
            dispositivo: Dict com dados do dispositivo
            tarefa: Tarefa de migração

        Returns:
            True se sucesso, False se erro
        """
        mac = dispositivo['mac']
        device_id = dispositivo['id']

        self.log.info(f"Processando dispositivo: MAC={mac}, ID={device_id}")

        try:
            # Listar playlists do dispositivo (priorizar cache, fallback para API)
            if 'playlists' in dispositivo and dispositivo.get('playlists'):
                # Usar playlists do cache (já disponíveis)
                playlists = dispositivo['playlists']
                self.log.debug(f"[Cache] Usando {len(playlists)} playlists do cache para device {device_id}")
            else:
                # Buscar playlists da API (comportamento original)
                self.log.debug(f"[API] Listando playlists do dispositivo {device_id} via API...")
                playlists = api.list_playlists(device_id=device_id)

            # DNS inicial será capturado dentro do loop (primeira playlist a ser migrada)
            dns_inicial = None

            # Criar registro de dispositivo na migração com o comentário do dispositivo
            disp_migracao = DispositivoMigracaoDNS.objects.create(
                tarefa=tarefa,
                device_id=mac,
                nome_dispositivo=dispositivo.get('reseller_activation', {}).get('comment', ''),
                dns_encontrado='',  # Será atualizado com a URL da playlist correta
                status='processando'
            )

            if not playlists:
                self.log.warning(f"Dispositivo {mac} não possui playlists")
                disp_migracao.status = 'pulado'
                disp_migracao.mensagem_erro = 'Nenhuma playlist encontrada'
                disp_migracao.processado_em = timezone.now()
                disp_migracao.save()
                return False

            self.log.info(f"Dispositivo {mac}: {len(playlists)} playlist(s) encontrada(s)")

            # Processar cada playlist
            playlists_atualizadas = 0

            for playlist in playlists:
                playlist_id = playlist['id']
                url_atual = playlist['url']
                nome = playlist.get('name', f'Playlist {playlist_id}')

                self.log.debug(f"Playlist '{nome}': {url_atual}")

                # Extrair domínio da URL atual
                dominio_atual = extrair_dominio_de_url(url_atual)

                if not dominio_atual:
                    self.log.warning(f"Não foi possível extrair domínio da URL: {url_atual}")
                    continue

                # Verificar se domínio atual corresponde ao domínio de origem
                if dominio_atual.lower() != tarefa.dominio_origem.lower():
                    self.log.debug(f"Domínio atual ({dominio_atual}) diferente do origem ({tarefa.dominio_origem}), pulando...")
                    continue

                # Capturar DNS inicial (primeira playlist que será migrada)
                if dns_inicial is None:
                    dns_inicial = url_atual
                    self.log.debug(f"DNS inicial capturado: {dns_inicial}")

                # Substituir domínio
                url_nova = substituir_dominio_em_url(
                    url_completa=url_atual,
                    dominio_origem=tarefa.dominio_origem,
                    dominio_destino=tarefa.dominio_destino
                )

                if url_nova == url_atual:
                    self.log.debug(f"URL não foi alterada, pulando...")
                    continue

                self.log.info(f"Atualizando playlist '{nome}':")
                self.log.info(f"  Antes: {url_atual}")
                self.log.info(f"  Depois: {url_nova}")

                # Atualizar via API (usar deviceId numérico da playlist)
                device_id_numerico = playlist.get('deviceId', device_id)
                api.update_playlist(id=playlist_id, device_id=device_id_numerico, url=url_nova)
                playlists_atualizadas += 1

                # Salvar DNS atualizado (capturar apenas primeira URL atualizada)
                if not disp_migracao.dns_atualizado:
                    disp_migracao.dns_atualizado = url_nova
                    disp_migracao.save(update_fields=['dns_atualizado'])

                self.log.info(f"Playlist '{nome}' atualizada com sucesso!")

            # Atualizar dns_encontrado com a URL da primeira playlist migrada
            if dns_inicial:
                disp_migracao.dns_encontrado = dns_inicial
                disp_migracao.save(update_fields=['dns_encontrado'])

            # Atualizar status do dispositivo
            if playlists_atualizadas > 0:
                disp_migracao.status = 'sucesso'
                disp_migracao.processado_em = timezone.now()
                disp_migracao.save()
                self.log.info(f"Dispositivo {mac}: {playlists_atualizadas} playlist(s) atualizada(s) ✓")
                return True
            else:
                disp_migracao.status = 'pulado'
                disp_migracao.mensagem_erro = 'Nenhuma playlist precisou ser atualizada'
                disp_migracao.processado_em = timezone.now()
                disp_migracao.save()
                self.log.warning(f"Dispositivo {mac}: Nenhuma playlist precisou ser atualizada")
                return False

        except Exception as e:
            self.log.error(f"Erro ao processar dispositivo {mac}: {e}")
            logger.log_exception(self.log, e, f"_processar_dispositivo(mac={mac})")

            # Atualizar status com erro
            disp_migracao.status = 'erro'
            disp_migracao.mensagem_erro = str(e)[:500]
            disp_migracao.processado_em = timezone.now()
            disp_migracao.save()

            return False

    def close(self):
        """Fecha o navegador"""
        if self.driver:
            self.log.info("Fechando navegador Chrome")
            logger.log_browser_action(self.log, 'close', 'Encerrando sessão')
            try:
                self.driver.quit()
                self.log.info("Navegador fechado com sucesso")
            except Exception as e:
                self.log.warning(f"Erro ao fechar navegador: {e}")
