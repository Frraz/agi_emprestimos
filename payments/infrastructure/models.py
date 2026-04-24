"""
Model de Pagamento — imutável após criação (histórico financeiro).
Nunca edite pagamentos; cancele e registre novo se necessário.
"""
from decimal import Decimal
from django.db import models
from core.models import BaseModel


class Pagamento(BaseModel):

    TIPO_CHOICES = [
        ('juros', 'Apenas Juros'),
        ('capital_parcial', 'Capital Parcial + Juros'),
        ('capital_total', 'Quitação Total (Capital + Juros)'),
        ('parcela', 'Parcela Parcelada'),
    ]

    # ── Relacionamentos ────────────────────────────────────────────────────
    emprestimo = models.ForeignKey(
        'loans.Emprestimo',
        on_delete=models.PROTECT,
        related_name='pagamentos',
    )
    parcela = models.ForeignKey(
        'loans.ParcelaEmprestimo',
        null=True, blank=True,
        on_delete=models.PROTECT,
        related_name='pagamentos_parcela',
    )
    registrado_por = models.ForeignKey(
        'auth.User', on_delete=models.PROTECT
    )

    # ── Valores ────────────────────────────────────────────────────────────
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    data_pagamento = models.DateField(db_index=True)

    # Detalhamento para relatório e auditoria
    valor_juros_pagos = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    valor_capital_pago = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )

    # Snapshot do saldo antes/depois — rastreabilidade completa
    capital_antes = models.DecimalField(max_digits=12, decimal_places=2)
    capital_depois = models.DecimalField(max_digits=12, decimal_places=2)

    observacoes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Pagamento'
        verbose_name_plural = 'Pagamentos'
        ordering = ['-data_pagamento', '-created_at']
        indexes = [
            models.Index(fields=['emprestimo', 'data_pagamento']),
        ]

    def __str__(self):
        return (
            f"Pagamento R${self.valor} "
            f"— {self.emprestimo.cliente.nome} "
            f"em {self.data_pagamento}"
        )