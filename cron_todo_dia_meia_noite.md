Para configurar o cron (roda todo dia à meia-noite):

crontab -e
# Adicione a linha:
1 0 * * * /home/ferraz/Área\ de\ trabalho/Projetos/agi_emprestimos/venv/bin/python /home/ferraz/Área\ de\ trabalho/Projetos/agi_emprestimos/manage.py atualizar_inadimplencia >> /tmp/agi_inadimplencia.log 2>&1