# cadastros/management/commands/import_leads_from_txt.py
import re
from pathlib import Path
from typing import Iterable, Tuple, Set, List

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction

from nossopainel.models import TelefoneLeads  # ajuste o caminho do seu app/models


PHONE_MAX_LEN = 20


def normalize_phone(raw: str, default_ddi: str = "") -> Tuple[str, str]:
    """
    Normaliza um telefone:
      - Remove espaços e símbolos, preservando + se houver.
      - '00' no início vira '+' (ex.: 0044... -> +44...).
      - Se não tiver '+', apenas prefixa '+' (o DDI deve estar no número).
      - Retorna (telefone_normalizado_ou_vazio, motivo_skip_ou_vazio)

    IMPORTANTE: O telefone deve vir com DDI correto. Não adiciona DDI automaticamente.
    Use --default-ddi=+55 se precisar adicionar DDI para números legados.
    """

    s = raw.strip()
    if not s or s.startswith("#"):
        return "", "linha_vazia_ou_comentario"

    # Preserve '+' se existir, senão remova tudo que não é dígito
    if s.startswith("+"):
        digits = "+" + re.sub(r"\D", "", s[1:])
    else:
        digits_only = re.sub(r"\D", "", s)
        # Converte discagem internacional '00' para '+'
        if digits_only.startswith("00"):
            digits = "+" + digits_only[2:]
        elif default_ddi:
            # Apenas adiciona DDI se explicitamente configurado via --default-ddi
            digits = f"{default_ddi}{digits_only}"
        else:
            # Apenas prefixa '+' - assume que o DDI já está no número
            digits = f"+{digits_only}" if digits_only else ""

    if not digits:
        return "", "sem_digitos"

    if len(digits) > PHONE_MAX_LEN:
        return "", "muito_longo"

    # Garantir que o formato final seja +\d+
    if not digits.startswith("+") or not digits[1:].isdigit():
        return "", "formato_invalido"

    return digits, ""


class Command(BaseCommand):
    help = "Importa telefones (um por linha) para TelefoneLeads a partir de arquivo(s) .txt."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            "-f",
            dest="files",
            nargs="+",
            required=True,
            help="Caminho(s) do(s) arquivo(s) .txt com um telefone por linha.",
        )
        user_group = parser.add_mutually_exclusive_group(required=True)
        user_group.add_argument("--username", help="Username do usuário dono dos leads.")
        user_group.add_argument("--user-id", type=int, help="ID do usuário dono dos leads.")

        parser.add_argument(
            "--default-ddi",
            default="",
            help="DDI a adicionar para números sem '+' (padrão: nenhum). Ex: --default-ddi=+55 para números BR legados.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra o que seria importado, mas não grava no banco.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Tamanho do lote para bulk_create (padrão: 1000).",
        )

    def handle(self, *args, **options):
        files: List[str] = options["files"]
        username = options.get("username")
        user_id = options.get("user_id")
        default_ddi = options["default_ddi"]
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]

        User = get_user_model()

        # Resolve user
        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                raise CommandError(f"Usuário com username='{username}' não encontrado.")
        else:
            try:
                user = User.objects.get(pk=user_id)
            except User.DoesNotExist:
                raise CommandError(f"Usuário com id={user_id} não encontrado.")

        # Coleta e normaliza todos os telefones dos arquivos
        seen: Set[str] = set()
        to_create: List[TelefoneLeads] = []

        stats = {
            "arquivos_lidos": 0,
            "linhas_lidas": 0,
            "normalizados": 0,
            "duplicados_no_arquivo": 0,
            "ja_existiam_no_db": 0,
            "skip_vazias_ou_comentario": 0,
            "skip_sem_digitos": 0,
            "skip_muito_longo": 0,
            "skip_formato_invalido": 0,
            "inseridos": 0,
        }

        for fpath in files:
            p = Path(fpath)
            if not p.exists() or not p.is_file():
                raise CommandError(f"Arquivo não encontrado: {fpath}")

            stats["arquivos_lidos"] += 1
            with p.open("r", encoding="utf-8") as f:
                for raw in f:
                    stats["linhas_lidas"] += 1
                    phone, reason = normalize_phone(raw, default_ddi=default_ddi)

                    if not phone:
                        if reason == "linha_vazia_ou_comentario":
                            stats["skip_vazias_ou_comentario"] += 1
                        elif reason == "sem_digitos":
                            stats["skip_sem_digitos"] += 1
                        elif reason == "muito_longo":
                            stats["skip_muito_longo"] += 1
                        elif reason == "formato_invalido":
                            stats["skip_formato_invalido"] += 1
                        continue

                    stats["normalizados"] += 1

                    # Dedup dentro do arquivo(s)
                    if phone in seen:
                        stats["duplicados_no_arquivo"] += 1
                        continue
                    seen.add(phone)

                    # Deixe a verificação contra o DB para um único passo (mais eficiente)
                    to_create.append(TelefoneLeads(telefone=phone, usuario=user))

        # Remover os que já existem no DB (por telefone e usuário)
        # Obtém apenas os telefones candidatos
        candidate_phones = [t.telefone for t in to_create]
        existing = set(
            TelefoneLeads.objects.filter(
                usuario=user, telefone__in=candidate_phones
            ).values_list("telefone", flat=True)
        )

        filtered_to_create = [t for t in to_create if t.telefone not in existing]
        stats["ja_existiam_no_db"] = len(to_create) - len(filtered_to_create)

        if dry_run:
            # Não comita nada
            self.stdout.write(self.style.WARNING("** DRY RUN ** Nenhum dado será gravado."))
            stats_preview = stats.copy()
            stats_preview["inseridos"] = len(filtered_to_create)

            self._print_stats(stats_preview, user, files)
            return

        # Insere em lote
        with transaction.atomic():
            created = TelefoneLeads.objects.bulk_create(
                filtered_to_create, batch_size=batch_size, ignore_conflicts=True
            )
        stats["inseridos"] = len(created)

        self._print_stats(stats, user, files)

    def _print_stats(self, stats, user, files):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== IMPORTAÇÃO DE LEADS FINALIZADA ==="))
        self.stdout.write(f"Usuário: {user} (id={user.pk})")
        self.stdout.write(f"Arquivos: {', '.join(files)}")
        self.stdout.write("")
        self.stdout.write(f"Linhas lidas: {stats['linhas_lidas']}")
        self.stdout.write(f"Telefones normalizados: {stats['normalizados']}")
        self.stdout.write(f"Duplicados no(s) arquivo(s): {stats['duplicados_no_arquivo']}")
        self.stdout.write(f"Já existiam no DB: {stats['ja_existiam_no_db']}")
        self.stdout.write(f"Inseridos agora: {stats['inseridos']}")
        self.stdout.write("")
        self.stdout.write("Skips:")
        self.stdout.write(f"  - Vazias/Comentário: {stats['skip_vazias_ou_comentario']}")
        self.stdout.write(f"  - Sem dígitos:       {stats['skip_sem_digitos']}")
        self.stdout.write(f"  - Muito longos:      {stats['skip_muito_longo']}")
        self.stdout.write(f"  - Formato inválido:  {stats['skip_formato_invalido']}")
        self.stdout.write("")
