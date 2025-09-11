import os
import sys
import json
import time
import django
import random
import requests
from django.utils.timezone import localtime
from typing import List, Optional, Tuple

# Definir a variável de ambiente DJANGO_SETTINGS_MODULE
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'setup.settings')

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carregar as configurações do Django
django.setup()

from django.utils.timezone import localtime
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404

from wpp.api_connection import (
    get_group_ids_by_names,
    registrar_log,
)

from cadastros.models import (
    SessaoWpp,
)

from scripts.mensagens_wpp import (
    obter_img_base64,
)

URL_API_WPP = os.getenv("URL_API_WPP")
LOG_GRUPOS = "logs/Envios grupos/envios.log"
TEMPLATE_LOG_MSG_GRUPO = os.getenv("TEMPLATE_LOG_MSG_GRUPO")
TEMPLATE_LOG_MSG_GRUPO_FALHOU = os.getenv("TEMPLATE_LOG_MSG_GRUPO_FALHOU")

##################################################################
################ FUNÇÃO PARA ENVIAR MENSAGENS ####################
##################################################################

# ----------------- HELPERS -----------------
def _listar_imagens(sub_directory: str) -> List[str]:
    """
    Lista arquivos de imagem existentes em /images/{sub_directory}.
    Retorna nomes de arquivos (ordenados alfabeticamente).
    """
    base_dir = os.path.join(os.path.dirname(__file__), f'../images/{sub_directory}')
    if not os.path.isdir(base_dir):
        return []
    exts = {'.png', '.jpg', '.jpeg', '.webp'}
    imgs = [f for f in os.listdir(base_dir) if os.path.splitext(f)[1].lower() in exts]
    return sorted(imgs)

def _mime_from_ext(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.webp': 'image/webp',
    }.get(ext, 'image/png')

# ----------------- ENVIO -----------------
def enviar_mensagem_grupos(
    grupo_id: str,
    grupo_nome: str,
    mensagem: str,
    usuario: str,
    token: str,
    tipo_envio: str,
    image_name: Optional[str] = None,
) -> None:
    """
    Envia mensagens/imagens para grupos conforme o tipo_envio:

    - 'grupo_vendas':
        * Envia 1 imagem (de 'gp_vendas') com legenda = `mensagem`.
        * Usa `image_name` para escolher a imagem.
    - 'grupo_futebol':
        * Envia TODAS as imagens existentes em 'gp_futebol', SEM legenda.
        * Ao final, envia APENAS um texto com `mensagem`.

    Observações:
        - `grupo_id` deve ser o id do grupo (ex.: '12345-67890@g.us').
        - `usuario` é o identificador da sessão no WPPConnect usado na URL.
        - `token` é o Bearer Token da sessão.
    """
    url_base = f"{URL_API_WPP}/{usuario}"
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}',
    }

    def _post_json(url: str, payload: dict, tentativa: int) -> Tuple[bool, str, int]:
        try:
            r = requests.post(url, headers=headers, json=payload)
            if r.status_code in (200, 201):
                return True, "", r.status_code
            # tenta extrair mensagem de erro da API
            try:
                msg = r.json().get('message', r.text)
            except json.JSONDecodeError:
                msg = r.text
            return False, msg, r.status_code
        except requests.RequestException as e:
            return False, str(e), -1

    def _log_ok():
        log = TEMPLATE_LOG_MSG_GRUPO.format(
            localtime().strftime('%d-%m-%Y %H:%M:%S'),
            tipo_envio.upper(),
            usuario,
            grupo_nome,
        )
        registrar_log(log, LOG_GRUPOS)

    def _log_fail(tentativa: int, status_code: int, erro: str):
        log = TEMPLATE_LOG_MSG_GRUPO_FALHOU.format(
            localtime().strftime('%d-%m-%Y %H:%M:%S'),
            tipo_envio.upper(),
            usuario,
            grupo_nome,
            status_code if status_code != -1 else 'N/A',
            tentativa,
            erro,
        )
        registrar_log(log, LOG_GRUPOS)

    # --------- fluxo GRUPO VENDAS ---------
    if tipo_envio == 'grupo_vendas':
        if not image_name:
            _log_fail(1, -1, "Imagem não informada para grupo_vendas.")
            return

        img_b64 = obter_img_base64(image_name, 'gp_vendas')
        if not img_b64:
            _log_fail(1, -1, f"Falha ao converter imagem '{image_name}' em base64 (gp_vendas).")
            return

        mime = _mime_from_ext(image_name)
        payload = {
            'phone': grupo_id,
            'isGroup': True,
            'filename': image_name,
            'caption': mensagem,
            'base64': f'data:{mime};base64,{img_b64}',
        }
        url = f"{url_base}/send-image"

        for tentativa in range(1, 3):
            ok, err, status = _post_json(url, payload, tentativa)
            if ok:
                _log_ok()
                break
            _log_fail(tentativa, status, err)
            time.sleep(random.uniform(20, 30))
        return

    # --------- fluxo GRUPO FUTEBOL ---------
    if tipo_envio == 'grupo_futebol':
        imagens = _listar_imagens('gp_futebol')
        # 1) Envia TODAS as imagens, SEM legenda
        for img in imagens:
            img_b64 = obter_img_base64(img, 'gp_futebol')
            if not img_b64:
                _log_fail(1, -1, f"Falha ao converter '{img}' em base64 (gp_futebol). Pulando arquivo.")
                continue

            mime = _mime_from_ext(img)
            payload_img = {
                'phone': grupo_id,
                'isGroup': True,
                'filename': img,
                'base64': f'data:{mime};base64,{img_b64}',
            }
            url_img = f"{url_base}/send-image"

            enviado = False
            for tentativa in range(1, 3):
                ok, err, status = _post_json(url_img, payload_img, tentativa)
                if ok:
                    _log_ok()
                    enviado = True
                    break
                _log_fail(tentativa, status, err)
                time.sleep(random.uniform(20, 30))

        # 2) Ao final, envia APENAS o texto `mensagem`
        if mensagem:
            payload_txt = {
                'phone': grupo_id,
                'isGroup': True,
                'message': mensagem,
            }
            url_txt = f"{url_base}/send-message"

            for tentativa in range(1, 3):
                ok, err, status = _post_json(url_txt, payload_txt, tentativa)
                if ok:
                    _log_ok()
                    break
                _log_fail(tentativa, status, err)
                time.sleep(random.uniform(20, 30))
        return

    # --------- tipo_envio inválido ---------
    _log_fail(1, -1, f"tipo_envio inválido: {tipo_envio}. Use 'grupo_vendas' ou 'grupo_futebol'.")
##### FIM #####

######################################################
################ FUNÇÃO PRINCIPAL ####################
######################################################

def _imagem_vendas_escolher(image_name: Optional[str]) -> Optional[str]:
    """
    Para grupo_vendas:
      - Se `image_name` vier preenchido, usa-o.
      - Caso contrário, escolhe a imagem MAIS RECENTE no diretório images/gp_vendas.
    Retorna o nome do arquivo (sem path) ou None se não houver imagem.
    """
    if image_name:
        return image_name

    base_dir = os.path.join(os.path.dirname(__file__), '../images/gp_vendas')
    if not os.path.isdir(base_dir):
        return None

    exts = {'.png', '.jpg', '.jpeg', '.webp'}
    arquivos = [
        f for f in os.listdir(base_dir)
        if os.path.splitext(f)[1].lower() in exts
    ]
    if not arquivos:
        return None

    # escolhe a mais recente por mtime
    arquivos.sort(key=lambda f: os.path.getmtime(os.path.join(base_dir, f)), reverse=True)
    return arquivos[0]


def mensagem_gp_wpp(
    tipo_envio: str,
    nomes_grupos: List[str],
    mensagem: str,
    image_name: Optional[str] = None,
    atraso_min_s: float = 6.0,
    atraso_max_s: float = 10.0,
) -> None:
    """
    Controla o envio de mensagens para grupos do WhatsApp.

    Parâmetros:
        tipo_envio: 'grupo_vendas' ou 'grupo_futebol'
        nomes_grupos: lista de nomes (ou partes do nome) a localizar
        mensagem: legenda (vendas) OU texto final (futebol)
        image_name: (opcional) nome do arquivo a usar em 'gp_vendas';
                    se None, escolhe a mais recente da pasta
        atraso_min_s / atraso_max_s: jitter entre envios para reduzir rate limit
    """
    ts = localtime().strftime('%d-%m-%Y %H:%M:%S')

    # ---- resolve sessão/token/usuário da API ----
    django_user = User.objects.get(id=1)  # ajuste se necessário
    sessao = get_object_or_404(SessaoWpp, usuario=django_user)
    token = sessao.token

    # identificador "user" utilizado na rota da API (ex.: nome da sessão WPPConnect)
    api_user = getattr(django_user, "username", str(django_user))

    # ---- valida tipo_envio ----
    if tipo_envio not in {"grupo_vendas", "grupo_futebol"}:
        registrar_log(
            TEMPLATE_LOG_MSG_GRUPO_FALHOU.format(
                ts, tipo_envio.upper(), api_user, "N/A", "N/A", 1,
                "tipo_envio inválido (use 'grupo_vendas' ou 'grupo_futebol')",
            ),
            LOG_GRUPOS,
        )
        return

    # ---- encontra grupos a partir dos nomes informados ----
    try:
        grupos_encontrados = get_group_ids_by_names(token, api_user, nomes_grupos, log_path=LOG_GRUPOS)
    except Exception as e:
        registrar_log(
            TEMPLATE_LOG_MSG_GRUPO_FALHOU.format(
                ts, tipo_envio.upper(), api_user, "N/A", "N/A", 1,
                f"Falha ao buscar grupos: {e}",
            ),
            LOG_GRUPOS,
        )
        return

    if not grupos_encontrados:
        registrar_log(
            TEMPLATE_LOG_MSG_GRUPO_FALHOU.format(
                ts, tipo_envio.upper(), api_user, "N/A", "N/A", 1,
                f"Nenhum grupo correspondente em {nomes_grupos}",
            ),
            LOG_GRUPOS,
        )
        return

    # ---- prepara imagem (somente para vendas) ----
    vendas_img = None
    if tipo_envio == "grupo_vendas":
        vendas_img = _imagem_vendas_escolher(image_name)
        if not vendas_img:
            registrar_log(
                TEMPLATE_LOG_MSG_GRUPO_FALHOU.format(
                    ts, tipo_envio.upper(), api_user, "N/A", "N/A", 1,
                    "Nenhuma imagem disponível em images/gp_vendas ou nome inexistente",
                ),
                LOG_GRUPOS,
            )
            return

    # ---- fan-out de envios por grupo ----
    for group_id, group_name in grupos_encontrados:
        try:
            # Para vendas: envia UMA imagem com legenda = mensagem
            # Para futebol: enviar_mensagem_grupos cuidará de enviar TODAS as imagens + texto final
            enviar_mensagem_grupos(
                grupo_id=group_id,
                grupo_nome=group_name,
                mensagem=mensagem,
                usuario=api_user,
                token=token,
                tipo_envio=tipo_envio,
                image_name=vendas_img if tipo_envio == "grupo_vendas" else None,
            )
        except Exception as e:
            registrar_log(
                TEMPLATE_LOG_MSG_GRUPO_FALHOU.format(
                    localtime().strftime('%d-%m-%Y %H:%M:%S'),
                    tipo_envio.upper(),
                    api_user,
                    group_name,
                    "N/A",
                    1,
                    f"Exceção ao enviar: {e}",
                ),
                LOG_GRUPOS,
            )

        # jitter entre grupos para aliviar rate limits
        time.sleep(random.uniform(atraso_min_s, atraso_max_s))
##### FIM #####

# VENDAS – usa a última imagem mais recente de images/gp_vendas e legenda informada
def chamada_funcao_gp_vendas():
    mensagem_gp_wpp(
        tipo_envio="grupo_vendas",
        nomes_grupos=[
            "Vendas e Desapegos",
            "👗Bazar das Meninas👗",
            "🌴BV2(Bazar/venda/troca)"
        ],
        mensagem="🔹 A *Star Max Streaming* se trata de um serviço onde através da sua TV Smart poderá ter acesso aos canais da TV Fechada brasileira e internacional.\n\n" \
        "🎬 Conteúdos de Filmes, Séries e Novelas das maiores plataformas de streaming, como _Amazon, Netflix, Globo Play, Disney+ e outras._\n\n"
        "* Tudo isso usando apenas a sua TV Smart e internet, sem precisar outros aparelhos;\n"
        "* Um excelente serviço por um custo baixíssimo;\n"
        "* Pague com *PIX ou Cartão de Crédito.*\n"
        "* 💰Planos a partir de R$ 25.00\n\n" \
        "‼️ Entre em contato conosco aqui mesmo no WhatsApp: +55 83 99332-9190",
        image_name="01.png",  # None => escolhe a mais recente em images/gp_vendas
    )

# FUTEBOL – envia todas as imagens de images/gp_futebol (sem legendas) e ao final um texto
"""mensagem_gp_wpp(
    tipo_envio="grupo_futebol",
    nomes_grupos=["Anotações 📝",],
    mensagem="⚽️ *FUTEBOL DO DIA!*"
    "\n📅 *DATA DOS JOGOS:* {}".format(localtime().strftime('%d/%m/%Y')),
)"""
##### FIM DO SCRIPT #####