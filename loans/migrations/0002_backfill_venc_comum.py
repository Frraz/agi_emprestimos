"""
Backfill de data_vencimento para empréstimos COMUNS antigos.

Bug histórico: criar_emprestimo_comum não gravava data_vencimento, deixando
o campo NULL. Sem vencimento, o empréstimo nunca era detectado como vencido.
Convenção adotada: vencimento = data_inicio + 1 mês (ciclo de crédito padrão).
"""
from django.db import migrations


def backfill_vencimento(apps, schema_editor):
    from dateutil.relativedelta import relativedelta

    Emprestimo = apps.get_model('loans', 'Emprestimo')
    qs = Emprestimo.objects.filter(tipo='comum', data_vencimento__isnull=True)
    for emp in qs.iterator():
        emp.data_vencimento = emp.data_inicio + relativedelta(months=1)
        emp.save(update_fields=['data_vencimento'])


def noop_reverse(apps, schema_editor):
    # Não revertemos: o vencimento passa a ser um dado legítimo.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('loans', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(backfill_vencimento, noop_reverse),
    ]
