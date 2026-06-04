"""
Regressão central: com o cron de inadimplência NUNCA executado, um empréstimo
comum vencido por data já deve elevar a inadimplência e o valor em atraso, e o
risco deve usar a nova composição ponderada.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


def test_comum_vencido_reflete_no_dashboard(criar_emprestimo):
    from dashboard.application.metrics import calcular_metricas_dashboard

    criar_emprestimo(
        tipo='comum', status='ativo',
        data_vencimento=date.today() - timedelta(days=10),
        capital=Decimal('1000'),
    )
    m = calcular_metricas_dashboard()

    assert m['inadimplentes'] == 1
    assert m['taxa_inadimplencia'] > 0
    assert m['valor_em_atraso'] == Decimal('1000')
    assert m['qtd_em_atraso'] == 1


def test_risco_tem_composicao_ponderada(criar_emprestimo):
    from dashboard.application.metrics import calcular_metricas_dashboard

    criar_emprestimo(
        tipo='comum', status='ativo',
        data_vencimento=date.today() - timedelta(days=10),
    )
    m = calcular_metricas_dashboard()
    comp = m['risco_composicao']
    assert set(comp) >= {'total', 'cobertura', 'historico', 'comprometimento', 'tempo'}
    # Sem garantia, fator cobertura é máximo (100)
    assert comp['cobertura'] == Decimal('100.00')


def test_sem_emprestimos_zera_metricas(db):
    from dashboard.application.metrics import calcular_metricas_dashboard
    m = calcular_metricas_dashboard()
    assert m['inadimplentes'] == 0
    assert m['valor_em_atraso'] == Decimal('0')
    assert m['taxa_inadimplencia'] == 0
