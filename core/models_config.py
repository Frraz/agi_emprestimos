"""
Configurações financeiras do operador.
Singleton — existe apenas um registro por sistema.
"""
from decimal import Decimal
from django.db import models
from core.models import BaseModel


class CapitalOperacional(BaseModel):
    """
    Representa o capital total disponível do operador.
    Capital em caixa = total_capital - capital_emprestado
    
    Use CapitalOperacional.get_instance() para acessar.
    """
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
    def get_instance(cls):
        """Retorna ou cria o registro único de capital operacional."""
        obj, _ = cls.objects.get_or_create(
            id='00000000-0000-0000-0000-000000000001',
            defaults={'total_capital': Decimal('0')},
        )
        return obj

    @property
    def capital_emprestado(self) -> Decimal:
        from loans.infrastructure.models import Emprestimo
        from django.db.models import Sum
        result = Emprestimo.objects.filter(
            status__in=['ativo', 'inadimplente'],
            deleted_at__isnull=True,
        ).aggregate(total=Sum('capital_atual'))['total']
        return result or Decimal('0')

    @property
    def capital_em_caixa(self) -> Decimal:
        return max(Decimal('0'), self.total_capital - self.capital_emprestado)