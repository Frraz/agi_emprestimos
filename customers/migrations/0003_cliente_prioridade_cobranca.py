from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0002_add_profissao_estadocivil_residencia'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='prioridade_cobranca',
            field=models.CharField(
                choices=[('essencial', 'Essencial'), ('preferencial', 'Preferencial')],
                db_index=True,
                default='preferencial',
                help_text='Essencial = cobrar primeiro; Preferencial = prioridade normal.',
                max_length=12,
            ),
        ),
    ]
