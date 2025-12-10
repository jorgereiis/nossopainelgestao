"""
Serviço de Migração de Clientes entre Usuários

Este módulo contém toda a lógica para migração segura de clientes
de um usuário para outro, incluindo validações, criação automática
de entidades relacionadas e migração transacional.
"""

from django.db import transaction
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from typing import Dict, List, Set, Tuple, Any
from collections import defaultdict

from nossopainel.models import (
    Cliente,
    Mensalidade,
    ContaDoAplicativo,
    ClientePlanoHistorico,
    OfertaPromocionalEnviada,
    DescontoProgressivoIndicacao,
    NotificationRead,
    Servidor,
    Dispositivo,
    Aplicativo,
    Tipos_pgto,
    Plano,
)


class MigrationValidationError(Exception):
    """Exceção customizada para erros de validação de migração"""
    pass


class ClientMigrationService:
    """
    Serviço responsável por migração de clientes entre usuários.

    Funcionalidades:
    - Validação de pré-requisitos (indicações, descontos, entidades)
    - Criação automática de entidades faltantes no destino
    - Migração transacional com rollback em caso de erro
    - Logging detalhado de todas as operações
    """

    def __init__(self, usuario_origem: User, usuario_destino: User):
        """
        Inicializa o serviço de migração.

        Args:
            usuario_origem: Usuário de onde os clientes serão migrados
            usuario_destino: Usuário para onde os clientes serão migrados
        """
        self.usuario_origem = usuario_origem
        self.usuario_destino = usuario_destino
        self.validation_errors = []
        self.validation_warnings = []
        self.entities_to_create = defaultdict(list)

    def validate_migration(self, clientes_ids: List[int]) -> Dict[str, Any]:
        """
        Valida se a migração pode ser realizada e retorna um resumo.

        Args:
            clientes_ids: Lista de IDs dos clientes a serem migrados

        Returns:
            Dicionário com resultado da validação e estatísticas

        Raises:
            MigrationValidationError: Se a validação falhar
        """
        self.validation_errors = []
        self.validation_warnings = []
        self.entities_to_create = defaultdict(list)

        # Buscar clientes
        clientes = Cliente.objects.filter(
            id__in=clientes_ids,
            usuario=self.usuario_origem
        ).select_related(
            'servidor', 'dispositivo', 'sistema', 'forma_pgto', 'plano', 'indicado_por'
        )

        if not clientes.exists():
            raise MigrationValidationError('Nenhum cliente válido selecionado para migração.')

        clientes_count = clientes.count()
        clientes_ids_set = set(clientes.values_list('id', flat=True))

        # 1. Validar indicações
        self._validate_indicacoes(clientes, clientes_ids_set)

        # 2. Validar descontos progressivos
        self._validate_descontos_progressivos(clientes, clientes_ids_set)

        # 3. Validar e preparar entidades relacionadas
        self._validate_entidades_relacionadas(clientes)

        # Se houver erros críticos, bloquear migração
        if self.validation_errors:
            raise MigrationValidationError(
                'Erros de validação encontrados:\n' + '\n'.join(self.validation_errors)
            )

        # Calcular estatísticas
        stats = self._calculate_migration_stats(clientes)

        return {
            'valid': True,
            'clientes_count': clientes_count,
            'warnings': self.validation_warnings,
            'entities_to_create': dict(self.entities_to_create),
            'stats': stats,
        }

    def _validate_indicacoes(self, clientes, clientes_ids_set: Set[int]) -> None:
        """
        Valida se todas as indicações estão sendo migradas juntas.

        Regra: Cliente com indicado_por só pode ser migrado se o indicador
        também estiver sendo migrado na mesma operação.
        """
        for cliente in clientes:
            if cliente.indicado_por:
                indicador_id = cliente.indicado_por.id

                # Verifica se o indicador está sendo migrado junto
                if indicador_id not in clientes_ids_set:
                    self.validation_errors.append(
                        f'Cliente "{cliente.nome}" (ID: {cliente.id}) foi indicado por '
                        f'"{cliente.indicado_por.nome}" (ID: {indicador_id}), que NÃO está '
                        f'sendo migrado. Inclua o cliente indicador na migração ou remova '
                        f'a indicação manualmente.'
                    )

    def _validate_descontos_progressivos(
        self, clientes, clientes_ids_set: Set[int]
    ) -> None:
        """
        Valida se descontos progressivos podem ser mantidos.

        Regra: Descontos progressivos só são mantidos se AMBOS os clientes
        (indicador E indicado) estiverem sendo migrados juntos.
        """
        # Buscar descontos onde algum dos clientes envolvidos está sendo migrado
        descontos = DescontoProgressivoIndicacao.objects.filter(
            usuario=self.usuario_origem
        ).filter(
            models.Q(cliente_indicador__id__in=clientes_ids_set) |
            models.Q(cliente_indicado__id__in=clientes_ids_set)
        ).select_related('cliente_indicador', 'cliente_indicado')

        for desconto in descontos:
            indicador_id = desconto.cliente_indicador.id
            indicado_id = desconto.cliente_indicado.id

            # Ambos devem estar sendo migrados
            indicador_migrando = indicador_id in clientes_ids_set
            indicado_migrando = indicado_id in clientes_ids_set

            if not (indicador_migrando and indicado_migrando):
                self.validation_errors.append(
                    f'Desconto progressivo entre "{desconto.cliente_indicador.nome}" '
                    f'(ID: {indicador_id}) e "{desconto.cliente_indicado.nome}" '
                    f'(ID: {indicado_id}) será perdido. Ambos os clientes devem ser '
                    f'migrados juntos para manter o desconto.'
                )

    def _validate_entidades_relacionadas(self, clientes) -> None:
        """
        Valida e prepara entidades relacionadas para criação no destino.

        Verifica se Servidor, Dispositivo, Aplicativo, Tipos_pgto e Plano
        existem no usuário de destino. Se não existirem, prepara para criação.
        """
        # Coletar entidades únicas usadas pelos clientes
        servidores_necessarios = set()
        dispositivos_necessarios = set()
        aplicativos_necessarios = set()
        formas_pgto_necessarias = set()
        planos_necessarios = set()

        for cliente in clientes:
            if cliente.servidor:
                servidores_necessarios.add(cliente.servidor.id)
            if cliente.dispositivo:
                dispositivos_necessarios.add(cliente.dispositivo.id)
            if cliente.sistema:
                aplicativos_necessarios.add(cliente.sistema.id)
            if cliente.forma_pgto:
                formas_pgto_necessarias.add(cliente.forma_pgto.id)
            if cliente.plano:
                planos_necessarios.add(cliente.plano.id)

        # Verificar quais já existem no destino
        self._check_and_prepare_entity(
            'Servidor', Servidor, servidores_necessarios
        )
        self._check_and_prepare_entity(
            'Dispositivo', Dispositivo, dispositivos_necessarios
        )
        self._check_and_prepare_entity(
            'Aplicativo', Aplicativo, aplicativos_necessarios
        )
        self._check_and_prepare_entity(
            'Tipos_pgto', Tipos_pgto, formas_pgto_necessarias
        )
        self._check_and_prepare_entity(
            'Plano', Plano, planos_necessarios
        )

    def _check_and_prepare_entity(
        self, entity_name: str, model_class, ids_necessarios: Set[int]
    ) -> None:
        """
        Verifica se entidades existem no destino e prepara para criação se necessário.
        """
        if not ids_necessarios:
            return

        # Buscar entidades na origem
        entidades_origem = model_class.objects.filter(
            id__in=ids_necessarios,
            usuario=self.usuario_origem
        )

        # Buscar entidades já existentes no destino (por nome)
        nomes_origem = list(entidades_origem.values_list('nome', flat=True))
        entidades_destino_existentes = set(
            model_class.objects.filter(
                usuario=self.usuario_destino,
                nome__in=nomes_origem
            ).values_list('nome', flat=True)
        )

        # Identificar quais precisam ser criadas
        for entidade in entidades_origem:
            if entidade.nome not in entidades_destino_existentes:
                self.entities_to_create[entity_name].append({
                    'id_origem': entidade.id,
                    'nome': entidade.nome,
                    'dados': self._serialize_entity(entidade),
                })
                self.validation_warnings.append(
                    f'{entity_name} "{entidade.nome}" não existe no usuário destino '
                    f'e será criado automaticamente.'
                )

    def _serialize_entity(self, entidade) -> Dict[str, Any]:
        """
        Serializa uma entidade para posterior criação no destino.
        """
        model_name = entidade.__class__.__name__
        data = {}

        # Campos comuns
        if hasattr(entidade, 'nome'):
            data['nome'] = entidade.nome

        # Campos específicos por modelo
        if model_name == 'Servidor':
            # Servidor tem apenas: nome, usuario, imagem_admin
            # Não copiar imagem_admin na migração (pode ser arquivo grande)
            pass
        elif model_name == 'Plano':
            # Plano tem: nome, telas, valor, usuario
            data.update({
                'valor': entidade.valor,
                'telas': entidade.telas,
            })
        elif model_name == 'Aplicativo':
            # Aplicativo tem: nome, device_has_mac, usuario
            if hasattr(entidade, 'device_has_mac'):
                data['device_has_mac'] = entidade.device_has_mac
        # Tipos_pgto e Dispositivo só têm nome

        return data

    def _calculate_migration_stats(self, clientes) -> Dict[str, int]:
        """
        Calcula estatísticas sobre a migração.
        """
        clientes_ids = list(clientes.values_list('id', flat=True))

        return {
            'clientes_ativos': clientes.filter(cancelado=False).count(),
            'clientes_cancelados': clientes.filter(cancelado=True).count(),
            'mensalidades': Mensalidade.objects.filter(cliente__id__in=clientes_ids).count(),
            'contas_aplicativo': ContaDoAplicativo.objects.filter(cliente__id__in=clientes_ids).count(),
            'historico_planos': ClientePlanoHistorico.objects.filter(cliente__id__in=clientes_ids).count(),
            'ofertas_promocionais': OfertaPromocionalEnviada.objects.filter(cliente__id__in=clientes_ids).count(),
            'descontos_progressivos': DescontoProgressivoIndicacao.objects.filter(
                usuario=self.usuario_origem
            ).filter(
                models.Q(cliente_indicador__id__in=clientes_ids) |
                models.Q(cliente_indicado__id__in=clientes_ids)
            ).count(),
        }

    @transaction.atomic
    def execute_migration(self, clientes_ids: List[int]) -> Dict[str, Any]:
        """
        Executa a migração dos clientes de forma transacional.

        Args:
            clientes_ids: Lista de IDs dos clientes a serem migrados

        Returns:
            Dicionário com resultado da migração

        Raises:
            MigrationValidationError: Se a validação falhar
            Exception: Se ocorrer erro durante a migração (rollback automático)
        """
        # Validar novamente antes de executar
        validation_result = self.validate_migration(clientes_ids)

        # Criar entidades faltantes no destino
        entity_mapping = self._create_missing_entities()

        # Buscar clientes a migrar
        clientes = Cliente.objects.filter(
            id__in=clientes_ids,
            usuario=self.usuario_origem
        ).select_related(
            'servidor', 'dispositivo', 'sistema', 'forma_pgto', 'plano'
        )

        # Migrar dados relacionados
        stats = {
            'clientes_migrados': 0,
            'mensalidades_migradas': 0,
            'contas_migradas': 0,
            'historicos_migrados': 0,
            'ofertas_migradas': 0,
            'descontos_migrados': 0,
            'notificacoes_migradas': 0,
        }

        for cliente in clientes:
            # Atualizar referências de entidades se necessário
            self._update_cliente_references(cliente, entity_mapping)

            # Migrar OfertaPromocionalEnviada
            ofertas_count = OfertaPromocionalEnviada.objects.filter(
                cliente=cliente
            ).update(usuario=self.usuario_destino)
            stats['ofertas_migradas'] += ofertas_count

            # Migrar ClientePlanoHistorico
            historicos_count = ClientePlanoHistorico.objects.filter(
                cliente=cliente
            ).update(usuario=self.usuario_destino)
            stats['historicos_migrados'] += historicos_count

            # Migrar Mensalidades
            mensalidades = Mensalidade.objects.filter(cliente=cliente)
            mensalidades_ids = list(mensalidades.values_list('id', flat=True))
            mensalidades_count = mensalidades.update(usuario=self.usuario_destino)
            stats['mensalidades_migradas'] += mensalidades_count

            # Migrar NotificationRead (relacionadas às mensalidades)
            notificacoes_count = NotificationRead.objects.filter(
                mensalidade__id__in=mensalidades_ids
            ).update(usuario=self.usuario_destino)
            stats['notificacoes_migradas'] += notificacoes_count

            # Migrar ContaDoAplicativo
            contas_count = ContaDoAplicativo.objects.filter(
                cliente=cliente
            ).update(usuario=self.usuario_destino)
            stats['contas_migradas'] += contas_count

            # Migrar DescontoProgressivoIndicacao
            descontos_count = DescontoProgressivoIndicacao.objects.filter(
                models.Q(cliente_indicador=cliente) | models.Q(cliente_indicado=cliente),
                usuario=self.usuario_origem
            ).update(usuario=self.usuario_destino)
            stats['descontos_migrados'] += descontos_count

            # Migrar Cliente (por último!)
            cliente.usuario = self.usuario_destino
            cliente.save()
            stats['clientes_migrados'] += 1

        return {
            'success': True,
            'stats': stats,
            'entities_created': dict(self.entities_to_create),
            'warnings': self.validation_warnings,
        }

    def _create_missing_entities(self) -> Dict[str, Dict[int, int]]:
        """
        Cria entidades faltantes no usuário destino.

        Returns:
            Mapeamento de ID origem -> ID destino para cada tipo de entidade
        """
        from django.db import models as django_models

        entity_mapping = defaultdict(dict)

        for entity_name, entities_data in self.entities_to_create.items():
            model_class = {
                'Servidor': Servidor,
                'Dispositivo': Dispositivo,
                'Aplicativo': Aplicativo,
                'Tipos_pgto': Tipos_pgto,
                'Plano': Plano,
            }[entity_name]

            for entity_data in entities_data:
                id_origem = entity_data['id_origem']
                dados = entity_data['dados'].copy()
                dados['usuario'] = self.usuario_destino

                # Criar entidade no destino
                nova_entidade = model_class.objects.create(**dados)
                entity_mapping[entity_name][id_origem] = nova_entidade.id

        return entity_mapping

    def _update_cliente_references(
        self, cliente: Cliente, entity_mapping: Dict[str, Dict[int, int]]
    ) -> None:
        """
        Atualiza referências de entidades no cliente se foram criadas novas.
        """
        if cliente.servidor_id and cliente.servidor_id in entity_mapping.get('Servidor', {}):
            cliente.servidor_id = entity_mapping['Servidor'][cliente.servidor_id]

        if cliente.dispositivo_id and cliente.dispositivo_id in entity_mapping.get('Dispositivo', {}):
            cliente.dispositivo_id = entity_mapping['Dispositivo'][cliente.dispositivo_id]

        if cliente.sistema_id and cliente.sistema_id in entity_mapping.get('Aplicativo', {}):
            cliente.sistema_id = entity_mapping['Aplicativo'][cliente.sistema_id]

        if cliente.forma_pgto_id and cliente.forma_pgto_id in entity_mapping.get('Tipos_pgto', {}):
            cliente.forma_pgto_id = entity_mapping['Tipos_pgto'][cliente.forma_pgto_id]

        if cliente.plano_id and cliente.plano_id in entity_mapping.get('Plano', {}):
            cliente.plano_id = entity_mapping['Plano'][cliente.plano_id]


# Import necessário que estava faltando
from django.db import models
