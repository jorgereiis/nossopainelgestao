"""
Dream TV API Client - Cliente completo para API Dream TV

Este módulo fornece uma interface Python para todos os endpoints da API Dream TV.
Organizado por categorias para facilitar o uso.

Uso:
    from lib.dream_tv_api import DreamTVAPI

    api = DreamTVAPI(jwt='seu-jwt-aqui')

    # Obter perfil
    profile = api.get_profile()

    # Listar dispositivos
    devices = api.list_devices(page=1, limit=10)

    # Ativar dispositivo
    api.activate_device(mac='00:1A:2B:3C:4D:5E', package_id=1)
"""

import requests
import json
from typing import Optional, Dict, Any, List, Union
from datetime import datetime


class APIError(Exception):
    """Exceção customizada para erros da API Dream TV"""

    def __init__(self, message: str, code: Optional[int] = None, endpoint: Optional[str] = None):
        self.message = message
        self.code = code
        self.endpoint = endpoint

        error_msg = f"API Error"
        if code:
            error_msg += f" {code}"
        if endpoint:
            error_msg += f" on {endpoint}"
        error_msg += f": {message}"

        super().__init__(error_msg)


class DreamTVAPI:
    """
    Cliente completo para API Dream TV

    Attributes:
        jwt (str): Token JWT para autenticação
        base_url (str): URL base da API
        timeout (int): Timeout para requisições em segundos
    """

    def __init__(self, jwt: str, base_url: str = 'https://api.dreamtv.life', timeout: int = 60, logger=None):
        """
        Inicializa o cliente da API

        Args:
            jwt: Token JWT para autenticação
            base_url: URL base da API (default: https://api.dreamtv.life)
            timeout: Timeout para requisições em segundos (default: 60)
            logger: Logger instance para debug (opcional)
        """
        self.jwt = jwt
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.headers = {
            'Authorization': jwt,
            'Content-Type': 'application/json'
        }
        self.log = logger

        if self.log:
            self.log.debug(f"DreamTVAPI inicializado: base_url={base_url}, timeout={timeout}s")

    # ==================== MÉTODOS INTERNOS ====================

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Método genérico para fazer requisições HTTP

        Args:
            method: Método HTTP (GET, POST, PUT, DELETE)
            endpoint: Endpoint da API (ex: /reseller/devices)
            **kwargs: Argumentos adicionais para requests

        Returns:
            Response object do requests

        Raises:
            APIError: Se houver erro na requisição
        """
        # Construir URL completa
        url = f"{self.base_url}{endpoint}"

        # Adicionar timeout se não especificado
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.timeout

        if self.log:
            params_str = str(kwargs.get('params', {})) if 'params' in kwargs else 'none'
            self.log.debug(f"Requisição: {method} {endpoint} (timeout={kwargs['timeout']}s, params={params_str})")

        try:
            # Fazer requisição
            response = requests.request(method, url, headers=self.headers, **kwargs)

            if self.log:
                self.log.debug(f"Resposta: status={response.status_code}, size={len(response.content)} bytes")

            return response

        except requests.exceptions.Timeout:
            timeout_used = kwargs.get('timeout', self.timeout)
            if self.log:
                self.log.error(f"Timeout após {timeout_used}s em {method} {endpoint}")
            raise APIError(f"Request timeout after {timeout_used}s", endpoint=endpoint)
        except requests.exceptions.ConnectionError:
            if self.log:
                self.log.error(f"Erro de conexão em {method} {endpoint}")
            raise APIError("Connection error - check your internet connection", endpoint=endpoint)
        except Exception as e:
            if self.log:
                self.log.error(f"Erro inesperado em {method} {endpoint}: {str(e)}")
            raise APIError(f"Request failed: {str(e)}", endpoint=endpoint)

    def _handle_response(self, response: requests.Response, endpoint: str = '') -> Any:
        """
        Processa resposta da API

        Args:
            response: Response object do requests
            endpoint: Endpoint chamado (para logging de erros)

        Returns:
            Dados da resposta (geralmente dict ou list)

        Raises:
            APIError: Se a resposta contém erro
        """
        # Tratamento especial para erro 429 (Rate Limiting)
        if response.status_code == 429:
            # Extrair tempo de espera do header Retry-After (se disponível)
            retry_after = response.headers.get('Retry-After', '60')
            wait_seconds = int(retry_after) if retry_after.isdigit() else 60

            error_msg = (
                f"API Rate Limit atingido (429 Too Many Requests). "
                f"A API bloqueou as requisições por excesso de chamadas. "
                f"Aguarde ~{wait_seconds}s antes de tentar novamente."
            )

            if self.log:
                self.log.warning(f"[{endpoint}] {error_msg}")

            raise APIError(
                error_msg,
                code=429,
                endpoint=endpoint
            )

        # Tentar parsear JSON
        try:
            data = response.json()
            if self.log:
                self.log.debug(f"JSON parseado de {endpoint}: {json.dumps(data, indent=2)[:500]}...")
        except json.JSONDecodeError:
            # Capturar conteúdo bruto da resposta para debug
            raw_content = response.text[:500]
            if self.log:
                self.log.error(f"Resposta inválida (não é JSON) de {endpoint}")
                self.log.error(f"Status: {response.status_code}")
                self.log.error(f"Conteúdo bruto: {raw_content}")

            # Mensagem de erro específica para 404
            if response.status_code == 404:
                raise APIError(
                    f"Endpoint não encontrado: {endpoint}. Verifique se o endpoint e método HTTP estão corretos.",
                    code=response.status_code,
                    endpoint=endpoint
                )

            raise APIError(
                f"Resposta inválida (não é JSON) - Status {response.status_code}: {raw_content[:100]}",
                code=response.status_code,
                endpoint=endpoint
            )

        # Verificar se há erro na resposta
        if isinstance(data, dict):
            # Verificar campo 'error'
            if data.get('error', False):
                error_msg = data.get('message', 'Unknown error')
                if self.log:
                    self.log.error(f"API retornou erro em {endpoint}: {error_msg}")
                raise APIError(
                    error_msg,
                    code=response.status_code,
                    endpoint=endpoint
                )

            # Retornar dados dentro de 'message' se existir
            if 'message' in data:
                extracted = data['message']
                if self.log:
                    self.log.debug(f"Extraindo 'message' de {endpoint}: {json.dumps(extracted, indent=2)[:300]}...")
                return extracted

        # Retornar dados completos
        if self.log:
            self.log.debug(f"Retornando dados completos de {endpoint}")
        return data

    # ==================== AUTENTICAÇÃO & PERFIL ====================

    def get_profile(self) -> Dict[str, Any]:
        """
        Obtém perfil completo do reseller

        Returns:
            Dict com dados do reseller:
                - id, name, surname, email
                - balance, credits
                - phone, company, country, address
                - gold_status, disabled, created_at, etc

        Exemplo:
            profile = api.get_profile()
            print(f"Nome: {profile['name']}")
            print(f"Saldo: R$ {profile['balance']:.2f}")
        """
        if self.log:
            self.log.debug("Obtendo perfil do reseller...")

        response = self._request('GET', '/reseller')
        data = self._handle_response(response, '/reseller')

        if self.log:
            self.log.debug(f"Dados recebidos em get_profile(): keys={list(data.keys()) if isinstance(data, dict) else 'not a dict'}")

        # Dados do reseller estão em data.reseller
        if isinstance(data, dict) and 'reseller' in data:
            profile = data['reseller']
            if self.log:
                self.log.debug(f"Perfil extraído: name={profile.get('name', 'N/A')}, total_activations={profile.get('total_activations', 'N/A')}, balance={profile.get('balance', 'N/A')}")
            return profile

        # Fallback: dados podem já estar diretos
        if self.log:
            self.log.warning(f"'reseller' não encontrado em data, retornando data diretamente. Keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")

        return data

    def update_profile(self, **kwargs) -> bool:
        """
        Atualiza perfil do reseller

        Args:
            name (str): Nome
            surname (str): Sobrenome
            phone (str): Telefone
            address (str): Endereço
            company (str): Empresa
            country (str): País

        Returns:
            True se atualizado com sucesso

        Exemplo:
            api.update_profile(
                name='João',
                surname='Silva',
                phone='+5511999999999'
            )
        """
        response = self._request('PUT', '/reseller', json=kwargs)
        self._handle_response(response, '/reseller')
        return True

    # ==================== DASHBOARD & ESTATÍSTICAS ====================

    def get_dashboard(self) -> Dict[str, Any]:
        """
        Obtém estatísticas do dashboard

        Returns:
            Dict com estatísticas:
                - total_activations, activations_today, activated_devices
                - earnings_this_month, total_earnings
                - balance, credits
                - subresellers_count, devices_expiring_soon
        """
        response = self._request('GET', '/reseller/dashboard')
        return self._handle_response(response, '/reseller/dashboard')

    def get_reseller_charts(self) -> Dict[str, Any]:
        """
        Obtém dados para gráficos de ativações e ganhos

        Returns:
            Dict com dados dos gráficos
        """
        response = self._request('GET', '/reseller/res_charts')
        return self._handle_response(response, '/reseller/res_charts')

    def get_referral_charts(self) -> Dict[str, Any]:
        """
        Obtém dados para gráficos de links de referência

        Returns:
            Dict com dados dos gráficos de referência
        """
        response = self._request('GET', '/reseller/ref_charts')
        return self._handle_response(response, '/reseller/ref_charts')

    # ==================== DISPOSITIVOS ====================

    def list_devices(self, page: int = 1, limit: int = 10,
                    sort: str = 'id', order: str = 'DESC',
                    search: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Lista dispositivos com paginação

        Args:
            page: Número da página (começando em 1)
            limit: Quantidade de itens por página
            sort: DEPRECATED - Não usado (causa timeout no backend)
            order: DEPRECATED - Não usado (causa timeout no backend)
            search: Filtros de busca (dict com chaves: mac, comment, etc)

        Returns:
            Dict com:
                - count (int): Total de dispositivos
                - rows (list): Lista de dispositivos

        Exemplo:
            devices = api.list_devices(page=1, limit=10, search={'comment': 'VIP'})
            print(f"Total: {devices['count']}")
            for device in devices['rows']:
                print(f"{device['mac']} - {device['expire_date']}")
        """
        if self.log:
            self.log.debug(f"Listando dispositivos: page={page}, limit={limit}, search={search}")

        params = {
            'page': page,
            'limit': limit,
        }

        # NUNCA enviar sort/order - causa timeout no backend da API Dream TV
        # A API usa ordenação padrão própria que funciona corretamente
        if search:
            params['search'] = json.dumps(search)
            if self.log:
                self.log.debug(f"Busca com filtro: {search}")

        # Usar timeout maior para listagens (podem ter muitos dados)
        response = self._request('GET', '/reseller/devices', params=params, timeout=120)
        result = self._handle_response(response, '/reseller/devices')

        if self.log:
            count = result.get('count', 0) if isinstance(result, dict) else 0
            rows = len(result.get('rows', [])) if isinstance(result, dict) else 0
            self.log.debug(f"Dispositivos retornados: {rows} de {count} total")

        return result

    def activate_device(self, mac: str, package_id: int,
                       comment: Optional[str] = None) -> Dict[str, Any]:
        """
        Ativa ou renova um dispositivo

        Args:
            mac: MAC address do dispositivo (formato XX:XX:XX:XX:XX:XX)
            package_id: ID do pacote de ativação
            comment: Comentário opcional (máx 255 caracteres)

        Returns:
            Dict com dados da ativação

        Exemplo:
            result = api.activate_device(
                mac='00:1A:2B:3C:4D:5E',
                package_id=1,
                comment='Cliente VIP'
            )
        """
        if self.log:
            self.log.debug(f"Ativando dispositivo: mac={mac.upper()}, package_id={package_id}, comment={comment}")

        payload = {
            'mac': mac.upper(),
            'package_id': package_id
        }

        if comment:
            payload['comment'] = comment[:255]

        response = self._request('POST', '/reseller/activate', json=payload)
        result = self._handle_response(response, '/reseller/activate')

        if self.log:
            self.log.debug(f"Dispositivo ativado com sucesso: {mac.upper()}")

        return result

    def get_activation_code(self, mac: str) -> Dict[str, Any]:
        """
        Gera código OTP para adicionar dispositivo

        Args:
            mac: MAC address do dispositivo

        Returns:
            Dict com código OTP e instruções
        """
        response = self._request('GET', f'/reseller/activation_code?mac={mac.upper()}')
        return self._handle_response(response, '/reseller/activation_code')

    def add_existing_device(self, mac: str, code: Optional[str] = None,
                           key: Optional[str] = None) -> Dict[str, Any]:
        """
        Adiciona dispositivo já existente usando código OTP ou key

        Args:
            mac: MAC address do dispositivo
            code: Código OTP (ou)
            key: Chave de ativação

        Returns:
            Dict com confirmação
        """
        payload = {'mac': mac.upper()}

        if code:
            payload['code'] = code
        elif key:
            payload['key'] = key
        else:
            raise ValueError("É necessário fornecer 'code' ou 'key'")

        response = self._request('POST', '/reseller/add_existing_device', json=payload)
        return self._handle_response(response, '/reseller/add_existing_device')

    def delete_device(self, mac: str) -> bool:
        """
        Deleta um dispositivo

        Args:
            mac: MAC address do dispositivo

        Returns:
            True se deletado com sucesso
        """
        response = self._request('DELETE', '/reseller/devices', json={'mac': mac.upper()})
        self._handle_response(response, '/reseller/devices')
        return True

    def transfer_device(self, mac: str, to_reseller_id: int) -> bool:
        """
        Transfere dispositivo para outro reseller

        Args:
            mac: MAC address do dispositivo
            to_reseller_id: ID do reseller destino

        Returns:
            True se transferido com sucesso
        """
        payload = {
            'mac': mac.upper(),
            'to_reseller_id': to_reseller_id
        }
        response = self._request('PUT', '/reseller/device/transfer', json=payload)
        self._handle_response(response, '/reseller/device/transfer')
        return True

    def update_device_comment(self, mac: str, comment: str) -> bool:
        """
        Atualiza comentário do dispositivo

        Args:
            mac: MAC address do dispositivo
            comment: Novo comentário (máx 255 caracteres)

        Returns:
            True se atualizado com sucesso
        """
        payload = {
            'mac': mac.upper(),
            'comment': comment[:255]
        }
        response = self._request('PUT', '/reseller/device/comment', json=payload)
        self._handle_response(response, '/reseller/device/comment')
        return True

    # ==================== ATIVAÇÕES ====================

    def list_activations(self, page: int = 1, limit: int = 10,
                        sort: str = 'id', order: str = 'DESC',
                        between: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Lista histórico completo de ativações

        Args:
            page: Número da página
            limit: Itens por página
            sort: DEPRECATED - Não usado (causa timeout no backend)
            order: DEPRECATED - Não usado (causa timeout no backend)
            between: DEPRECATED - Não usado (causa erro 500 no backend - bug SQL com 'from')

        Returns:
            Dict com count e rows

        NOTA: Filtro por data (between) não funciona devido a bug no backend da API.
              O backend tenta usar 'from' como nome de coluna (palavra reservada SQL).
              Erro retornado: "Unknown column 'activations_history.from' in 'where clause'"
        """
        params = {
            'page': page,
            'limit': limit,
        }

        # NUNCA enviar sort/order ou between - causam timeout/erro no backend da API Dream TV
        # between causa erro 500: backend usa 'from' como coluna (palavra reservada SQL)

        # Usar timeout maior para listagens (podem ter muitos dados)
        response = self._request('GET', '/reseller/activations_history', params=params, timeout=120)
        return self._handle_response(response, '/reseller/activations_history')

    def get_device_activations(self, mac: str, page: int = 1,
                              limit: int = 10) -> Dict[str, Any]:
        """
        Lista ativações de um dispositivo específico

        Args:
            mac: MAC address do dispositivo
            page: Número da página
            limit: Itens por página

        Returns:
            Dict com histórico de ativações do dispositivo
        """
        params = {
            'mac': mac.upper(),
            'page': page,
            'limit': limit
        }

        response = self._request('GET', '/reseller/activations', params=params)
        return self._handle_response(response, '/reseller/activations')

    # ==================== PACOTES ====================

    def list_packages(self) -> List[Dict[str, Any]]:
        """
        Lista pacotes de ativação disponíveis

        Returns:
            Lista de pacotes com id, name, credits, duration, price, etc

        Exemplo:
            packages = api.list_packages()
            for pkg in packages:
                print(f"{pkg['name']}: {pkg['credits']} créditos - R$ {pkg['price']}")
        """
        response = self._request('GET', '/reseller/activation_packages')
        return self._handle_response(response, '/reseller/activation_packages')

    # ==================== PLAYLISTS ====================

    def list_playlists(self, device_id: int) -> List[Dict[str, Any]]:
        """
        Lista playlists de um dispositivo específico

        Args:
            device_id: ID do dispositivo (obrigatório)

        Returns:
            Lista direta de playlists [{"id": X, "name": Y, "url": Z, ...}, ...]
            Campos importantes: id, name, url, is_selected, is_protected, expired_date

        NOTAS:
            - O backend da API exige deviceId obrigatório para listar playlists
            - Paginação NÃO é suportada - API retorna todas as playlists do dispositivo
            - Parâmetros 'page' e 'limit' causam erro 500: "page is not allowed"
            - Retorna lista direta, NÃO dict com count/rows (diferente de outros endpoints)
        """
        params = {
            'deviceId': device_id
        }
        # Usar timeout maior para listagens (podem ter muitos dados)
        response = self._request('GET', '/reseller/playlist', params=params, timeout=120)
        return self._handle_response(response, '/reseller/playlist')

    def add_playlist(self, device_id: int, name: str, url: str) -> Dict[str, Any]:
        """
        Adiciona nova playlist a um dispositivo específico

        Args:
            device_id: ID do dispositivo (obrigatório)
            name: Nome da playlist
            url: URL completa da playlist (deve conter username, password e parâmetros necessários)

        Returns:
            Dict com resposta da API ({"error": false, "message": "Playlist created", "status": 200})

        Exemplo de URL:
            http://exemplo.com/get.php?username=USER&password=PASS&type=m3u_plus&output=m3u8
        """
        payload = {
            'deviceId': device_id,
            'name': name,
            'url': url
        }

        response = self._request('POST', '/reseller/playlist', json=payload)
        return self._handle_response(response, '/reseller/playlist')

    def update_playlist(self, id: int, device_id: int, **kwargs) -> bool:
        """
        Atualiza playlist existente

        Args:
            id: ID da playlist
            device_id: ID do dispositivo (obrigatório pela API)
            **kwargs: Campos a atualizar (name, url, protect, etc)

        Returns:
            True se atualizado
        """
        payload = {'deviceId': device_id, 'id': id, **kwargs}
        response = self._request('PUT', '/reseller/playlist', json=payload)
        self._handle_response(response, '/reseller/playlist')
        return True

    def delete_playlist(self, id: int, device_id: int) -> bool:
        """
        Deleta playlist de um dispositivo específico

        Args:
            id: ID da playlist
            device_id: ID do dispositivo (obrigatório)

        Returns:
            True se deletado

        NOTA: API exige deviceId no payload além do id da playlist
        """
        response = self._request('DELETE', '/reseller/playlist', json={'id': id, 'deviceId': device_id})
        self._handle_response(response, '/reseller/playlist')
        return True

    def set_default_playlist(self, id: int) -> bool:
        """
        Define playlist como padrão (is_selected = true)

        Args:
            id: ID da playlist

        Returns:
            True se definido como padrão

        Resposta esperada:
            {"error": false, "message": "Success", "status": 200}

        NOTA: Método HTTP deve ser PUT (não POST)
              Payload: {"id": playlist_id}
        """
        response = self._request('PUT', '/reseller/playlist/set_selected', json={'id': id})
        self._handle_response(response, '/reseller/playlist/set_selected')
        return True

    # ==================== SUB-RESELLERS ====================

    def list_subresellers(self, page: int = 1, limit: int = 10,
                         sort: str = 'id', order: str = 'DESC',
                         search: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Lista sub-resellers com paginação

        Args:
            page: Número da página
            limit: Itens por página
            sort: DEPRECATED - Não usado (causa timeout no backend)
            order: DEPRECATED - Não usado (causa timeout no backend)
            search: Filtros de busca

        Returns:
            Dict com count e rows
        """
        params = {
            'page': page,
            'limit': limit,
        }

        # NUNCA enviar sort/order - causa timeout no backend da API Dream TV
        if search:
            params['search'] = json.dumps(search)

        # Usar timeout maior para listagens (podem ter muitos dados)
        response = self._request('GET', '/reseller/subreseller', params=params, timeout=120)
        return self._handle_response(response, '/reseller/subreseller')

    def create_subreseller(self, name: str, surname: str, email: str,
                          password: str, **kwargs) -> Dict[str, Any]:
        """
        Cria novo sub-reseller

        Args:
            name: Nome
            surname: Sobrenome
            email: Email
            password: Senha
            **kwargs: phone, company, country, manage_server, manage_free_dns

        Returns:
            Dict com dados do sub-reseller criado
        """
        payload = {
            'name': name,
            'surname': surname,
            'email': email,
            'password': password,
            **kwargs
        }

        response = self._request('POST', '/reseller/subreseller', json=payload)
        return self._handle_response(response, '/reseller/subreseller')

    def update_subreseller(self, id: int, **kwargs) -> bool:
        """
        Atualiza sub-reseller

        Args:
            id: ID do sub-reseller
            **kwargs: Campos a atualizar

        Returns:
            True se atualizado
        """
        payload = {'id': id, **kwargs}
        response = self._request('PUT', '/reseller/subreseller', json=payload)
        self._handle_response(response, '/reseller/subreseller')
        return True

    def toggle_subreseller(self, id: int, disabled: bool) -> bool:
        """
        Habilita ou desabilita sub-reseller

        Args:
            id: ID do sub-reseller
            disabled: True para desabilitar, False para habilitar

        Returns:
            True se alterado
        """
        payload = {'id': id, 'disabled': disabled}
        response = self._request('PUT', '/reseller/disable', json=payload)
        self._handle_response(response, '/reseller/disable')
        return True

    def give_credits_to_subreseller(self, subreseller_id: int, credits: int) -> bool:
        """
        Dá créditos para sub-reseller

        Args:
            subreseller_id: ID do sub-reseller
            credits: Quantidade de créditos

        Returns:
            True se transferido
        """
        payload = {
            'subreseller_id': subreseller_id,
            'credits': credits
        }
        response = self._request('POST', '/reseller/activation', json=payload)
        self._handle_response(response, '/reseller/activation')
        return True

    def take_credits_from_subreseller(self, subreseller_id: int, credits: int) -> bool:
        """
        Retira créditos de sub-reseller

        Args:
            subreseller_id: ID do sub-reseller
            credits: Quantidade de créditos

        Returns:
            True se removido
        """
        payload = {
            'subreseller_id': subreseller_id,
            'credits': credits
        }
        response = self._request('PUT', '/reseller/activation', json=payload)
        self._handle_response(response, '/reseller/activation')
        return True

    # ==================== SAQUES ====================

    def list_withdrawals(self, page: int = 1, limit: int = 10,
                        sort: str = 'id', order: str = 'DESC') -> Dict[str, Any]:
        """
        Lista histórico de saques

        Args:
            page: Número da página
            limit: Itens por página
            sort: DEPRECATED - Não usado (causa timeout no backend)
            order: DEPRECATED - Não usado (causa timeout no backend)

        Returns:
            Dict com count e rows
        """
        params = {
            'page': page,
            'limit': limit,
        }

        # NUNCA enviar sort/order - causa timeout no backend da API Dream TV

        # Usar timeout maior para listagens (podem ter muitos dados)
        response = self._request('GET', '/reseller/withdraw', params=params, timeout=120)
        return self._handle_response(response, '/reseller/withdraw')

    def request_paypal_withdrawal(self, email: str, amount: float) -> Dict[str, Any]:
        """
        Solicita saque via PayPal

        Args:
            email: Email do PayPal
            amount: Valor a sacar

        Returns:
            Dict com dados da solicitação
        """
        payload = {
            'email': email,
            'amount': amount,
            'method': 'paypal'
        }

        response = self._request('POST', '/reseller/withdraw', json=payload)
        return self._handle_response(response, '/reseller/withdraw')

    def request_wire_withdrawal(self, name: str, surname: str, email: str,
                               amount: float, country: str, swift: str,
                               iban: str) -> Dict[str, Any]:
        """
        Solicita saque via transferência bancária

        Args:
            name: Nome
            surname: Sobrenome
            email: Email
            amount: Valor
            country: País
            swift: Código SWIFT
            iban: IBAN

        Returns:
            Dict com dados da solicitação
        """
        payload = {
            'name': name,
            'surname': surname,
            'email': email,
            'amount': amount,
            'country': country,
            'swift': swift,
            'iban': iban,
            'method': 'wired transfer'
        }

        response = self._request('POST', '/reseller/withdraw', json=payload)
        return self._handle_response(response, '/reseller/withdraw')

    # ==================== VALIDAÇÕES & UTILIDADES ====================

    def validate_mac(self, mac: str) -> bool:
        """
        Valida formato de MAC address

        Args:
            mac: MAC address a validar

        Returns:
            True se válido, False se inválido
        """
        try:
            response = self._request('GET', f'/api/validate_mac?mac={mac.upper()}')
            data = self._handle_response(response, '/api/validate_mac')
            return not data.get('error', True)
        except:
            return False

    def get_app_info(self) -> Dict[str, Any]:
        """
        Obtém informações gerais da aplicação

        Returns:
            Dict com informações da app
        """
        response = self._request('GET', '/api/app_info')
        return self._handle_response(response, '/api/app_info')
