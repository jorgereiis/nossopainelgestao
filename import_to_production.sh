#!/bin/bash
###############################################################################
# Script de Importação para PRODUÇÃO - Nosso Painel Gestão
#
# ATENÇÃO: Este script SUBSTITUI o banco de dados atual!
# Use apenas em produção após testar o dump em desenvolvimento
###############################################################################

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Verifica se foi passado o arquivo de dump
if [ -z "$1" ]; then
    echo -e "${RED}❌ Uso: $0 <arquivo_dump.sql.gz> [arquivo_media.tar.gz]${NC}"
    echo ""
    echo -e "${YELLOW}Exemplo:${NC}"
    echo "  $0 nossopaineldb_20251026_231000.sql.gz media_20251026_231000.tar.gz"
    exit 1
fi

DUMP_FILE="$1"
MEDIA_FILE="$2"

# Verifica se arquivo existe
if [ ! -f "$DUMP_FILE" ]; then
    echo -e "${RED}❌ Arquivo não encontrado: $DUMP_FILE${NC}"
    exit 1
fi

echo -e "${RED}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${RED}║              ⚠️  IMPORTAÇÃO PARA PRODUÇÃO  ⚠️                 ║${NC}"
echo -e "${RED}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${RED}ATENÇÃO: Esta operação irá:${NC}"
echo -e "${RED}  1. SUBSTITUIR completamente o banco de dados atual${NC}"
echo -e "${RED}  2. PARAR os serviços da aplicação${NC}"
echo -e "${RED}  3. Restaurar arquivos de mídia (se fornecido)${NC}"
echo ""
echo -e "${YELLOW}Arquivo dump: $DUMP_FILE${NC}"
if [ -n "$MEDIA_FILE" ]; then
    echo -e "${YELLOW}Arquivo mídia: $MEDIA_FILE${NC}"
fi
echo ""
echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${RED}RECOMENDAÇÃO: Faça backup do banco atual antes de continuar!${NC}"
echo -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
echo ""
read -p "Deseja continuar? Digite 'SIM' em maiúsculas para confirmar: " -r
echo

if [ "$REPLY" != "SIM" ]; then
    echo -e "${YELLOW}Operação cancelada${NC}"
    exit 0
fi

# Carrega variáveis de ambiente (apenas DB_*)
if [ -f .env ]; then
    while IFS='=' read -r key value; do
        # Remove espaços, aspas e line endings (CR/LF)
        key=$(echo "$key" | xargs | tr -d '\r')
        value=$(echo "$value" | xargs | sed "s/^['\"]//;s/['\"]$//" | tr -d '\r')
        if [[ $key == DB_* ]]; then
            export "$key=$value"
        fi
    done < <(grep -E '^DB_' .env)
else
    echo -e "${RED}❌ Arquivo .env não encontrado!${NC}"
    echo -e "${YELLOW}   Configure o .env com as credenciais do MySQL${NC}"
    exit 1
fi

DB_NAME="${DB_NAME:-nossopaineldb}"
DB_USER="${DB_USER:-nossopaineluser}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"
DB_PASSWORD="${DB_PASSWORD}"

# Verifica se está usando MySQL
if [ "$DB_ENGINE" != "mysql" ]; then
    echo -e "${RED}❌ O .env não está configurado para MySQL!${NC}"
    echo -e "${YELLOW}   Configure DB_ENGINE=mysql no arquivo .env${NC}"
    exit 1
fi

# 1. BACKUP DO BANCO ATUAL
echo -e "\n${YELLOW}════════════════════════════════════════════${NC}"
echo -e "${YELLOW}ETAPA 1: Backup do banco atual${NC}"
echo -e "${YELLOW}════════════════════════════════════════════${NC}"

BACKUP_DIR="backups_pre_migration"
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
CURRENT_BACKUP="${BACKUP_DIR}/backup_before_import_${TIMESTAMP}.sql.gz"

echo -e "${YELLOW}➤ Criando backup de segurança...${NC}"
mysqldump \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --user="$DB_USER" \
    --password="$DB_PASSWORD" \
    --single-transaction \
    --routines \
    --triggers \
    --default-character-set=utf8mb4 \
    "$DB_NAME" 2>/dev/null | gzip -9 > "$CURRENT_BACKUP"

if [ $? -eq 0 ]; then
    BACKUP_SIZE=$(du -h "$CURRENT_BACKUP" | cut -f1)
    echo -e "${GREEN}✅ Backup atual salvo: $CURRENT_BACKUP (Tamanho: $BACKUP_SIZE)${NC}"
else
    echo -e "${YELLOW}⚠️  Não foi possível criar backup (banco pode não existir ainda)${NC}"
fi

# 2. PARAR SERVIÇOS
echo -e "\n${YELLOW}════════════════════════════════════════════${NC}"
echo -e "${YELLOW}ETAPA 2: Parar serviços${NC}"
echo -e "${YELLOW}════════════════════════════════════════════${NC}"

if command -v supervisorctl &> /dev/null; then
    echo -e "${YELLOW}➤ Parando serviços do Supervisor...${NC}"
    sudo supervisorctl stop all
    echo -e "${GREEN}✅ Serviços parados${NC}"
else
    echo -e "${YELLOW}⚠️  Supervisor não encontrado, pulando...${NC}"
fi

# 3. RECRIAR BANCO DE DADOS
echo -e "\n${YELLOW}════════════════════════════════════════════${NC}"
echo -e "${YELLOW}ETAPA 3: Recriar banco de dados${NC}"
echo -e "${YELLOW}════════════════════════════════════════════${NC}"

echo -e "${YELLOW}➤ Removendo banco atual...${NC}"
mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -e "DROP DATABASE IF EXISTS $DB_NAME" 2>/dev/null
echo -e "${GREEN}✅ Banco removido${NC}"

echo -e "${YELLOW}➤ Criando novo banco...${NC}"
mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -e "CREATE DATABASE $DB_NAME CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
echo -e "${GREEN}✅ Banco criado${NC}"

# 4. IMPORTAR DUMP
echo -e "\n${YELLOW}════════════════════════════════════════════${NC}"
echo -e "${YELLOW}ETAPA 4: Importar dados${NC}"
echo -e "${YELLOW}════════════════════════════════════════════${NC}"

echo -e "${YELLOW}➤ Descompactando e importando dump...${NC}"
echo -e "${YELLOW}   Isso pode levar alguns minutos para grandes bancos...${NC}"

gunzip -c "$DUMP_FILE" | mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Dados importados com sucesso!${NC}"
else
    echo -e "${RED}❌ ERRO na importação!${NC}"
    echo -e "${YELLOW}   Restaurando backup anterior...${NC}"
    gunzip -c "$CURRENT_BACKUP" | mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" "$DB_NAME"
    echo -e "${RED}   Banco restaurado para estado anterior${NC}"
    exit 1
fi

# 5. RESTAURAR ARQUIVOS DE MÍDIA
if [ -n "$MEDIA_FILE" ] && [ -f "$MEDIA_FILE" ]; then
    echo -e "\n${YELLOW}════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}ETAPA 5: Restaurar arquivos de mídia${NC}"
    echo -e "${YELLOW}════════════════════════════════════════════${NC}"

    echo -e "${YELLOW}➤ Extraindo arquivos de mídia...${NC}"
    tar -xzf "$MEDIA_FILE"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Arquivos de mídia restaurados${NC}"
    else
        echo -e "${YELLOW}⚠️  Erro ao restaurar mídia (não crítico)${NC}"
    fi
fi

# 6. VALIDAR DADOS
echo -e "\n${YELLOW}════════════════════════════════════════════${NC}"
echo -e "${YELLOW}ETAPA 6: Validar dados importados${NC}"
echo -e "${YELLOW}════════════════════════════════════════════${NC}"

echo -e "${YELLOW}➤ Contando registros...${NC}"

USERS_COUNT=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -D"$DB_NAME" -se "SELECT COUNT(*) FROM auth_user" 2>/dev/null || echo "0")
CLIENTES_COUNT=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -D"$DB_NAME" -se "SELECT COUNT(*) FROM cadastros_cliente" 2>/dev/null || echo "0")
MENSALIDADES_COUNT=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -D"$DB_NAME" -se "SELECT COUNT(*) FROM cadastros_mensalidade" 2>/dev/null || echo "0")

echo ""
echo -e "${GREEN}📊 Estatísticas:${NC}"
echo "   ├─ Users: $USERS_COUNT"
echo "   ├─ Clientes: $CLIENTES_COUNT"
echo "   └─ Mensalidades: $MENSALIDADES_COUNT"

# 7. APLICAR MIGRAÇÕES (se necessário)
echo -e "\n${YELLOW}════════════════════════════════════════════${NC}"
echo -e "${YELLOW}ETAPA 7: Aplicar migrações pendentes${NC}"
echo -e "${YELLOW}════════════════════════════════════════════${NC}"

if [ -f "manage.py" ]; then
    echo -e "${YELLOW}➤ Verificando migrações...${NC}"

    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi

    python manage.py migrate --noinput

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Migrações aplicadas${NC}"
    else
        echo -e "${YELLOW}⚠️  Erro ao aplicar migrações${NC}"
    fi
fi

# 8. COLETAR ARQUIVOS ESTÁTICOS
echo -e "\n${YELLOW}════════════════════════════════════════════${NC}"
echo -e "${YELLOW}ETAPA 8: Coletar arquivos estáticos${NC}"
echo -e "${YELLOW}════════════════════════════════════════════${NC}"

if [ -f "manage.py" ]; then
    echo -e "${YELLOW}➤ Coletando arquivos estáticos...${NC}"

    python manage.py collectstatic --noinput

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Arquivos estáticos coletados${NC}"
    fi
fi

# 9. REINICIAR SERVIÇOS
echo -e "\n${YELLOW}════════════════════════════════════════════${NC}"
echo -e "${YELLOW}ETAPA 9: Reiniciar serviços${NC}"
echo -e "${YELLOW}════════════════════════════════════════════${NC}"

if command -v supervisorctl &> /dev/null; then
    echo -e "${YELLOW}➤ Reiniciando serviços...${NC}"
    sudo supervisorctl start all
    sleep 2
    sudo supervisorctl status
    echo -e "${GREEN}✅ Serviços reiniciados${NC}"
fi

# RESUMO FINAL
echo -e "\n${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           IMPORTAÇÃO CONCLUÍDA COM SUCESSO!                  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}✅ Banco de dados importado e validado${NC}"
echo -e "${GREEN}✅ Serviços reiniciados${NC}"
echo ""
echo -e "${YELLOW}📌 Próximos passos:${NC}"
echo ""
echo -e "${YELLOW}1. Testar a aplicação:${NC}"
echo "   - Acesse a aplicação no navegador"
echo "   - Faça login com cada usuário (jrg, megatv, blacktv)"
echo "   - Verifique o dashboard e funcionalidades"
echo ""
echo -e "${YELLOW}2. Monitorar logs do scheduler:${NC}"
echo "   - tail -f logs/Scheduler/scheduler.log"
echo "   - Aguarde a próxima execução agendada"
echo "   - Verifique se NÃO aparece 'database is locked'"
echo ""
echo -e "${YELLOW}3. Backup de segurança salvo em:${NC}"
echo "   $CURRENT_BACKUP"
echo "   (pode ser removido após validação completa)"
echo ""
echo -e "${GREEN}🎉 Migração para MySQL concluída!${NC}"
echo ""
