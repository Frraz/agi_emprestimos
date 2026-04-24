"""
Entidades de domínio para Empréstimos.
Classes puras — sem Django. Representam o estado e as invariantes do negócio.
"""
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional


class TipoEmprestimo(str, Enum):
    COMUM = 'comum'
    PARCELADO = 'parcelado'
    DIARIA = 'diaria'


class SubtipoParcelado(str, Enum):
    FIXO = 'fixo'   # Parcela fixa com juros sobre capital inicial
    SAC = 'sac'     # Sistema de Amortização Constante (parcela decrescente)


class StatusEmprestimo(str, Enum):
    ATIVO = 'ativo'
    QUITADO = 'quitado'
    INADIMPLENTE = 'inadimplente'
    CANCELADO = 'cancelado'
    RENEGOCIADO = 'renegociado'


class StatusParcela(str, Enum):
    PENDENTE = 'pendente'
    PAGO = 'pago'
    PARCIALMENTE_PAGO = 'parcialmente_pago'
    ATRASADO = 'atrasado'
    CANCELADO = 'cancelado'


@dataclass
class EmprestimoEntity:
    """
    Invariantes obrigatórias:
    - capital_inicial > 0
    - 0 < taxa_juros_mensal < 1
    - tipo PARCELADO requer n_parcelas e subtipo_parcelado
    """
    cliente_id: str
    tipo: TipoEmprestimo
    capital_inicial: Decimal
    taxa_juros_mensal: Decimal
    data_inicio: date

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    subtipo_parcelado: Optional[SubtipoParcelado] = None
    n_parcelas: Optional[int] = None
    capital_atual: Optional[Decimal] = None
    data_vencimento: Optional[date] = None
    status: StatusEmprestimo = StatusEmprestimo.ATIVO
    observacoes: Optional[str] = None

    def __post_init__(self):
        if self.capital_atual is None:
            self.capital_atual = self.capital_inicial

    @property
    def esta_quitado(self) -> bool:
        return self.capital_atual <= Decimal('0') or self.status == StatusEmprestimo.QUITADO

    @property
    def esta_inadimplente(self) -> bool:
        return self.status == StatusEmprestimo.INADIMPLENTE

    @property
    def pode_receber_pagamento(self) -> bool:
        return self.status in (StatusEmprestimo.ATIVO, StatusEmprestimo.INADIMPLENTE)