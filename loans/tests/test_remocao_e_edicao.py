"""
Testes das ações de remoção (Desativar/Ativar/Apagar) e edição de empréstimo.

Cobre:
  - Desativar/Ativar/Apagar pagamento recalcula o saldo do empréstimo.
  - Caixa do operador se corrige após desativar/apagar.
  - Apagar empréstimo e cliente em cascata, sem ProtectedError.
  - Editar empréstimo comum com nova taxa recalcula o saldo.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db

HOJE = date.today()


def _user(username):
    from django.contrib.auth.models import User
    return User.objects.create_user(username=username, password='x')


def _cliente(nome, cpf, owner=None):
    from customers.infrastructure.models import Cliente
    return Cliente.objects.create(
        nome=nome, cpf=cpf, telefone_principal='(11) 90000-0000', owner=owner,
    )


def _emp_comum(u, c, capital=Decimal('600'), taxa=Decimal('0.20')):
    from loans.application.services import EmprestimoService
    return EmprestimoService.criar_emprestimo_comum(
        cliente_id=str(c.id), capital=capital, taxa_mensal=taxa,
        data_inicio=HOJE, data_vencimento=HOJE + timedelta(days=30), usuario=u,
    )


def _emp_parcelado(u, c, n=5, capital=Decimal('1000'), taxa=Decimal('0')):
    from loans.application.services import EmprestimoService
    return EmprestimoService.criar_emprestimo_parcelado(
        cliente_id=str(c.id), capital=capital, taxa_mensal=taxa,
        n_parcelas=n, subtipo='fixo', data_inicio=HOJE,
        data_primeira_parcela=HOJE, usuario=u,
    )


# ── Pagamento: desativar / ativar / apagar ──────────────────────────────────

class TestRemoverPagamentoComum:

    def test_desativar_pagamento_reverte_saldo(self):
        from loans.application.services import EmprestimoService
        u = _user('rp1'); c = _cliente('C', '50000000001', owner=u)
        emp = _emp_comum(u, c)
        pag = EmprestimoService.registrar_pagamento_comum(
            emprestimo_id=str(emp.id), valor=Decimal('400'), data_pagamento=HOJE, usuario=u,
        )
        emp.refresh_from_db()
        assert emp.capital_atual == Decimal('320.00')  # 600 - (400 - 120)

        EmprestimoService.desativar_pagamento(str(pag.id), u)
        emp.refresh_from_db()
        assert emp.capital_atual == Decimal('600.00')
        assert emp.juros_acumulados == Decimal('120.00')
        pag.refresh_from_db()
        assert pag.deleted_at is not None

    def test_ativar_pagamento_reaplica_saldo(self):
        from loans.application.services import EmprestimoService
        u = _user('rp2'); c = _cliente('C', '50000000002', owner=u)
        emp = _emp_comum(u, c)
        pag = EmprestimoService.registrar_pagamento_comum(
            emprestimo_id=str(emp.id), valor=Decimal('400'), data_pagamento=HOJE, usuario=u,
        )
        EmprestimoService.desativar_pagamento(str(pag.id), u)
        EmprestimoService.ativar_pagamento(str(pag.id), u)
        emp.refresh_from_db()
        assert emp.capital_atual == Decimal('320.00')
        pag.refresh_from_db()
        assert pag.deleted_at is None

    def test_apagar_pagamento_remove_e_recalcula(self):
        from loans.application.services import EmprestimoService
        from payments.infrastructure.models import Pagamento
        u = _user('rp3'); c = _cliente('C', '50000000003', owner=u)
        emp = _emp_comum(u, c)
        pag = EmprestimoService.registrar_pagamento_comum(
            emprestimo_id=str(emp.id), valor=Decimal('400'), data_pagamento=HOJE, usuario=u,
        )
        pag_id = pag.id
        EmprestimoService.apagar_pagamento(str(pag.id), u)
        emp.refresh_from_db()
        assert emp.capital_atual == Decimal('600.00')
        assert not Pagamento.objects.filter(id=pag_id).exists()


class TestRemoverPagamentoParcelado:

    def test_apagar_pagamento_de_parcela_reabre_parcela(self):
        from loans.application.services import EmprestimoService
        from payments.infrastructure.models import Pagamento
        u = _user('rp4'); c = _cliente('C', '50000000004', owner=u)
        emp = _emp_parcelado(u, c)
        p1 = emp.parcelas.order_by('numero').first()
        EmprestimoService.registrar_pagamento_parcelas(
            emprestimo_id=str(emp.id), parcela_ids=[str(p1.id)],
            valor=Decimal('200'), data_pagamento=HOJE, usuario=u,
        )
        emp.refresh_from_db()
        assert emp.capital_atual == Decimal('800.00')

        pag = Pagamento.objects.filter(parcela=p1).first()
        EmprestimoService.apagar_pagamento(str(pag.id), u)
        p1.refresh_from_db(); emp.refresh_from_db()
        assert p1.status == 'pendente'
        assert p1.valor_pago == Decimal('0.00')
        assert emp.capital_atual == Decimal('1000.00')


# ── Caixa ────────────────────────────────────────────────────────────────────

class TestCaixaAposRemocao:

    def test_caixa_volta_ao_desativar_pagamento(self):
        from loans.application.services import EmprestimoService
        from core.models_config import CapitalOperacional
        from core.capital import registrar_aporte
        u = _user('cx1'); c = _cliente('C', '51000000001', owner=u)
        registrar_aporte(u, Decimal('1000'))
        emp = _emp_comum(u, c)
        pag = EmprestimoService.registrar_pagamento_comum(
            emprestimo_id=str(emp.id), valor=Decimal('400'), data_pagamento=HOJE, usuario=u,
        )
        cfg = CapitalOperacional.get_for_user(u)
        assert cfg.juros_recebidos == Decimal('120.00')
        assert cfg.capital_em_caixa == Decimal('800.00')  # 1000 + 120 - 320

        EmprestimoService.desativar_pagamento(str(pag.id), u)
        cfg = CapitalOperacional.get_for_user(u)
        assert cfg.juros_recebidos == Decimal('0.00')
        assert cfg.capital_emprestado == Decimal('600.00')
        assert cfg.capital_em_caixa == Decimal('400.00')  # 1000 + 0 - 600

    def test_caixa_libera_ao_desativar_emprestimo(self):
        from loans.application.services import EmprestimoService
        from core.models_config import CapitalOperacional
        from core.capital import registrar_aporte
        u = _user('cx2'); c = _cliente('C', '51000000002', owner=u)
        registrar_aporte(u, Decimal('1000'))
        emp = _emp_comum(u, c)
        assert CapitalOperacional.get_for_user(u).capital_em_caixa == Decimal('400.00')

        EmprestimoService.desativar_emprestimo(str(emp.id), u)
        assert CapitalOperacional.get_for_user(u).capital_em_caixa == Decimal('1000.00')


# ── Apagar em cascata ────────────────────────────────────────────────────────

class TestApagarCascata:

    def test_apagar_emprestimo_parcelado_remove_tudo(self):
        from loans.application.services import EmprestimoService
        from loans.infrastructure.models import Emprestimo, ParcelaEmprestimo
        from payments.infrastructure.models import Pagamento
        u = _user('ap1'); c = _cliente('C', '52000000001', owner=u)
        emp = _emp_parcelado(u, c)
        p1 = emp.parcelas.order_by('numero').first()
        EmprestimoService.registrar_pagamento_parcelas(
            emprestimo_id=str(emp.id), parcela_ids=[str(p1.id)],
            valor=Decimal('200'), data_pagamento=HOJE, usuario=u,
        )
        emp_id = emp.id
        EmprestimoService.apagar_emprestimo(str(emp.id), u)
        assert not Emprestimo.objects.filter(id=emp_id).exists()
        assert not ParcelaEmprestimo.objects.filter(emprestimo_id=emp_id).exists()
        assert not Pagamento.objects.filter(emprestimo_id=emp_id).exists()

    def test_apagar_cliente_remove_emprestimos_e_pagamentos(self):
        from loans.application.services import EmprestimoService
        from customers.application.services import ClienteService
        from customers.infrastructure.models import Cliente
        from loans.infrastructure.models import Emprestimo
        from payments.infrastructure.models import Pagamento
        u = _user('ap2'); c = _cliente('C', '52000000002', owner=u)
        emp = _emp_comum(u, c)
        EmprestimoService.registrar_pagamento_comum(
            emprestimo_id=str(emp.id), valor=Decimal('400'), data_pagamento=HOJE, usuario=u,
        )
        cid = c.id
        ClienteService.apagar_cliente(str(c.id), u)
        assert not Cliente.objects.filter(id=cid).exists()
        assert not Emprestimo.objects.filter(cliente_id=cid).exists()
        assert not Pagamento.objects.filter(emprestimo__cliente_id=cid).exists()


# ── Editar empréstimo ────────────────────────────────────────────────────────

class TestEditarEmprestimo:

    def test_editar_taxa_comum_recalcula(self):
        from loans.application.services import EmprestimoService
        u = _user('ee1'); c = _cliente('C', '53000000001', owner=u)
        emp = _emp_comum(u, c, taxa=Decimal('0.20'))
        assert emp.juros_acumulados == Decimal('120.00')

        EmprestimoService.editar_emprestimo(
            str(emp.id), usuario=u, observacoes='nova obs', taxa_mensal=Decimal('0.10'),
        )
        emp.refresh_from_db()
        assert emp.taxa_juros_mensal == Decimal('0.10')
        assert emp.juros_acumulados == Decimal('60.00')  # 600 * 0.10
        assert emp.observacoes == 'nova obs'
