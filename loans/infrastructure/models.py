"""
Models Django para Empréstimos e Parcelas.
"""
from decimal import Decimal
from django.db import models
from core.models import BaseModel
from core.validators import validate_taxa_juros, validate_capital_positivo


class Emprestimo(BaseModel):

    TIPO_CHOICES = [
        ('comum', 'Comum (Sem Parcela Fixa)'),
        ('parcelado', 'Parcelado'),
        ('diaria', 'Diária'),
    ]

    SUBTIPO_PARCELADO_CHOICES = [
        ('fixo', 'Parcela Fixa (Juros sobre Capital Inicial)'),
        ('sac', 'Parcela Decrescente — SAC'),
    ]

    STATUS_CHOICES = [
        ('ativo', 'Ativo'),
        ('quitado', 'Quitado'),
        ('inadimplente', 'Inadimplente'),
        ('cancelado', 'Cancelado'),
        ('renegociado', 'Renegociado'),
    ]

    # ── Relacionamentos ────────────────────────────────────────────────────
    cliente = models.ForeignKey(
        'customers.Cliente',
        on_delete=models.PROTECT,
        related_name='emprestimos',
        db_index=True,
    )
    emprestimo_origem = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='renegociacoes',
        help_text='Preenchido quando este empréstimo é uma renegociação.',
    )
    registrado_por = models.ForeignKey(
        'auth.User',
        on_delete=models.PROTECT,
        related_name='emprestimos_registrados',
    )

    # ── Tipo ───────────────────────────────────────────────────────────────
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES, db_index=True)
    subtipo_parcelado = models.CharField(
        max_length=10, choices=SUBTIPO_PARCELADO_CHOICES,
        null=True, blank=True,
    )

    # ── Valores financeiros ────────────────────────────────────────────────
    capital_inicial = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[validate_capital_positivo],
    )
    capital_atual = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text='Saldo devedor atual. Atualizado a cada pagamento.',
    )
    taxa_juros_mensal = models.DecimalField(
        max_digits=8, decimal_places=6,
        validators=[validate_taxa_juros],
        help_text='Ex: 0.050000 = 5,00% ao mês',
    )

    # ── Parcelamento ───────────────────────────────────────────────────────
    n_parcelas = models.PositiveIntegerField(null=True, blank=True)

    # ── Datas ──────────────────────────────────────────────────────────────
    data_inicio = models.DateField(db_index=True)
    data_vencimento = models.DateField(
        null=True, blank=True, db_index=True,
        help_text='Data de vencimento final (última parcela ou vencimento avençado).',
    )
    data_quitacao = models.DateField(null=True, blank=True)

    # ── Status ─────────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default='ativo', db_index=True
    )

    observacoes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Empréstimo'
        verbose_name_plural = 'Empréstimos'
        ordering = ['-data_inicio']
        indexes = [
            models.Index(fields=['cliente', 'status']),
            models.Index(fields=['status', 'data_vencimento']),
            models.Index(fields=['tipo', 'status']),
        ]

    def __str__(self):
        return (
            f"[{self.get_tipo_display()}] {self.cliente.nome} "
            f"— R$ {self.capital_inicial} ({self.get_status_display()})"
        )

    @property
    def taxa_percentual_display(self) -> str:
        return f"{self.taxa_juros_mensal * 100:.2f}% a.m."

    @property
    def total_garantias(self) -> Decimal:
        return self.garantias.filter(deleted_at__isnull=True).aggregate(
            total=models.Sum('valor_estimado')
        )['total'] or Decimal('0')

    @property
    def total_pago(self) -> Decimal:
        return self.pagamentos.aggregate(
            total=models.Sum('valor')
        )['total'] or Decimal('0')


class ParcelaEmprestimo(BaseModel):
    """
    Gerada automaticamente pelo EmprestimoService ao criar empréstimos do tipo PARCELADO.
    Nunca crie parcelas manualmente — use o service.
    """

    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('pago', 'Pago'),
        ('parcialmente_pago', 'Parcialmente Pago'),
        ('atrasado', 'Atrasado'),
        ('cancelado', 'Cancelado'),
    ]

    emprestimo = models.ForeignKey(
        Emprestimo, on_delete=models.CASCADE, related_name='parcelas'
    )
    numero = models.PositiveIntegerField()

    # ── Valores calculados pelo domínio ────────────────────────────────────
    valor_parcela = models.DecimalField(max_digits=12, decimal_places=2)
    valor_principal = models.DecimalField(max_digits=12, decimal_places=2)
    valor_juros = models.DecimalField(max_digits=12, decimal_places=2)
    saldo_devedor_antes = models.DecimalField(max_digits=12, decimal_places=2)
    saldo_devedor_depois = models.DecimalField(max_digits=12, decimal_places=2)

    # ── Controle de pagamento ──────────────────────────────────────────────
    valor_pago = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0')
    )
    data_vencimento = models.DateField(db_index=True)
    data_pagamento = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pendente', db_index=True
    )

    class Meta:
        verbose_name = 'Parcela'
        verbose_name_plural = 'Parcelas'
        ordering = ['emprestimo', 'numero']
        unique_together = [('emprestimo', 'numero')]

    def __str__(self):
        return f"Parcela {self.numero}/{self.emprestimo.n_parcelas} — {self.emprestimo}"

    @property
    def valor_em_aberto(self) -> Decimal:
        return self.valor_parcela - self.valor_pago

    @property
    def esta_atrasada(self) -> bool:
        from datetime import date
        return (
            self.status in ('pendente', 'parcialmente_pago')
            and self.data_vencimento < date.today()
        )