"""
Serviço de capital: aportes/retiradas manuais e lançamentos automáticos
(empréstimo concedido / recebimento) no histórico de movimentações.

O caixa disponível é derivado em CapitalOperacional (total_capital + juros
recebidos − emprestado), então os lançamentos automáticos são informativos.
Aporte/retirada ajustam total_capital (o capital efetivamente aportado).
"""
from datetime import date
from decimal import Decimal


def _money(v) -> Decimal:
    from decimal import ROUND_HALF_UP
    return Decimal(v).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def registrar_aporte(usuario, valor, descricao='', quando=None):
    from core.models_config import CapitalOperacional, MovimentacaoCapital
    valor = _money(valor)
    cfg = CapitalOperacional.get_for_user(usuario)
    cfg.total_capital = cfg.total_capital + valor
    cfg.save(update_fields=['total_capital', 'updated_at'])
    return MovimentacaoCapital.objects.create(
        owner=usuario, tipo='aporte', valor=valor,
        data=quando or date.today(), descricao=descricao,
    )


def registrar_retirada(usuario, valor, descricao='', quando=None):
    from core.models_config import CapitalOperacional, MovimentacaoCapital
    valor = _money(valor)
    cfg = CapitalOperacional.get_for_user(usuario)
    cfg.total_capital = cfg.total_capital - valor
    cfg.save(update_fields=['total_capital', 'updated_at'])
    return MovimentacaoCapital.objects.create(
        owner=usuario, tipo='retirada', valor=valor,
        data=quando or date.today(), descricao=descricao,
    )


def registrar_movimento_emprestimo(emprestimo, usuario, quando=None):
    """Lançamento informativo: empréstimo concedido (debita o caixa disponível
    via capital_emprestado)."""
    from core.models_config import MovimentacaoCapital
    try:
        MovimentacaoCapital.objects.create(
            owner=usuario, tipo='emprestimo', valor=_money(emprestimo.capital_inicial),
            data=quando or date.today(), emprestimo=emprestimo,
            descricao=f'Empréstimo para {emprestimo.cliente.nome}',
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning('Falha ao registrar movimento de empréstimo')


def registrar_movimento_recebimento(emprestimo, valor, usuario, quando=None):
    """Lançamento informativo: recebimento de pagamento (credita o caixa)."""
    from core.models_config import MovimentacaoCapital
    try:
        MovimentacaoCapital.objects.create(
            owner=usuario, tipo='recebimento', valor=_money(valor),
            data=quando or date.today(), emprestimo=emprestimo,
            descricao=f'Recebimento de {emprestimo.cliente.nome}',
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning('Falha ao registrar movimento de recebimento')
