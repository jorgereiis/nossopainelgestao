#!/bin/bash

# Caminho do arquivo de log
LOG_FILE_1="/g/Meu Drive/backup.log"
LOG_FILE_2="./backup.log"

# Data e hora atual
DATE=$(date +"%Y-%m-%d")
TIME=$(date +"%H:%M:%S")

# Copia o Banco para o Drive
cp -f ./db.sqlite3 "/g/Meu Drive/" 2>> "$LOG_FILE_1"

# Verifica se houve erro na cópia e registra no log
if [ $? -eq 0 ]; then
    echo "[$DATE] [$TIME] - Backup realizado com sucesso" >> "$LOG_FILE_1"
    echo "[$DATE] [$TIME] - Backup realizado com sucesso" >> "$LOG_FILE_2"
else
    echo "[$DATE] [$TIME] - O backup apresentou erro: $?" >> "$LOG_FILE_1"
    echo "[$DATE] [$TIME] - O backup apresentou erro? $?" >> "$LOG_FILE_2"
fi
