# UTILIZADO NAS MODELS
DDD_UF_MAP = {
    '11': 'SP', '12': 'SP', '13': 'SP', '14': 'SP', '15': 'SP', '16': 'SP', '17': 'SP', '18': 'SP', '19': 'SP',
    '21': 'RJ', '22': 'RJ', '24': 'RJ',
    '27': 'ES', '28': 'ES',
    '31': 'MG', '32': 'MG', '33': 'MG', '34': 'MG', '35': 'MG', '37': 'MG', '38': 'MG',
    '41': 'PR', '42': 'PR', '43': 'PR', '44': 'PR', '45': 'PR', '46': 'PR',
    '47': 'SC', '48': 'SC', '49': 'SC',
    '51': 'RS', '53': 'RS', '54': 'RS', '55': 'RS',
    '61': 'DF',
    '62': 'GO', '64': 'GO',
    '63': 'TO',
    '65': 'MT', '66': 'MT',
    '67': 'MS',
    '68': 'AC',
    '69': 'RO',
    '71': 'BA', '73': 'BA', '74': 'BA', '75': 'BA', '77': 'BA',
    '79': 'SE',
    '81': 'PE', '87': 'PE',
    '82': 'AL',
    '83': 'PB',
    '84': 'RN',
    '85': 'CE', '88': 'CE',
    '86': 'PI', '89': 'PI',
    '91': 'PA', '93': 'PA', '94': 'PA',
    '92': 'AM', '97': 'AM',
    '95': 'RR',
    '96': 'AP',
    '98': 'MA', '99': 'MA',
}

###################################################
##### FUNÇÕES PARA CONEXÃO COM API WPPCONNECT #####
###################################################
import os
import requests

URL_API_WPP = os.getenv("URL_API_WPP")
USER_SESSION_WPP = os.getenv("USER_SESSION_WPP")

def get_label_contact(telefone, token):
    # Monta a URL da requisição com o número de telefone
    url = f'{URL_API_WPP}/{USER_SESSION_WPP}/contact/{telefone}'

    # Define os headers com o token de autenticação
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    try:
        # Faz uma requisição GET para obter informações do contato
        response = requests.get(url, headers=headers)

        # Se a resposta for bem-sucedida (200 ou 201)
        if response.status_code in [200, 201]:
            # Converte a resposta JSON em dicionário
            response_data = response.json()
            # Extrai a lista de labels, se houver
            labels = response_data.get('response', {}).get('labels', [])
            return labels
        else:
            # Exibe erro caso a resposta não tenha sido bem-sucedida
            print(f"Erro ao obter labels do contato Nº {telefone}: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        # Trata exceções como erro de rede ou parsing
        print(f"Exceção ao fazer requisição: {e}")
        return []


def check_number_status(telefone, token):
    # Monta a URL da requisição para checar status do número
    url = f'{URL_API_WPP}/{USER_SESSION_WPP}/check-number-status/{telefone}'

    # Define os headers com token de autenticação
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    try:
        # Envia requisição GET para verificar se o número existe no WhatsApp
        response = requests.get(url, headers=headers)

        if response.status_code in [200, 201]:
            # Converte a resposta em JSON
            response_data = response.json()
            # Retorna o valor booleano que indica se o número existe
            status = response_data.get('response', {}).get('numberExists', False)
            return status
        else:
            # Exibe erro caso não tenha sucesso
            print(f"Erro ao verificar status do número {telefone}: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        # Trata falhas na requisição
        print(f"Exceção ao verificar status do número: {e}")
        return False


def get_all_labels(token):
    # Monta a URL da requisição para obter todas as labels
    url = f'{URL_API_WPP}/{USER_SESSION_WPP}/get-all-labels'

    # Headers com autenticação
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    try:
        # Envia requisição GET
        response = requests.get(url, headers=headers)

        if response.status_code in [200, 201]:
            # Converte resposta para JSON
            response_data = response.json()
            # Retorna a lista de labels encontrada na chave 'response'
            labels = response_data.get('response', [])
            return labels
        else:
            # Exibe mensagem de erro se a resposta falhar
            print(f"Erro ao obter labels: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        # Captura e mostra falhas na requisição
        print(f"Exceção ao tentar obter labels: {e}")
        return []


def add_or_remove_label_contact(label_id_1, label_id_2, label_name, telefone, token):
    # Normaliza o telefone (remove + e @c.us, caso existam)
    telefone = telefone.replace('+', '').replace('@c.us', '').strip()

    # URL para adicionar ou remover label
    url = f'{URL_API_WPP}/{USER_SESSION_WPP}/add-or-remove-label'

    # Headers com content-type e autenticação
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }

    # Garante que label_id_2 seja uma lista
    labels_to_remove = label_id_2 if isinstance(label_id_2, list) else [label_id_2]

    # Corpo da requisição: adiciona uma label e remove outra
    body = {
        "chatIds": [telefone],
        "options": [
            {"labelId": label_id_1, "type": "add"}
        ] + [
            {"labelId": label, "type": "remove"} for label in labels_to_remove if label
        ]
    }

    # Envia requisição POST com JSON
    response = requests.post(url, headers=headers, json=body)

    if response.status_code in [200, 201]:
        # Mensagem de sucesso
        print(f"Label do contato alterada para {label_id_1} - {label_name}.")
    else:
        # Mensagem de erro com status code e texto da resposta
        print(f"Erro ao alterar label do contato Nº {telefone}: {response.status_code} - {response.text}")

    try:
        # Tenta converter a resposta para JSON
        response_data = response.json()
    except Exception:
        # Se falhar, retorna o texto bruto
        response_data = response.text

    # Retorna o status da requisição e a resposta convertida ou bruta
    return response.status_code, response_data


def criar_label_se_nao_existir(nome_label, token, hex_color=None):
    """
    Cria a label no WhatsApp se não existir. Se hex_color for fornecido, aplica a cor.
    Após criação, busca novamente todas as labels para obter o ID correto.
    """
    labels = get_all_labels(token)

    # Verifica se a label já existe
    label_existente = next((label for label in labels if label["name"].strip().lower() == nome_label.lower()), None)
    if label_existente:
        return label_existente.get("id")

    # Monta requisição
    url = f"{URL_API_WPP}/{USER_SESSION_WPP}/add-new-label"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

    body = {"name": nome_label}

    if hex_color:
        try:
            color_int = int(hex_color.lstrip("#"), 16) + (255 << 24)  # adiciona alpha FF
            body["options"] = {"labelColor": color_int}
        except ValueError:
            print(f"⚠️ Cor inválida para a label '{nome_label}': {hex_color}")

    # Faz a requisição
    response = requests.post(url, headers=headers, json=body)
    if response.status_code in [200, 201]:
        print(f"✅ Label '{nome_label}' criada com sucesso.")

        # --- Correção ---
        # Após criar, buscar novamente todas as labels para encontrar o ID
        try:
            labels = get_all_labels(token)
            nova_label = next((label for label in labels if label["name"].strip().lower() == nome_label.lower()), None)
            if nova_label:
                return nova_label.get("id")
            else:
                print(f"⚠️ Label '{nome_label}' criada mas não encontrada após criação.")
                return None
        except Exception as e:
            print(f"❌ Erro ao buscar labels após criação: {e}")
            return None

    else:
        print(f"❌ Erro ao criar label '{nome_label}': {response.status_code} - {response.text}")
        return None