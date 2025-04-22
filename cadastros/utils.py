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

"""import os
from cadastros.models import SessaoWpp

URL_API_WPP = os.getenv('URL_API_WPP')

token_obj = SessaoWpp.objects.filter(usuario=usuario).first()

if not token_obj:
    registrar_log(f"[ERRO] [EXECUTAR_UPLOAD_STATUS] Token do usuário {usuario.username} não encontrado.")
    return

token = token_obj.token
# Consulta as labels de um contato no WhatsApp
def consulta_label(usuario, token):
    url = f"{URL_API_WPP}/{usuario}/get-all-labels"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + token
    }

# Altera o label de um contato no WhatsApp
def altera_label(telefone, label_add, label_remove, usuario, token):
    url = f"{URL_API_WPP}/{usuario}/add-or-remove-label"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + token
    }"""