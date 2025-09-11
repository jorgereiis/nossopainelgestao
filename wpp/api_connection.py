import os
import time
import base64
import random
import inspect
import requests
import mimetypes
from django.utils.timezone import localtime

URL_API_WPP = os.getenv("URL_API_WPP")
MEU_NUM_CLARO = os.getenv("MEU_NUM_CLARO")

##################################################################
################ FUNÇÃO PARA REGISTRAR LOGS ######################
##################################################################

# Função para registrar mensagens no arquivo de log principal
def registrar_log(mensagem: str, log_path: str) -> None:
    """
    Registra uma mensagem no arquivo de log do usuário.
    """
    # Garante que o diretório onde o log será salvo exista
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    with open(log_path, "a", encoding="utf-8") as log:
        log.write(mensagem + "\n")
#### FIM #####

###################################################
##### FUNÇÕES PARA CONEXÃO COM API WPPCONNECT #####
###################################################

##### FUNÇÕES PARA GERENCIAR SESSÕES DO WHATSAPP #####
# --- Estas funções permitem gerar token, iniciar sessão, verificar status, obter QR code, verificar conexão, fechar sessão e fazer logout. ---
def gerar_token(session: str, secret: str):
    url = f"{URL_API_WPP}/{session}/{secret}/generate-token"
    response = requests.post(url)
    return response.json(), response.status_code

def start_session(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/start-session"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "webhook": "",
        "waitQrCode": True
    }
    response = requests.post(url, json=data, headers=headers)
    return response.json(), response.status_code

def status_session(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/status-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.json(), response.status_code

def get_qrcode(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/qrcode-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.content, response.status_code

def check_connection(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/check-connection-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.json(), response.status_code

def close_session(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/close-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(url, headers=headers)
    time.sleep(3)  # Aguarda se necessário
    return response.json(), response.status_code

def logout_session(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/logout-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(url, headers=headers)
    time.sleep(3)
    return response.json(), response.status_code

##### FUNÇÕES PARA GERENCIAR CONTATOS E LABELS #####
# --- Função para obter labels de um contato ---
def get_label_contact(telefone, token, user):
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    func_name = inspect.currentframe().f_code.co_name

    # Monta a URL da requisição com o número de telefone
    url = f'{URL_API_WPP}/{user}/contact/{telefone}'

    # Define os headers com o token de autenticação
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    body = {
        "phone": telefone,
    }

    try:
        # Faz uma requisição GET para obter informações do contato
        response = requests.get(url, headers=headers, json=body)

        # Se a resposta for bem-sucedida (200 ou 201)
        if response.status_code in [200, 201]:
            # Converte a resposta JSON em dicionário
            response_data = response.json()
            # Extrai a lista de labels, se houver
            labels = (response_data.get('response') or {}).get('labels', [])
            return labels
        else:
            # Exibe erro caso a resposta não tenha sido bem-sucedida
            print(f"[{timestamp}] [ERROR] [{func_name}] [{user}] Erro ao obter labels do telefone {telefone}: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        # Trata exceções como erro de rede ou parsing
        print(f"[{timestamp}] [ERROR] [{func_name}] [{user}] Exceção ao fazer requisição: {e}")
        return []

# --- Função para verificar se o número existe no WhatsApp ---
def check_number_status(telefone, token, user):
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    func_name = inspect.currentframe().f_code.co_name

    # Monta a URL da requisição para checar status do número
    url = f'{URL_API_WPP}/{user}/check-number-status/{telefone}'

    # Define os headers com token de autenticação
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    body = {
        "phone": telefone,
    }

    try:
        # Envia requisição GET para verificar se o número existe no WhatsApp
        response = requests.get(url, headers=headers, json=body)

        if response.status_code in [200, 201]:
            # Converte a resposta em JSON
            response_data = response.json()
            # Retorna o valor booleano que indica se o número existe
            status = response_data.get('response', {}).get('numberExists', False)
            user_number = response_data.get('response', {}).get('id', None).get('user', None)
            print(f"[{timestamp}] [INFO] [{func_name}] [{user}] O número informado é válido no WhatsApp.")
            return {'status': status, 'user': user_number}
        else:
            # Exibe erro caso não tenha sucesso
            print(f"[{timestamp}] [ERROR] [{func_name}] [{user}] Erro ao verificar status do número {telefone}: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        # Trata falhas na requisição
        print(f"[{timestamp}] [ERROR] [{func_name}] [{user}] Exceção ao verificar status do número: {e}")
        return False


# --- Função para obter todas as labels disponíveis para um contato ---
def get_all_labels(token, user):
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    func_name = inspect.currentframe().f_code.co_name

    # Monta a URL da requisição para obter todas as labels
    url = f'{URL_API_WPP}/{user}/get-all-labels'

    # Headers com autenticação
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    body = {
        "phone": MEU_NUM_CLARO,
    }

    try:
        # Envia requisição GET
        response = requests.get(url, headers=headers, json=body)

        if response.status_code in [200, 201]:
            # Converte resposta para JSON
            response_data = response.json()
            # Retorna a lista de labels encontradas
            labels = response_data.get('response', [])
            print(f"[{timestamp}] [INFO] [{func_name}] [{user}] Labels obtidas com sucesso - {len(labels)} labels encontradas.")
            return labels
        else:
            # Exibe mensagem de erro se a resposta falhar
            print(f"[{timestamp}] [ERROR] [{func_name}] [{user}] Erro ao obter labels: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        # Captura e mostra falhas na requisição
        print(f"[{timestamp}] [ERROR] [{func_name}] [{user}] Exceção ao tentar obter labels: {e}")
        return []


# --- Função para adicionar ou remover labels de um contato ---
def add_or_remove_label_contact(label_id_1, label_id_2, label_name, telefone, token, user):
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    func_name = inspect.currentframe().f_code.co_name
    
    # Normaliza o telefone (remove + e @c.us, caso existam)
    telefone = telefone.replace('+', '').replace('@c.us', '').strip()

    # Garante que label_id_2 seja lista
    labels_atual = label_id_2 if isinstance(label_id_2, list) else [label_id_2]

    # Se a label desejada já está aplicada, não faz nada
    if label_id_1 in labels_atual:
        print(f"[{timestamp}] [INFO] [{func_name}] [{user}] Label '{label_name}' já atribuída ao contato. Nenhuma alteração necessária.")
        return 200, {"status": "skipped", "message": "Label já atribuída"}

    # Prepara headers e URL
    url = f'{URL_API_WPP}/{user}/add-or-remove-label'
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    # Remove todas as labels anteriores e adiciona a nova
    body = {
        "chatIds": [telefone],
        "options": [
            {"labelId": label_id_1, "type": "add"}
        ] + [
            {"labelId": label, "type": "remove"} for label in labels_atual if label and label != label_id_1
        ]
    }
  
    # Envia requisição POST com JSON
    response = requests.post(url, headers=headers, json=body)
    print(f"[{timestamp}] [INFO] [{func_name}] [{user}] Response status code: {response.status_code}, response text: {response.text}")

    if response.status_code in [200, 201]:
        # Mensagem de sucesso
        print(f"[{timestamp}] [INFO] [{func_name}] [{user}] Label definida: {label_id_1} - {label_name}.")
    else:
        # Mensagem de erro com status code e texto da resposta
        print(f"[{timestamp}] [ERROR] [{func_name}] [{user}] Erro ao alterar label do telefone {telefone}: {response.status_code} - {response.text}")

    try:
        # Tenta converter a resposta para JSON
        response_data = response.json()
    except Exception:
        # Se falhar, retorna o texto bruto
        response_data = response.text

    # Retorna o status da requisição e a resposta convertida ou bruta
    return response.status_code, response_data


# --- Função para criar uma nova label se não existir ---
def criar_label_se_nao_existir(nome_label, token, user, hex_color=None):
    """
    Cria a label no WhatsApp se não existir. Se hex_color for fornecido, aplica a cor.
    Após criação, busca novamente todas as labels para obter o ID correto.
    """
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    func_name = inspect.currentframe().f_code.co_name
    labels = get_all_labels(token, user)

    # Verifica se a label já existe
    label_existente = next((label for label in labels if label["name"].strip().lower() == nome_label.lower()), None)
    if label_existente:
        return label_existente.get("id")

    # Monta requisição
    url = f"{URL_API_WPP}/{user}/add-new-label"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

    body = {"name": nome_label}

    if hex_color:
        try:
            color_int = int(hex_color.lstrip("#"), 16) + (255 << 24)
            body["options"] = {"labelColor": color_int}
        except ValueError:
            print(f"[{timestamp}] [ERROR] [{func_name}] [{user}] Cor inválida para a label '{nome_label}': {hex_color}")

    # Faz a requisição
    response = requests.post(url, headers=headers, json=body)
    if response.status_code in [200, 201]:
        print(f"[{timestamp}] [INFO] [{func_name}] [{user}] Label '{nome_label}' criada com sucesso.")

        # Após criar, buscar novamente todas as labels para encontrar o ID
        try:
            labels = get_all_labels(token, user)
            nova_label = next((label for label in labels if label["name"].strip().lower() == nome_label.lower()), None)
            if nova_label:
                return nova_label.get("id")
            else:
                print(f"[{timestamp}] [INFO] [{func_name}] [{user}] Label '{nome_label}' criada mas não encontrada após criação.")
                return None
        except Exception as e:
            print(f"[{timestamp}] [ERROR] [{func_name}] [{user}] Erro ao buscar labels após criação: {e}")
            return None

    else:
        print(f"[{timestamp}] [ERROR] [{func_name}] [{user}] Erro ao criar label '{nome_label}': {response.status_code} - {response.text}")
        return None

##### FUNÇÃO PARA GERENCIAR GRUPOS DO WHATSAPP #####
# --- Obter todos os grupos disponíveis na sessão do WhatsApp ---
def get_all_groups(token, user):
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    func_name = inspect.currentframe().f_code.co_name

    # Monta a URL da requisição para obter todos os grupos
    url = f'{URL_API_WPP}/{user}/all-groups'

    # Headers com autenticação
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    try:
        # Envia requisição GET (sem body)
        response = requests.get(url, headers=headers)

        if response.status_code in [200, 201]:
            # Converte resposta para JSON
            response_data = response.json()
            # Retorna a lista de grupos encontrada na chave 'response'
            groups = response_data.get('response', [])
            return groups
        else:
            # Exibe mensagem de erro se a resposta falhar
            print(f"[{timestamp}] [ERROR] [{func_name}] [{user}] Erro ao obter grupos: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        # Captura e mostra falhas na requisição
        print(f"[{timestamp}] [ERROR] [{func_name}] [{user}] Exceção ao tentar obter grupos: {e}")
        return []
    
# --- Extrai ID dos grupos do WhatsApp para envio das notificações ---
def get_ids_grupos_envio(grupos, adm_envia_alertas, log_path):
    """
    Retorna lista de grupos do WhatsApp em que o USER é admin.
    Cada item: (group_id, nome)
    """
    numero = str(adm_envia_alertas)
    if not numero.startswith('55'):
        numero = f'55{numero}'
    telefone_adm = f"{numero}@c.us"

    grupos_admin = []
    for g in grupos:
        participantes = (
            g.get("groupMetadata", {}).get("participants", [])
            or g.get("participants", [])
        )
        eh_admin = any(
            p.get("id", {}).get("_serialized") == telefone_adm and (
                bool(p.get("isAdmin")) or bool(p.get("isSuperAdmin"))
            )
            for p in participantes
        )
        if eh_admin:
            group_id = g.get("id", {}).get("_serialized")
            nome = g.get("name") or g.get("groupMetadata", {}).get("subject") or "Grupo sem nome"
            if group_id:
                grupos_admin.append((group_id, nome))
                registrar_log(f"Grupo autorizado: {nome} ({group_id})", log_path)
    return grupos_admin

# --- Buscar IDs de grupos a partir de nomes fornecidos ---
def get_group_ids_by_names(token, user, group_names, log_path=None):
    """
    Retorna os IDs dos grupos do WhatsApp com base nos nomes informados.

    :param token: Token da sessão WPPConnect
    :param user: Usuário/diretório da sessão
    :param group_names: Lista com nomes (ou parte do nome) dos grupos
    :param log_path: Caminho do log (opcional)
    :return: Lista de tuplas (group_id, nome)
    """
    timestamp = localtime().strftime('%d-%m-%Y %H:%M:%S')
    func_name = inspect.currentframe().f_code.co_name

    try:
        # Obter todos os grupos disponíveis
        grupos = get_all_groups(token, user)
        if not grupos:
            print(f"[{timestamp}] [WARN] [{func_name}] [{user}] Nenhum grupo encontrado.")
            return []

        # Normaliza nomes para comparação (case insensitive e strip)
        nomes_busca = [n.strip().lower() for n in group_names]

        grupos_encontrados = []
        for g in grupos:
            group_id = g.get("id", {}).get("_serialized")
            nome = g.get("name") or g.get("groupMetadata", {}).get("subject") or "Grupo sem nome"

            if nome and any(n in nome.lower() for n in nomes_busca):
                grupos_encontrados.append((group_id, nome))
                if log_path:
                    registrar_log(f"Grupo encontrado: {nome} ({group_id})", log_path)

        if not grupos_encontrados:
            print(f"[{timestamp}] [INFO] [{func_name}] [{user}] Nenhum grupo correspondente encontrado para {group_names}.")

        return grupos_encontrados

    except Exception as e:
        print(f"[{timestamp}] [ERROR] [{func_name}] [{user}] Erro ao buscar grupos por nome: {e}")
        return []


##### FUNÇÃO PARA ENVIAR MENSAGENS DE STATUS NO WHATSAPP #####
# --- Envia mensagem de texto para o status do WhatsApp ---
def upload_status_sem_imagem(texto_status, usuario, token, log_path):
    url = f"{URL_API_WPP}/{usuario}/send-text-storie"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + token
    }
    body = {"text": texto_status}

    try:
        response = requests.post(url, json=body, headers=headers, timeout=30)
        response.raise_for_status()
        registrar_log(f"[OK] Mensagem de status enviada para {usuario}", log_path)
        random.randint(10, 30)
        return True
    except Exception as e:
        registrar_log(f"[ERRO] {usuario} => {e}", log_path)
        return False

# --- Envia imagem com legenda para o status do WhatsApp ---
def upload_imagem_status(imagem, legenda, usuario, token, log_path):
    try:
        # Se for uma URL (http ou https), envia diretamente
        if imagem.startswith("http://") or imagem.startswith("https://"):
            path_param = imagem
        else:
            # Arquivo local — converte para base64 com tipo MIME
            if not os.path.exists(imagem):
                raise FileNotFoundError(f"Arquivo não encontrado: {imagem}")

            mime_type, _ = mimetypes.guess_type(imagem)
            if not mime_type:
                raise ValueError("Tipo MIME não identificado para a imagem.")

            with open(imagem, "rb") as img_file:
                img_base64 = base64.b64encode(img_file.read()).decode("utf-8")

            path_param = f"data:{mime_type};base64,{img_base64}"

        url = f"{URL_API_WPP}/{usuario}/send-image-storie"
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': 'Bearer ' + token
        }
        body = {
            "path": path_param,
            "caption": legenda or ""
        }

        response = requests.post(url, json=body, headers=headers, timeout=30)
        response.raise_for_status()
        registrar_log(f"[OK] Imagem enviada para {usuario}: {legenda}", log_path)
        return True

    except Exception as e:
        registrar_log(f"[ERRO] {usuario} => {e}", log_path)
        return False