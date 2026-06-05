"""
Configurações financeiras do operador.
Um registro de capital por usuário (isolamento por dono).
"""
from decimal import Decimal
from django.db import models
from core.models import BaseModel
from core.ownership import owner_field

# UUID do registro global legado (capital pré-isolamento, owner = NULL).
LEGADO_CAPITAL_ID = '00000000-0000-0000-0000-000000000001'


class CapitalOperacional(BaseModel):
    """
    Capital total disponível de um operador (usuário).
    Capital em caixa = total_capital - capital_emprestado (dos empréstimos do dono).

    Use CapitalOperacional.get_for_user(user) para acessar o registro do usuário.
    """
    # owner único: um registro de capital por usuário. NULL = registro legado.
    owner = owner_field(unique=True)

    total_capital = models.DecimalField(
        max_digits=14, decimal_places=2,
        default=Decimal('0'),
        verbose_name='Capital Total do Operador',
        help_text='Soma de todo o capital disponível para empréstimos.',
    )
    observacoes = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Capital Operacional'
        verbose_name_plural = 'Capital Operacional'

    def __str__(self):
        return f"Capital Total: R$ {self.total_capital}"

    @classmethod
    def get_for_user(cls, user):
        """Retorna ou cria o registro de capital do usuário."""
        obj, _ = cls.objects.get_or_create(
            owner=user,
            defaults={'total_capital': Decimal('0')},
        )
        return obj

    @classmethod
    def get_instance(cls):
        """Registro global legado (owner=NULL). Mantido para compatibilidade
        (seed, métricas globais). Novas telas usam get_for_user."""
        obj, _ = cls.objects.get_or_create(
            id=LEGADO_CAPITAL_ID,
            defaults={'total_capital': Decimal('0')},
        )
        return obj

    @property
    def capital_emprestado(self) -> Decimal:
        """Capital na rua dos empréstimos visíveis ao dono (dono + legado)."""
        from loans.infrastructure.models import Emprestimo
        from core.ownership import escopo_opcional
        from django.db.models import Sum
        qs = Emprestimo.objects.filter(
            status__in=['ativo', 'inadimplente'],
            deleted_at__isnull=True,
        )
        qs = escopo_opcional(qs, self.owner)
        return qs.aggregate(total=Sum('capital_atual'))['total'] or Decimal('0')

    @property
    def juros_recebidos(self) -> Decimal:
        """Total de juros já recebidos (lucro que engrossa o caixa)."""
        from payments.infrastructure.models import Pagamento
        from core.ownership import escopo_opcional
        from django.db.models import Sum
        qs = escopo_opcional(
            Pagamento.objects.filter(deleted_at__isnull=True), self.owner
        )
        return qs.aggregate(t=Sum('valor_juros_pagos'))['t'] or Decimal('0')

    @property
    def capital_em_operacao(self) -> Decimal:
        """Total que o operador controla = capital aportado + lucro recebido."""
        return self.total_capital + self.juros_recebidos

    @property
    def capital_em_caixa(self) -> Decimal:
        """Disponível = total em operação − o que está emprestado na rua."""
        return self.capital_em_operacao - self.capital_emprestado


class MovimentacaoCapital(BaseModel):
    """
    Histórico de movimentações de capital do operador.

    - aporte/retirada: ajustes manuais do capital aportado (afetam total_capital).
    - emprestimo/recebimento: lançamentos automáticos (informativos) quando um
      empréstimo é criado ou um pagamento é recebido. O caixa disponível é
      sempre derivado de total_capital + juros − emprestado (ver
      CapitalOperacional), então estes lançamentos servem ao histórico/auditoria.
    """
    TIPO_CHOICES = [
        ('aporte', 'Aporte (entrada de crédito)'),
        ('retirada', 'Retirada'),
        ('emprestimo', 'Empréstimo concedido'),
        ('recebimento', 'Recebimento'),
    ]

    owner = owner_field()
    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES, db_index=True)
    valor = models.DecimalField(max_digits=14, decimal_places=2)
    data = models.DateField(db_index=True)
    descricao = models.CharField(max_length=200, blank=True, null=True)
    emprestimo = models.ForeignKey(
        'loans.Emprestimo', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='movimentacoes_capital',
    )

    class Meta:
        verbose_name = 'Movimentação de Capital'
        verbose_name_plural = 'Movimentações de Capital'
        ordering = ['-data', '-created_at']

    def __str__(self):
        return f"{self.get_tipo_display()} — R$ {self.valor} ({self.data})"

    @property
    def sinal(self) -> int:
        """+1 entra no caixa, -1 sai."""
        return 1 if self.tipo in ('aporte', 'recebimento') else -1


class ConfiguracaoNotificacao(BaseModel):
    """
    Preferências de notificação de vencimentos por usuário (P10).
    Estrutura preparada para envio futuro por e-mail — sem envio automático
    nesta versão.
    """
    owner = owner_field(unique=True)
    ativo = models.BooleanField(default=False, help_text='Liga/desliga as notificações.')
    notificar_1_dia = models.BooleanField(default=False)
    notificar_3_dias = models.BooleanField(default=False)
    notificar_7_dias = models.BooleanField(default=False)
    canal = models.CharField(
        max_length=20, default='email',
        help_text='Canal de envio (preparado para e-mail).',
    )

    class Meta:
        verbose_name = 'Configuração de Notificação'
        verbose_name_plural = 'Configurações de Notificação'

    def __str__(self):
        return f'Notificações de {self.owner_id} ({"on" if self.ativo else "off"})'

    @classmethod
    def get_for_user(cls, user):
        obj, _ = cls.objects.get_or_create(owner=user)
        return obj
