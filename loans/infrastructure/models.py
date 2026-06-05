"""
Models Django para Empréstimos e Parcelas.
"""
from datetime import date
from decimal import Decimal
from django.db import models
from core.models import BaseModel
from core.ownership import owner_field
from core.validators import validate_taxa_juros, validate_capital_positivo


class EmprestimoQuerySet(models.QuerySet):
    """
    Espelha, no ORM, os predicados de atraso definidos em
    loans.domain.calculators.CalculadoraAtraso — fonte única da verdade.
    """

    def for_user(self, user):
        """Restringe ao dono + legado (owner NULL). Ver core/ownership.py."""
        from core.ownership import filtrar_por_usuario
        return filtrar_por_usuario(self, user)

    def ativos(self):
        return self.filter(
            status__in=['ativo', 'inadimplente'],
            deleted_at__isnull=True,
        )

    def vencidos(self, ref: date = None):
        """
        Empréstimos em atraso por DATA (independe do cron já ter rodado):
          • comum: tem data_vencimento e ela já passou;
          • parcelado: tem ao menos uma parcela em aberto já vencida.
        """
        ref = ref or date.today()
        comum_q = models.Q(
            tipo='comum',
            data_vencimento__isnull=False,
            data_vencimento__lt=ref,
        )
        parcelado_q = models.Q(
            tipo='parcelado',
            parcelas__status__in=['pendente', 'parcialmente_pago', 'atrasado'],
            parcelas__data_vencimento__lt=ref,
        )
        return self.ativos().filter(comum_q | parcelado_q).distinct()


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
    # Isolamento por usuário (NULL = legado compartilhado). Ver core/ownership.py.
    owner = owner_field()

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
    juros_acumulados = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0'),
        help_text=(
            'Juros já lançados e ainda em aberto (empréstimo comum). '
            'NÃO rende juros — sem capitalização (juros sobre juros).'
        ),
    )
    data_ultimo_acumulo = models.DateField(
        null=True, blank=True,
        help_text=(
            'Data do último ciclo de juros lançado em juros_acumulados. '
            'Controla o acúmulo idempotente feito pelo cron.'
        ),
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

    objects = EmprestimoQuerySet.as_manager()

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

    # ── Atraso (delega ao domínio; baseado em data, não no status) ──────────
    @property
    def juros_mes(self) -> Decimal:
        """Juros do mês corrente (empréstimo comum)."""
        from loans.domain.calculators import CalculadoraEmprestimoComum
        return CalculadoraEmprestimoComum.calcular_juros_mes(
            self.capital_atual, self.taxa_juros_mensal
        )

    @property
    def total_quitacao(self) -> Decimal:
        """Valor para quitar hoje: capital + juros acumulados (empréstimo comum)."""
        from loans.domain.calculators import CalculadoraEmprestimoComum
        return CalculadoraEmprestimoComum.calcular_total_quitacao(
            self.capital_atual, self.juros_acumulados
        )

    @property
    def esta_vencido(self) -> bool:
        from loans.domain.calculators import CalculadoraAtraso
        ref = date.today()
        if self.tipo == 'comum':
            return CalculadoraAtraso.esta_vencido_comum(
                self.status, self.data_vencimento, ref
            )
        if self.tipo == 'parcelado':
            if self.status not in ('ativo', 'inadimplente'):
                return False
            return any(p.esta_atrasada for p in self.parcelas.all())
        return False

    @property
    def dias_atraso(self) -> int:
        from loans.domain.calculators import CalculadoraAtraso
        ref = date.today()
        if self.tipo == 'comum':
            if not self.esta_vencido:
                return 0
            return CalculadoraAtraso.dias_atraso(self.data_vencimento, ref)
        if self.tipo == 'parcelado':
            atrasos = [
                CalculadoraAtraso.dias_atraso(p.data_vencimento, ref)
                for p in self.parcelas.all() if p.esta_atrasada
            ]
            return max(atrasos) if atrasos else 0
        return 0

    @property
    def valor_em_atraso(self) -> Decimal:
        """
        Valor em atraso para fins de cobrança.
        Comum: saldo devedor atual (capital_atual). Parcelado: soma do
        valor em aberto das parcelas vencidas.
        """
        if self.tipo == 'comum':
            return self.total_quitacao if self.esta_vencido else Decimal('0')
        if self.tipo == 'parcelado':
            return sum(
                (p.valor_em_aberto for p in self.parcelas.all() if p.esta_atrasada),
                Decimal('0'),
            )
        return Decimal('0')

    @property
    def obrigacao_mensal(self) -> Decimal:
        """
        Obrigação mensal estimada do cliente para este empréstimo, usada no
        cálculo de comprometimento de renda. Comum: juros do mês. Parcelado:
        valor da próxima parcela em aberto. Zero se o empréstimo não está ativo.
        """
        if self.status not in ('ativo', 'inadimplente'):
            return Decimal('0')
        if self.tipo == 'comum':
            return self.juros_mes
        if self.tipo == 'parcelado':
            proxima = (
                self.parcelas
                .filter(status__in=['pendente', 'parcialmente_pago', 'atrasado'])
                .order_by('numero')
                .first()
            )
            return proxima.valor_parcela if proxima else Decimal('0')
        return Decimal('0')


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