"""
Value Objects do domínio de empréstimos.
Imutáveis, sem identidade — representam conceitos financeiros.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class Dinheiro:
    """Representa um valor monetário. Nunca permite negativos."""
    valor: Decimal

    def __post_init__(self):
        if self.valor < Decimal('0'):
            raise ValueError(f"Valor monetário não pode ser negativo: {self.valor}")

    def __add__(self, other: 'Dinheiro') -> 'Dinheiro':
        return Dinheiro(self.valor + other.valor)

    def __sub__(self, other: 'Dinheiro') -> 'Dinheiro':
        return Dinheiro(max(Decimal('0'), self.valor - other.valor))

    def __mul__(self, fator) -> 'Dinheiro':
        resultado = self.valor * Decimal(str(fator))
        return Dinheiro(resultado.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))

    def __str__(self):
        return f"R$ {self.valor:.2f}"

    @property
    def formatado(self) -> str:
        v = f"{self.valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"R$ {v}"


@dataclass(frozen=True)
class TaxaJuros:
    """
    Taxa de juros mensal.
    valor: decimal entre 0 e 1. Ex: 0.05 = 5% a.m.
    """
    valor: Decimal

    def __post_init__(self):
        if not (Decimal('0') < self.valor < Decimal('1')):
            raise ValueError(
                f"Taxa de juros deve estar entre 0 e 1 (exclusivo). Recebido: {self.valor}"
            )

    @property
    def percentual(self) -> Decimal:
        return (self.valor * 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def __str__(self):
        return f"{self.percentual}% a.m."