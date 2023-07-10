from django.test import TestCase
from datetime import datetime
log_directory = './logs/'
log_filename = os.path.join(log_directory, 'cron.log')
import os

# Create your tests here.

# Verificar se o diretório de logs existe e criar se necessário
if not os.path.exists(log_directory):
    os.makedirs(log_directory)
# Verificar se o arquivo de log existe e criar se necessário
if not os.path.isfile(log_filename):
    open(log_filename, 'w').close()

with open(log_filename, 'a') as log_file:
    log_file.write('Teste ' + datetime.now().strftime("%d-%m-%Y %H:%M:%S"))
