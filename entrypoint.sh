#!/bin/sh
set -e

echo "========================================="
echo "  Agi Empréstimos — Iniciando container"
echo "========================================="

# Aguarda o PostgreSQL estar pronto
echo "→ Aguardando banco de dados..."
while ! python -c "
import os, psycopg2
try:
    psycopg2.connect(
        dbname=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        host=os.environ['DB_HOST'],
        port=os.environ.get('DB_PORT', '5432'),
    )
    print('OK')
except psycopg2.OperationalError:
    exit(1)
" 2>/dev/null; do
    echo "  Banco não disponível, aguardando 2s..."
    sleep 2
done
echo "  Banco OK."

# Aplica migrations
echo "→ Aplicando migrations..."
python manage.py migrate --noinput

# Coleta arquivos estáticos
echo "→ Coletando arquivos estáticos..."
python manage.py collectstatic --noinput --clear

echo "→ Pronto. Iniciando servidor..."
echo "========================================="

exec "$@"