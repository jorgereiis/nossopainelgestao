#!/bin/bash
###############################################################################
# Script de Backup MySQL - Nosso Painel Gestão
#
# Cria backup completo do banco de dados MySQL usando mysqldump
# Melhor prática para migração de desenvolvimento → produção
###############################################################################

set -e  # Para execução em caso de erro

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Carrega variáveis de ambiente do .env (apenas DB_*)
if [ -f .env ]; then
    while IFS='=' read -r key value; do
        # Remove espaços, aspas e line endings (CR/LF)
        key=$(echo "$key" | xargs | tr -d '\r')
        value=$(echo "$value" | xargs | sed "s/^['\"]//;s/['\"]$//" | tr -d '\r')

        # Exporta apenas variáveis DB_*
        if [[ $key == DB_* ]]; then
            export "$key=$value"
        fi
    done < <(grep -E '^DB_' .env)
else
    echo -e "${RED}❌ Arquivo .env não encontrado!${NC}"
    exit 1
fi

# Configurações
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="backups_mysql"
BACKUP_FILE="${BACKUP_DIR}/nossopaineldb_${TIMESTAMP}.sql"
BACKUP_FILE_GZ="${BACKUP_FILE}.gz"
MEDIA_BACKUP="${BACKUP_DIR}/media_${TIMESTAMP}.tar.gz"

# Informações do banco
DB_NAME="${DB_NAME:-nossopaineldb}"
DB_USER="${DB_USER:-nossopaineluser}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"
DB_PASSWORD="${DB_PASSWORD}"

echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         BACKUP MySQL - Nosso Painel Gestão                   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Cria diretório de backup se não existir
mkdir -p "$BACKUP_DIR"

# Verifica se MySQL está acessível
echo -e "${YELLOW}➤ Verificando conexão com MySQL...${NC}"
if ! mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"${DB_PASSWORD}" -e "SELECT 1" > /dev/null 2>&1; then
    echo -e "${RED}❌ Não foi possível conectar ao MySQL!${NC}"
    echo -e "${RED}   Verifique as credenciais no arquivo .env${NC}"
    echo -e "${YELLOW}   Debug: DB_USER=$DB_USER, DB_HOST=$DB_HOST${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Conexão com MySQL OK${NC}"

# Informações do banco
echo -e "\n${YELLOW}➤ Informações do banco:${NC}"
echo "   Database: $DB_NAME"
echo "   User: $DB_USER"
echo "   Host: $DB_HOST"
echo "   Port: $DB_PORT"

# Conta registros (para validação posterior)
echo -e "\n${YELLOW}➤ Contando registros...${NC}"
USERS_COUNT=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -D"$DB_NAME" -se "SELECT COUNT(*) FROM auth_user")
CLIENTES_COUNT=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -D"$DB_NAME" -se "SELECT COUNT(*) FROM cadastros_cliente")
MENSALIDADES_COUNT=$(mysql -h"$DB_HOST" -P"$DB_PORT" -u"$DB_USER" -p"$DB_PASSWORD" -D"$DB_NAME" -se "SELECT COUNT(*) FROM cadastros_mensalidade")

echo "   Users: $USERS_COUNT"
echo "   Clientes: $CLIENTES_COUNT"
echo "   Mensalidades: $MENSALIDADES_COUNT"

# Cria arquivo de contagens para validação
cat > "${BACKUP_DIR}/counts_${TIMESTAMP}.txt" <<EOF
=== CONTAGENS DO BACKUP ===
Data: $(date)
Users: $USERS_COUNT
Clientes: $CLIENTES_COUNT
Mensalidades: $MENSALIDADES_COUNT
EOF

# Cria dump do banco de dados
echo -e "\n${YELLOW}➤ Criando dump do banco de dados...${NC}"
echo "   Arquivo: $BACKUP_FILE"

mysqldump \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --user="$DB_USER" \
    --password="$DB_PASSWORD" \
    --single-transaction \
    --routines \
    --triggers \
    --events \
    --default-character-set=utf8mb4 \
    --add-drop-table \
    --quick \
    --lock-tables=false \
    "$DB_NAME" > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    DUMP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}✅ Dump criado com sucesso! (Tamanho: $DUMP_SIZE)${NC}"
else
    echo -e "${RED}❌ Erro ao criar dump!${NC}"
    exit 1
fi

# Compacta o dump
echo -e "\n${YELLOW}➤ Compactando dump...${NC}"
gzip -9 "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    GZ_SIZE=$(du -h "$BACKUP_FILE_GZ" | cut -f1)
    echo -e "${GREEN}✅ Dump compactado! (Tamanho: $GZ_SIZE)${NC}"
else
    echo -e "${RED}❌ Erro ao compactar dump!${NC}"
    exit 1
fi

# Backup dos arquivos de mídia
echo -e "\n${YELLOW}➤ Criando backup dos arquivos de mídia...${NC}"
if [ -d "media" ]; then
    tar -czf "$MEDIA_BACKUP" media/

    if [ $? -eq 0 ]; then
        MEDIA_SIZE=$(du -h "$MEDIA_BACKUP" | cut -f1)
        echo -e "${GREEN}✅ Backup de mídia criado! (Tamanho: $MEDIA_SIZE)${NC}"
    else
        echo -e "${YELLOW}⚠️  Aviso: Erro ao criar backup de mídia${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Diretório 'media' não encontrado, pulando backup de mídia${NC}"
fi

# Cria arquivo README com instruções
cat > "${BACKUP_DIR}/README_${TIMESTAMP}.txt" <<EOF
╔══════════════════════════════════════════════════════════════╗
║         BACKUP MySQL - Nosso Painel Gestão                   ║
╚══════════════════════════════════════════════════════════════╝

Data do backup: $(date)

ARQUIVOS INCLUÍDOS:
  - nossopaineldb_${TIMESTAMP}.sql.gz  → Dump do banco de dados (compactado)
  - media_${TIMESTAMP}.tar.gz          → Arquivos de mídia (avatars, uploads)
  - counts_${TIMESTAMP}.txt            → Contagens para validação
  - README_${TIMESTAMP}.txt            → Este arquivo

CONTAGENS:
  Users: $USERS_COUNT
  Clientes: $CLIENTES_COUNT
  Mensalidades: $MENSALIDADES_COUNT

═══════════════════════════════════════════════════════════════
INSTRUÇÕES PARA IMPORTAÇÃO EM PRODUÇÃO
═══════════════════════════════════════════════════════════════

1. TRANSFERIR ARQUIVOS PARA O SERVIDOR DE PRODUÇÃO:

   scp backups_mysql/nossopaineldb_${TIMESTAMP}.sql.gz user@servidor:/caminho/destino/
   scp backups_mysql/media_${TIMESTAMP}.tar.gz user@servidor:/caminho/destino/

2. NO SERVIDOR DE PRODUÇÃO, CRIAR BANCO DE DADOS:

   mysql -u root -p

   CREATE DATABASE nossopaineldb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'nossopaineluser'@'localhost' IDENTIFIED BY 'SENHA_FORTE_AQUI';
   GRANT ALL PRIVILEGES ON nossopaineldb.* TO 'nossopaineluser'@'localhost';
   FLUSH PRIVILEGES;
   exit;

3. DESCOMPACTAR E IMPORTAR DUMP:

   gunzip nossopaineldb_${TIMESTAMP}.sql.gz

   mysql -u nossopaineluser -p nossopaineldb < nossopaineldb_${TIMESTAMP}.sql

4. RESTAURAR ARQUIVOS DE MÍDIA:

   cd /caminho/do/projeto
   tar -xzf /caminho/destino/media_${TIMESTAMP}.tar.gz

5. CONFIGURAR .env NO SERVIDOR DE PRODUÇÃO:

   DB_ENGINE=mysql
   DB_NAME=nossopaineldb
   DB_USER=nossopaineluser
   DB_PASSWORD=SENHA_FORTE_AQUI
   DB_HOST=localhost
   DB_PORT=3306
   DEBUG=False

6. INSTALAR DEPENDÊNCIA MySQL:

   source .venv/bin/activate
   pip install mysqlclient>=2.2.0

7. APLICAR MIGRAÇÕES (caso necessário):

   python manage.py migrate

8. VALIDAR CONTAGENS:

   python manage.py shell -c "
   from django.contrib.auth.models import User
   from cadastros.models import Cliente, Mensalidade
   print(f'Users: {User.objects.count()}')
   print(f'Clientes: {Cliente.objects.count()}')
   print(f'Mensalidades: {Mensalidade.objects.count()}')
   "

   Compare com as contagens deste arquivo!

9. COLETAR ARQUIVOS ESTÁTICOS:

   python manage.py collectstatic --noinput

10. REINICIAR SERVIÇOS:

    sudo supervisorctl restart all

═══════════════════════════════════════════════════════════════
ROLLBACK (em caso de problemas)
═══════════════════════════════════════════════════════════════

Se precisar reverter para SQLite:

1. No .env, altere:
   DB_ENGINE=sqlite

2. Restaure o db.sqlite3 do backup anterior

3. Reinicie os serviços:
   sudo supervisorctl restart all

═══════════════════════════════════════════════════════════════
IMPORTANTE - SEGURANÇA
═══════════════════════════════════════════════════════════════

⚠️  Este dump contém dados sensíveis:
   - Senhas de usuários (hashadas)
   - Números de telefone de clientes
   - Informações de pagamento
   - Credenciais de aplicativos

✓  Transferir apenas por conexões seguras (SCP/SFTP)
✓  Não compartilhar publicamente
✓  Deletar após importação bem-sucedida
✓  Manter backup em local seguro

EOF

# Resumo final
echo -e "\n${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                  BACKUP CONCLUÍDO COM SUCESSO!               ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}📁 Arquivos criados:${NC}"
echo "   ├─ $BACKUP_FILE_GZ"
if [ -f "$MEDIA_BACKUP" ]; then
    echo "   ├─ $MEDIA_BACKUP"
fi
echo "   ├─ ${BACKUP_DIR}/counts_${TIMESTAMP}.txt"
echo "   └─ ${BACKUP_DIR}/README_${TIMESTAMP}.txt"
echo ""
echo -e "${YELLOW}📊 Estatísticas:${NC}"
echo "   ├─ Users: $USERS_COUNT"
echo "   ├─ Clientes: $CLIENTES_COUNT"
echo "   └─ Mensalidades: $MENSALIDADES_COUNT"
echo ""
echo -e "${GREEN}✅ Leia o arquivo README_${TIMESTAMP}.txt para instruções de importação${NC}"
echo ""
