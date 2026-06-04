"""
Testes do CobrancaService: agrupamento em baldes e total por cliente.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db

HOJE = date.today()
ONTEM = HOJE - timedelta(days=1)
AMANHA = HOJE + timedelta(days=1)


class TestBuckets:

    def test_balde_atrasados_e_hoje(self, criar_emprestimo):
        from cobrancas.application.services import CobrancaService
        criar_emprestimo(tipo='comum', data_vencimento=ONTEM, capital=Decimal('1000'))
        criar_emprestimo(tipo='comum', data_vencimento=HOJE, capital=Decimal('500'))

        baldes = CobrancaService.vencimentos_por_bucket(ref=HOJE)
        assert len(baldes['atrasados']) == 1
        assert len(baldes['hoje']) == 1

    def test_balde_amanha(self, criar_emprestimo):
        from cobrancas.application.services import CobrancaService
        criar_emprestimo(tipo='comum', data_vencimento=AMANHA)
        baldes = CobrancaService.vencimentos_por_bucket(ref=HOJE)
        assert len(baldes['amanha']) == 1

    def test_data_especifica(self, criar_emprestimo):
        from cobrancas.application.services import CobrancaService
        alvo = HOJE - timedelta(days=3)
        criar_emprestimo(tipo='comum', data_vencimento=alvo)
        baldes = CobrancaService.vencimentos_por_bucket(ref=HOJE, data_especifica=alvo)
        assert len(baldes['data_especifica']) == 1


class TestTotalPorCliente:

    def test_essencial_vem_primeiro(self, criar_emprestimo, criar_cliente):
        from cobrancas.application.services import CobrancaService
        pref = criar_cliente(nome='Preferencial', prioridade='preferencial')
        ess = criar_cliente(nome='Essencial', prioridade='essencial')
        # Preferencial deve mais, mas Essencial tem prioridade de cobrança
        criar_emprestimo(tipo='comum', cli=pref, data_vencimento=ONTEM, capital=Decimal('5000'))
        criar_emprestimo(tipo='comum', cli=ess, data_vencimento=ONTEM, capital=Decimal('100'))

        linhas = CobrancaService.total_atraso_por_cliente(ref=HOJE)
        assert linhas[0]['cliente'].id == ess.id
        assert linhas[1]['cliente'].id == pref.id

    def test_agrega_valor_e_conta(self, criar_emprestimo, criar_cliente):
        from cobrancas.application.services import CobrancaService
        c = criar_cliente(nome='Multi')
        criar_emprestimo(tipo='comum', cli=c, data_vencimento=ONTEM, capital=Decimal('1000'), taxa=Decimal('0.10'))
        criar_emprestimo(tipo='comum', cli=c, data_vencimento=ONTEM, capital=Decimal('2000'), taxa=Decimal('0.10'))

        linhas = CobrancaService.total_atraso_por_cliente(ref=HOJE)
        linha = next(l for l in linhas if l['cliente'].id == c.id)
        assert linha['qtd'] == 2
        # total = total_quitacao dos dois (capital + juros do mês)
        assert linha['total'] == Decimal('1100.00') + Decimal('2200.00')
