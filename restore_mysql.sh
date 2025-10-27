#!/bin/bash
###############################################################################
# Script de Restauração MySQL - Nosso Painel Gestão
#
# Restaura backup do MySQL e valida integridade
# Use para TESTAR o dump antes de importar em produção
###############################################################################

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Verifica se foi passado o arquivo de backup
if [ -z "$1" ]; then
    echo -e "${RED}❌ Uso: $0 <arquivo_backup.sql.gz>${NC}"
    echo ""
    echo -e "${YELLOW}Exemplo:${NC}"
    echo "  $0 backups_mysql/nossopaineldb_20251026_231000.sql.gz"
    echo ""
    echo -e "${YELLOW}Backups disponíveis:${NC}"
    ls -lh backups_mysql/*.sql.gz 2>/dev/null || echo "  Nenhum backup encontrado"
    exit 1
fi

BACKUP_FILE="$1"

# Verifica se arquivo existe
if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}❌ Arquivo não encontrado: $BACKUP_FILE${NC}"
    exit 1
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
    exit 1
fi

DB_NAME="${DB_NAME:-nossopaineldb}"
DB_USER="${DB_USER:-nossopaineluser}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"
DB_PASSWORD="${DB_PASSWORD}"

# Nome do banco de teste (para não sobrescrever o atual)
TEST_DB="${DB_NAME}_test"

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         RESTAURAÇÃO MySQL - Nosso Painel Gestão              ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}⚠️  ATENÇÃO: Este script irá criar um banco de TESTE${NC}"
echo -e "${YELLOW}    Banco de teste: $TEST_DB${NC}"
echo -e "${YELLOW}    Banco atual NÃO será afetado${NC}"
echo ""
read -p "Continuar? (s/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Ss]$ ]]; then
    echo -e "${YELLOW}Operação cancelada${NC}"
    exit 0
fi

# Verifica conexão MySQL
echo -e "\n${YELLOW}➤ Verificando conexão com MySQL...${NC}"
if ! mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -e "SELECT 1" > /dev/null 2>&1; then
    echo -e "${RED}❌ Não foi possível conectar ao MySQL!${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Conexão OK${NC}"

# Remove banco de teste anterior (se existir)
echo -e "\n${YELLOW}➤ Removendo banco de teste anterior (se existir)...${NC}"
mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -e "DROP DATABASE IF EXISTS $TEST_DB" 2>/dev/null
echo -e "${GREEN}✅ Pronto${NC}"

# Cria novo banco de teste
echo -e "\n${YELLOW}➤ Criando banco de teste: $TEST_DB${NC}"
mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -e "CREATE DATABASE $TEST_DB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
echo -e "${GREEN}✅ Banco criado${NC}"

# Descompacta e importa dump
echo -e "\n${YELLOW}➤ Descompactando e importando dump...${NC}"
echo "   Arquivo: $BACKUP_FILE"
echo "   Destino: $TEST_DB"
echo ""
echo -e "${YELLOW}   Isso pode levar alguns minutos...${NC}"

gunzip -c "$BACKUP_FILE" | mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" "$TEST_DB"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Importação concluída!${NC}"
else
    echo -e "${RED}❌ Erro na importação!${NC}"
    exit 1
fi

# Valida contagens
echo -e "\n${YELLOW}➤ Validando dados importados...${NC}"

USERS_COUNT=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -D"$TEST_DB" -se "SELECT COUNT(*) FROM auth_user" 2>/dev/null || echo "0")
CLIENTES_COUNT=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -D"$TEST_DB" -se "SELECT COUNT(*) FROM cadastros_cliente" 2>/dev/null || echo "0")
MENSALIDADES_COUNT=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -D"$TEST_DB" -se "SELECT COUNT(*) FROM cadastros_mensalidade" 2>/dev/null || echo "0")
HORARIOS_COUNT=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -D"$TEST_DB" -se "SELECT COUNT(*) FROM cadastros_horarioenvios" 2>/dev/null || echo "0")

echo ""
echo -e "${GREEN}📊 Estatísticas do banco restaurado:${NC}"
echo "   ├─ Users: $USERS_COUNT"
echo "   ├─ Clientes: $CLIENTES_COUNT"
echo "   ├─ Mensalidades: $MENSALIDADES_COUNT"
echo "   └─ HorarioEnvios: $HORARIOS_COUNT"

# Busca arquivo de contagens do backup
BACKUP_DIR=$(dirname "$BACKUP_FILE")
TIMESTAMP=$(basename "$BACKUP_FILE" | grep -oP '\d{8}_\d{6}')
COUNTS_FILE="${BACKUP_DIR}/counts_${TIMESTAMP}.txt"

if [ -f "$COUNTS_FILE" ]; then
    echo -e "\n${YELLOW}➤ Comparando com contagens originais...${NC}"
    cat "$COUNTS_FILE"

    # Extrai contagens do arquivo
    ORIGINAL_USERS=$(grep "Users:" "$COUNTS_FILE" | grep -oP '\d+')
    ORIGINAL_CLIENTES=$(grep "Clientes:" "$COUNTS_FILE" | grep -oP '\d+')
    ORIGINAL_MENSALIDADES=$(grep "Mensalidades:" "$COUNTS_FILE" | grep -oP '\d+')

    echo ""
    if [ "$USERS_COUNT" == "$ORIGINAL_USERS" ] && \
       [ "$CLIENTES_COUNT" == "$ORIGINAL_CLIENTES" ] && \
       [ "$MENSALIDADES_COUNT" == "$ORIGINAL_MENSALIDADES" ]; then
        echo -e "${GREEN}✅ VALIDAÇÃO PASSOU: Todas as contagens conferem!${NC}"
    else
        echo -e "${RED}⚠️  ATENÇÃO: Diferenças encontradas!${NC}"
        echo "   Users: $USERS_COUNT (esperado: $ORIGINAL_USERS)"
        echo "   Clientes: $CLIENTES_COUNT (esperado: $ORIGINAL_CLIENTES)"
        echo "   Mensalidades: $MENSALIDADES_COUNT (esperado: $ORIGINAL_MENSALIDADES)"
    fi
fi

# Testa integridade referencial
echo -e "\n${YELLOW}➤ Testando integridade referencial...${NC}"

ORPHAN_CLIENTES=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -D"$TEST_DB" -se "
    SELECT COUNT(*) FROM cadastros_cliente c
    LEFT JOIN auth_user u ON c.usuario_id = u.id
    WHERE u.id IS NULL
" 2>/dev/null || echo "0")

ORPHAN_MENSALIDADES=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -D"$TEST_DB" -se "
    SELECT COUNT(*) FROM cadastros_mensalidade m
    LEFT JOIN cadastros_cliente c ON m.cliente_id = c.id
    WHERE c.id IS NULL
" 2>/dev/null || echo "0")

if [ "$ORPHAN_CLIENTES" == "0" ] && [ "$ORPHAN_MENSALIDADES" == "0" ]; then
    echo -e "${GREEN}✅ Integridade referencial OK${NC}"
else
    echo -e "${YELLOW}⚠️  Avisos de integridade:${NC}"
    echo "   Clientes órfãos (sem user): $ORPHAN_CLIENTES"
    echo "   Mensalidades órfãs (sem cliente): $ORPHAN_MENSALIDADES"
fi

# Resumo
echo -e "\n${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                VALIDAÇÃO CONCLUÍDA COM SUCESSO!              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}📌 Próximos passos:${NC}"
echo ""
echo -e "${GREEN}1. O dump foi validado e está íntegro!${NC}"
echo ""
echo -e "${BLUE}2. Para usar este backup em PRODUÇÃO:${NC}"
echo "   - Transfira o arquivo para o servidor de produção"
echo "   - Use o script de importação ou siga o README"
echo ""
echo -e "${BLUE}3. Banco de teste criado:${NC}"
echo "   - Nome: $TEST_DB"
echo "   - Para remover: mysql -u$DB_USER -p -e \"DROP DATABASE $TEST_DB\""
echo ""
echo -e "${YELLOW}⚠️  Lembre-se: Este é um banco de TESTE${NC}"
echo -e "${YELLOW}   Seu banco atual ($DB_NAME) não foi alterado${NC}"
echo ""
