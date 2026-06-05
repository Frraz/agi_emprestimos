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
    # Dívida total em atraso = capital 1000 + juros do ciclo (10% = 100)
    assert m['valor_em_atraso'] == Decimal('1100.00')
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


def test_recebimentos_mensais_zera_meses_vazios(db):
    from dashboard.application.metrics import calcular_metricas_dashboard
    m = calcular_metricas_dashboard()
    serie = m['recebimentos_mensais']

    assert len(serie) == 6
    assert all(item['total'] == Decimal('0') for item in serie)
    assert all({'label', 'total', 'juros'} <= set(item) for item in serie)
    # O último item é o mês corrente.
    assert m['recebido_mes_atual'] == serie[-1]


def test_recebimentos_mensais_soma_pagamentos_do_mes(criar_emprestimo, usuario):
    from dashboard.application.metrics import calcular_metricas_dashboard
    from payments.infrastructure.models import Pagamento

    emp = criar_emprestimo(tipo='comum', status='ativo', capital=Decimal('1000'))
    Pagamento.objects.create(
        emprestimo=emp,
        registrado_por=usuario,
        valor=Decimal('300'),
        valor_juros_pagos=Decimal('100'),
        valor_capital_pago=Decimal('200'),
        tipo='capital_parcial',
        data_pagamento=date.today(),
        capital_antes=Decimal('1000'),
        capital_depois=Decimal('800'),
    )
    m = calcular_metricas_dashboard()

    mes_atual = m['recebimentos_mensais'][-1]
    assert mes_atual['total'] == Decimal('300')
    assert mes_atual['juros'] == Decimal('100')


def test_taxa_ocupacao_capital(criar_emprestimo):
    from dashboard.application.metrics import calcular_metricas_dashboard
    from core.models_config import CapitalOperacional

    cfg = CapitalOperacional.get_instance()
    cfg.total_capital = Decimal('2000')
    cfg.save(update_fields=['total_capital', 'updated_at'])

    criar_emprestimo(tipo='comum', status='ativo', capital=Decimal('1000'))
    m = calcular_metricas_dashboard()

    # 1000 emprestado / 2000 total = 50%
    assert m['taxa_ocupacao_capital'] == Decimal('50.0')
