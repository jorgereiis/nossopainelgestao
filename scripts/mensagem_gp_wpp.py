import os
import sys
import json
import time
import django
import random
import requests
from datetime import datetime, timedelta
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

def _subdir_futebol(data_envio: Optional[str]) -> Tuple[str, str, str, List[str]]:
    """
    Resolve o subdiretório (relativo a /images) onde estão os banners de futebol,
    aplicando fallback quando `data_envio` não for informada.

    Ordem de busca:
      1. Pasta do dia solicitado (ou dia atual, se `data_envio` for None);
      2. Pasta do dia anterior;
      3. Pasta mais recente disponível (ordem decrescente).

    Retorna uma tupla:
      (subdir_resolvido, data_resolvida, data_solicitada, imagens_encontradas)
    """
    data_solicitada = (data_envio or localtime().strftime('%d-%m-%Y')).strip()

    def _build_subdir(date_str: str) -> str:
        return f"telegram_banners/{date_str}"

    def _listar_para_data(date_str: str) -> List[str]:
        return _listar_imagens(_build_subdir(date_str))

    # Se uma data específica foi informada, mantém comportamento original (sem fallback extra).
    if data_envio:
        imagens_data = _listar_para_data(data_solicitada)
        return _build_subdir(data_solicitada), data_solicitada, data_solicitada, imagens_data

    base_dir = os.path.join(os.path.dirname(__file__), '../images/telegram_banners')
    now_local = localtime()
    candidatos: List[str] = []
    vistos = set()

    def _adicionar_candidato(date_str: str) -> None:
        if date_str and date_str not in vistos:
            candidatos.append(date_str)
            vistos.add(date_str)

    _adicionar_candidato(data_solicitada)
    _adicionar_candidato((now_local - timedelta(days=1)).strftime('%d-%m-%Y'))

    if os.path.isdir(base_dir):
        datas_disponiveis: List[str] = []
        for nome in os.listdir(base_dir):
            caminho = os.path.join(base_dir, nome)
            if not os.path.isdir(caminho):
                continue
            try:
                datetime.strptime(nome, '%d-%m-%Y')
            except ValueError:
                continue
            datas_disponiveis.append(nome)

        for nome in sorted(datas_disponiveis, key=lambda d: datetime.strptime(d, '%d-%m-%Y'), reverse=True):
            _adicionar_candidato(nome)

    for candidato in candidatos:
        imagens_candidato = _listar_para_data(candidato)
        if imagens_candidato:
            return _build_subdir(candidato), candidato, data_solicitada, imagens_candidato

    imagens_solicitada = _listar_para_data(data_solicitada)
    return _build_subdir(data_solicitada), data_solicitada, data_solicitada, imagens_solicitada

# ----------------- ENVIO -----------------
def enviar_mensagem_grupos(
    grupo_id: str,
    grupo_nome: str,
    mensagem: str,
    usuario: str,
    token: str,
    tipo_envio: str,
    image_name: Optional[str] = None,
    data_envio: Optional[str] = None,   # << novo: permite testar datas passadas (DD-MM-YYYY)
) -> None:
    """
    Envia mensagens/imagens para grupos conforme o tipo_envio:

    - 'grupo_vendas':
        * Envia 1 imagem (de 'gp_vendas') com legenda = `mensagem`.
        * Usa `image_name` para escolher a imagem.

    - 'grupo_futebol':
        * Envia TODAS as imagens existentes em 'images/telegram_banners/DD-MM-YYYY', SEM legenda.
        * Ao final, envia APENAS um texto com `mensagem` **SE e somente SE ao menos uma imagem foi enviada**.

    Observações:
        - `grupo_id` deve ser o id do grupo (ex.: '12345-67890@g.us').
        - `usuario` é o identificador da sessão no WPPConnect usado na URL.
        - `token` é o Bearer Token da sessão.
        - `data_envio` opcional no formato 'DD-MM-YYYY' para testar datas passadas.
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
        subdir_dia, data_resolvida, data_solicitada, imagens = _subdir_futebol(data_envio)

        if data_resolvida != data_solicitada:
            registrar_log(
                f"{localtime().strftime('%d-%m-%Y %H:%M:%S')} "
                f"[TIPO][{tipo_envio.upper()}] [USUARIO][{usuario}] [GRUPO][{grupo_nome}] [CODE][N/A] "
                f"[FALLBACK] - Pasta '{data_solicitada}' indisponível. Usando '{data_resolvida}'.",
                LOG_GRUPOS,
            )

        imagens_enviadas = 0

        if not imagens:
            _log_fail(1, -1, f"Nenhuma imagem encontrada em /images/{subdir_dia}. Texto final será ignorado.")
        else:
            # 1) Envia TODAS as imagens do dia, SEM legenda
            for img in imagens:
                img_b64 = obter_img_base64(img, subdir_dia)
                if not img_b64:
                    _log_fail(1, -1, f"Falha ao converter '{img}' em base64 ({subdir_dia}). Pulando arquivo.")
                    continue

                mime = _mime_from_ext(img)
                payload_img = {
                    'phone': grupo_id,
                    'isGroup': True,
                    'filename': img,
                    'base64': f'data:{mime};base64,{img_b64}',
                }
                url_img = f"{url_base}/send-image"

                enviado_essa = False
                for tentativa in range(1, 3):
                    ok, err, status = _post_json(url_img, payload_img, tentativa)
                    if ok:
                        _log_ok()
                        enviado_essa = True
                        break
                    _log_fail(tentativa, status, err)
                    time.sleep(random.uniform(20, 30))

                if enviado_essa:
                    imagens_enviadas += 1

        # 2) Envia o texto final **apenas se ao menos 1 imagem foi enviada**
        if imagens_enviadas > 0 and mensagem:
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
        elif imagens_enviadas == 0:
            _log_fail(1, -1, f"Nenhuma imagem enviada com sucesso em /images/{subdir_dia}. Texto final não será enviado.")
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

    arquivos.sort(key=lambda f: os.path.getmtime(os.path.join(base_dir, f)), reverse=True)
    return arquivos[0]


def mensagem_gp_wpp(
    tipo_envio: str,
    nomes_grupos: List[str],
    mensagem: str,
    image_name: Optional[str] = None,
    atraso_min_s: float = 10.0,
    atraso_max_s: float = 20.0,
    data_envio: Optional[str] = None,
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
        data_envio: (opcional) 'DD-MM-YYYY' para buscar imagens em telegram_banners/data
    """
    ts = localtime().strftime('%d-%m-%Y %H:%M:%S')

    django_user = User.objects.get(id=1)  # ajuste se necessário
    sessao = get_object_or_404(SessaoWpp, usuario=django_user)
    token = sessao.token

    api_user = getattr(django_user, "username", str(django_user))

    if tipo_envio not in {"grupo_vendas", "grupo_futebol"}:
        registrar_log(
            TEMPLATE_LOG_MSG_GRUPO_FALHOU.format(
                ts, tipo_envio.upper(), api_user, "N/A", "N/A", 1,
                "tipo_envio inválido (use 'grupo_vendas' ou 'grupo_futebol')",
            ),
            LOG_GRUPOS,
        )
        return

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

    for group_id, group_name in grupos_encontrados:
        try:
            enviar_mensagem_grupos(
                grupo_id=group_id,
                grupo_nome=group_name,
                mensagem=mensagem,
                usuario=api_user,
                token=token,
                tipo_envio=tipo_envio,
                image_name=vendas_img if tipo_envio == "grupo_vendas" else None,
                data_envio=data_envio,  # << propaga data override para futebol
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

        time.sleep(random.uniform(atraso_min_s, atraso_max_s))
##### FIM #####

# Exemplo de chamadas
def chamada_funcao_gp_vendas():
    mensagem_gp_wpp(
        tipo_envio="grupo_vendas",
        nomes_grupos=[
            "Vendas e Desapegos",
            "🌴BV2(Bazar/venda/troca)",
            "👾OLX Brasil Ｇrµ ¹⁹",
            "OLX FORTALEZA",
            "OLX CEARÁ",
            "Compras, vendas e trocas br",
            "💥 TROCAS E VENDAS 💥",
            "OLX  JACINTINHO - MACEIÓ. VENDAS/TROCAS/ PRESTAÇÃO DE SERVIÇOS.",
        ],
        mensagem=(
            "🔹 A *Star Max Streaming* se trata de um serviço onde através da sua TV Smart poderá ter acesso aos canais da TV Fechada brasileira e internacional.\n\n"
            "🎬 Conteúdos de Filmes, Séries e Novelas das maiores plataformas de streaming, como _Amazon, Netflix, Globo Play, Disney+ e outras._\n\n"
            "* Tudo isso usando apenas a sua TV Smart e internet, sem precisar outros aparelhos;\n"
            "* Um excelente serviço por um custo baixíssimo;\n"
            "* Pague com *PIX ou Cartão de Crédito.*\n"
            "* 💰Planos a partir de R$ 25.00\n\n"
            "‼️ Entre em contato conosco aqui mesmo no WhatsApp: +55 83 99332-9190"
        ),
        image_name="01.png",
    )

def chamada_funcao_gp_futebol():
    # sem override => usa a pasta do dia atual
    mensagem_gp_wpp(
        tipo_envio="grupo_futebol",
        nomes_grupos=[
            "BAMOR 5° VG 🇲🇫🌪️",
            "Jampa de Aço 5988",
        ],
        mensagem="⚽️ *AGENDA FUTEBOL DO DIA!*"
                 "\n📅 *DATA:* {}\n\n" \
                 "Transmissão completa de todos os campeonatos apenas aqui 😉\n\n" \
                 "Chamaaaaa!! 🔥".format(localtime().strftime('%d/%m/%Y')),
    )

def chamada_funcao_gp_futebol_teste_data_passada():
    # com override => busca imagens em images/telegram_banners/26-09-2025
    mensagem_gp_wpp(
        tipo_envio="grupo_futebol",
        nomes_grupos=["Anotações 📝"],
        mensagem="⚽️ *FUTEBOL (TESTE PASSADO)*"
                 "\n📅 *DATA DOS JOGOS:* 26/09/2025",
        data_envio="26-09-2025",
    )

##### FIM DO SCRIPT #####
