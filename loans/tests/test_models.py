"""
Testes do EmprestimoQuerySet.vencidos() e das properties de atraso.
A detecção é baseada em DATA, sem depender do comando de inadimplência.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db

HOJE = date.today()
ONTEM = HOJE - timedelta(days=1)
SEMANA_PASSADA = HOJE - timedelta(days=7)
AMANHA = HOJE + timedelta(days=1)


class TestVencidosComum:

    def test_comum_vencido_aparece(self, criar_emprestimo):
        from loans.infrastructure.models import Emprestimo
        emp = criar_emprestimo(tipo='comum', data_vencimento=ONTEM)
        assert emp in Emprestimo.objects.vencidos()
        assert emp.esta_vencido is True
        assert emp.dias_atraso == 1
        assert emp.valor_em_atraso == emp.capital_atual

    def test_comum_sem_vencimento_nao_aparece(self, criar_emprestimo):
        from loans.infrastructure.models import Emprestimo
        emp = criar_emprestimo(tipo='comum', data_vencimento=None)
        assert emp not in Emprestimo.objects.vencidos()
        assert emp.esta_vencido is False

    def test_comum_a_vencer_nao_aparece(self, criar_emprestimo):
        from loans.infrastructure.models import Emprestimo
        emp = criar_emprestimo(tipo='comum', data_vencimento=AMANHA)
        assert emp not in Emprestimo.objects.vencidos()

    def test_comum_quitado_nao_aparece(self, criar_emprestimo):
        from loans.infrastructure.models import Emprestimo
        emp = criar_emprestimo(tipo='comum', status='quitado', data_vencimento=ONTEM)
        assert emp not in Emprestimo.objects.vencidos()
        assert emp.esta_vencido is False


class TestVencidosParcelado:

    def test_parcela_aberta_vencida_inclui_emprestimo(self, criar_emprestimo, criar_parcela):
        from loans.infrastructure.models import Emprestimo
        emp = criar_emprestimo(tipo='parcelado', data_vencimento=ONTEM)
        criar_parcela(emp, numero=1, data_vencimento=SEMANA_PASSADA, status='pendente')
        assert emp in Emprestimo.objects.vencidos()
        assert emp.esta_vencido is True
        assert emp.dias_atraso == 7
        assert emp.valor_em_atraso == Decimal('200')

    def test_parcelas_pagas_nao_incluem(self, criar_emprestimo, criar_parcela):
        from loans.infrastructure.models import Emprestimo
        emp = criar_emprestimo(tipo='parcelado', data_vencimento=ONTEM)
        criar_parcela(emp, numero=1, data_vencimento=SEMANA_PASSADA, status='pago')
        assert emp not in Emprestimo.objects.vencidos()
        assert emp.esta_vencido is False

    def test_parcela_futura_nao_inclui(self, criar_emprestimo, criar_parcela):
        from loans.infrastructure.models import Emprestimo
        emp = criar_emprestimo(tipo='parcelado', data_vencimento=AMANHA)
        criar_parcela(emp, numero=1, data_vencimento=AMANHA, status='pendente')
        assert emp not in Emprestimo.objects.vencidos()


class TestAtivos:

    def test_ativos_inclui_ativo_e_inadimplente(self, criar_emprestimo):
        from loans.infrastructure.models import Emprestimo
        a = criar_emprestimo(status='ativo', data_vencimento=AMANHA)
        b = criar_emprestimo(status='inadimplente', data_vencimento=ONTEM)
        c = criar_emprestimo(status='quitado', data_vencimento=AMANHA)
        ativos = Emprestimo.objects.ativos()
        assert a in ativos and b in ativos
        assert c not in ativos
