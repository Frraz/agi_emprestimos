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
    def capital_em_caixa(self) -> Decimal:
        return max(Decimal('0'), self.total_capital - self.capital_emprestado)
