"""
Testes de Fase A:
  - Isolamento de dados por usuário (P1).
  - Pagamento de empréstimo comum sem capitalização, ponta a ponta (P2).
  - Empréstimo com juros zero (P9).
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db

HOJE = date.today()


# ── Helpers ────────────────────────────────────────────────────────────────

def _user(username):
    from django.contrib.auth.models import User
    return User.objects.create_user(username=username, password='x')


def _cliente(nome, cpf, owner=None):
    from customers.infrastructure.models import Cliente
    return Cliente.objects.create(
        nome=nome, cpf=cpf, telefone_principal='(11) 90000-0000', owner=owner,
    )


# ── P1 — Isolamento ──────────────────────────────────────────────────────────

class TestIsolamentoPorUsuario:

    def test_cliente_so_aparece_para_o_dono_e_legado_para_todos(self):
        from customers.infrastructure.models import Cliente
        from core.ownership import filtrar_por_usuario

        a = _user('alice')
        b = _user('bob')
        cli_a = _cliente('Cliente A', '11111111111', owner=a)
        cli_b = _cliente('Cliente B', '22222222222', owner=b)
        cli_legado = _cliente('Legado', '33333333333', owner=None)

        vis_a = set(filtrar_por_usuario(Cliente.objects.all(), a).values_list('id', flat=True))
        vis_b = set(filtrar_por_usuario(Cliente.objects.all(), b).values_list('id', flat=True))

        assert cli_a.id in vis_a and cli_legado.id in vis_a and cli_b.id not in vis_a
        assert cli_b.id in vis_b and cli_legado.id in vis_b and cli_a.id not in vis_b

    def test_emprestimo_for_user(self):
        from loans.application.services import EmprestimoService
        from loans.infrastructure.models import Emprestimo

        a = _user('alice2')
        b = _user('bob2')
        cli_a = _cliente('A', '44444444444', owner=a)
        cli_b = _cliente('B', '55555555555', owner=b)

        emp_a = EmprestimoService.criar_emprestimo_comum(
            cliente_id=str(cli_a.id), capital=Decimal('1000'), taxa_mensal=Decimal('0.10'),
            data_inicio=HOJE, data_vencimento=HOJE + timedelta(days=30), usuario=a,
        )
        emp_b = EmprestimoService.criar_emprestimo_comum(
            cliente_id=str(cli_b.id), capital=Decimal('500'), taxa_mensal=Decimal('0.10'),
            data_inicio=HOJE, data_vencimento=HOJE + timedelta(days=30), usuario=b,
        )

        ids_a = set(Emprestimo.objects.for_user(a).values_list('id', flat=True))
        assert emp_a.id in ids_a and emp_b.id not in ids_a

    def test_usuario_anonimo_nao_ve_nada(self):
        from customers.infrastructure.models import Cliente
        from core.ownership import filtrar_por_usuario

        _cliente('Qualquer', '66666666666', owner=_user('carol'))
        assert filtrar_por_usuario(Cliente.objects.all(), None).count() == 0


# ── P2 — Pagamento comum sem capitalização (ponta a ponta) ──────────────────

class TestPagamentoComumServico:

    def _criar(self, capital, taxa, usuario, cliente):
        from loans.application.services import EmprestimoService
        return EmprestimoService.criar_emprestimo_comum(
            cliente_id=str(cliente.id), capital=capital, taxa_mensal=taxa,
            data_inicio=HOJE, data_vencimento=HOJE + timedelta(days=30), usuario=usuario,
        )

    def test_criacao_lanca_primeiro_ciclo_de_juros(self):
        u = _user('op1')
        cli = _cliente('C', '77777777777', owner=u)
        emp = self._criar(Decimal('600'), Decimal('0.20'), u, cli)
        assert emp.juros_acumulados == Decimal('120.00')
        assert emp.total_quitacao == Decimal('720.00')

    def test_bug_600_paga_719_99_deixa_um_centavo(self):
        from loans.application.services import EmprestimoService
        u = _user('op2')
        cli = _cliente('C', '88888888888', owner=u)
        emp = self._criar(Decimal('600'), Decimal('0.20'), u, cli)

        EmprestimoService.registrar_pagamento_comum(
            emprestimo_id=str(emp.id), valor=Decimal('719.99'), data_pagamento=HOJE, usuario=u,
        )
        emp.refresh_from_db()
        assert emp.capital_atual == Decimal('0.01')
        assert emp.juros_acumulados == Decimal('0.00')
        assert emp.status == 'ativo'   # ainda há 0,01 de capital

    def test_pagamentos_fracionados_quitam_sem_recobrar_juros(self):
        from loans.application.services import EmprestimoService
        u = _user('op3')
        cli = _cliente('C', '99999999999', owner=u)
        emp = self._criar(Decimal('600'), Decimal('0.20'), u, cli)

        EmprestimoService.registrar_pagamento_comum(
            emprestimo_id=str(emp.id), valor=Decimal('400'), data_pagamento=HOJE, usuario=u,
        )
        EmprestimoService.registrar_pagamento_comum(
            emprestimo_id=str(emp.id), valor=Decimal('320'), data_pagamento=HOJE, usuario=u,
        )
        emp.refresh_from_db()
        # 400 + 320 = 720 = dívida total → quitado, sem juros sobre juros
        assert emp.capital_atual == Decimal('0.00')
        assert emp.status == 'quitado'

    # ── P9 — Juros zero ──────────────────────────────────────────────────────

    def test_emprestimo_juros_zero_quita_com_o_capital(self):
        from loans.application.services import EmprestimoService
        u = _user('op4')
        cli = _cliente('C', '10101010101', owner=u)
        emp = self._criar(Decimal('1000'), Decimal('0'), u, cli)
        assert emp.juros_acumulados == Decimal('0.00')
        assert emp.total_quitacao == Decimal('1000.00')

        EmprestimoService.registrar_pagamento_comum(
            emprestimo_id=str(emp.id), valor=Decimal('1000'), data_pagamento=HOJE, usuario=u,
        )
        emp.refresh_from_db()
        assert emp.capital_atual == Decimal('0.00')
        assert emp.status == 'quitado'


# ── P3 — Pagamento de parcelas ───────────────────────────────────────────────

class TestPagamentoParcelas:

    def _emp(self, usuario, cliente, n=5, capital=Decimal('1000'), taxa=Decimal('0')):
        from loans.application.services import EmprestimoService
        return EmprestimoService.criar_emprestimo_parcelado(
            cliente_id=str(cliente.id), capital=capital, taxa_mensal=taxa,
            n_parcelas=n, subtipo='fixo', data_inicio=HOJE,
            data_primeira_parcela=HOJE, usuario=usuario,
        )

    def test_pagar_parcela_unica_total(self):
        from loans.application.services import EmprestimoService
        u = _user('pp1'); c = _cliente('C', '20202020201', owner=u)
        emp = self._emp(u, c)
        p1 = emp.parcelas.order_by('numero').first()
        res = EmprestimoService.registrar_pagamento_parcelas(
            emprestimo_id=str(emp.id), parcela_ids=[str(p1.id)],
            valor=Decimal('200'), data_pagamento=HOJE, usuario=u,
        )
        p1.refresh_from_db(); emp.refresh_from_db()
        assert p1.status == 'pago'
        assert emp.capital_atual == Decimal('800.00')
        assert res['excedente_info'] == []

    def test_pagamento_parcial(self):
        from loans.application.services import EmprestimoService
        u = _user('pp2'); c = _cliente('C', '20202020202', owner=u)
        emp = self._emp(u, c)
        p1 = emp.parcelas.order_by('numero').first()
        EmprestimoService.registrar_pagamento_parcelas(
            emprestimo_id=str(emp.id), parcela_ids=[str(p1.id)],
            valor=Decimal('100'), data_pagamento=HOJE, usuario=u,
        )
        p1.refresh_from_db(); emp.refresh_from_db()
        assert p1.status == 'parcialmente_pago'
        assert p1.valor_em_aberto == Decimal('100.00')
        assert emp.capital_atual == Decimal('900.00')

    def test_excedente_vai_para_proxima_parcela(self):
        from loans.application.services import EmprestimoService
        u = _user('pp3'); c = _cliente('C', '20202020203', owner=u)
        emp = self._emp(u, c)
        p1, p2 = emp.parcelas.order_by('numero')[:2]
        res = EmprestimoService.registrar_pagamento_parcelas(
            emprestimo_id=str(emp.id), parcela_ids=[str(p1.id)],
            valor=Decimal('250'), data_pagamento=HOJE, usuario=u,
        )
        p1.refresh_from_db(); p2.refresh_from_db(); emp.refresh_from_db()
        assert p1.status == 'pago'
        assert p2.status == 'parcialmente_pago'
        assert p2.valor_pago == Decimal('50.00')
        assert res['excedente_info'][0]['numero'] == 2
        assert res['excedente_info'][0]['valor_aplicado'] == Decimal('50.00')
        assert res['excedente_info'][0]['novo_em_aberto'] == Decimal('150.00')
        assert emp.capital_atual == Decimal('750.00')

    def test_multiplas_parcelas(self):
        from loans.application.services import EmprestimoService
        u = _user('pp4'); c = _cliente('C', '20202020204', owner=u)
        emp = self._emp(u, c)
        p1, p2 = emp.parcelas.order_by('numero')[:2]
        EmprestimoService.registrar_pagamento_parcelas(
            emprestimo_id=str(emp.id), parcela_ids=[str(p1.id), str(p2.id)],
            valor=Decimal('400'), data_pagamento=HOJE, usuario=u,
        )
        p1.refresh_from_db(); p2.refresh_from_db(); emp.refresh_from_db()
        assert p1.status == 'pago' and p2.status == 'pago'
        assert emp.capital_atual == Decimal('600.00')

    def test_quita_ao_pagar_todas(self):
        from loans.application.services import EmprestimoService
        u = _user('pp5'); c = _cliente('C', '20202020205', owner=u)
        emp = self._emp(u, c)
        ids = [str(p.id) for p in emp.parcelas.order_by('numero')]
        res = EmprestimoService.registrar_pagamento_parcelas(
            emprestimo_id=str(emp.id), parcela_ids=ids,
            valor=Decimal('1000'), data_pagamento=HOJE, usuario=u,
        )
        emp.refresh_from_db()
        assert emp.status == 'quitado'
        assert emp.capital_atual == Decimal('0.00')
        assert res['quitado'] is True


# ── P4 — Edição de pagamento (recalcula saldo) ──────────────────────────────

class TestEditarPagamento:

    def test_editar_valor_comum_recalcula_saldo(self):
        from loans.application.services import EmprestimoService
        u = _user('ep1'); c = _cliente('C', '30303030301', owner=u)
        emp = EmprestimoService.criar_emprestimo_comum(
            cliente_id=str(c.id), capital=Decimal('600'), taxa_mensal=Decimal('0.20'),
            data_inicio=HOJE, data_vencimento=HOJE + timedelta(days=30), usuario=u,
        )
        pag = EmprestimoService.registrar_pagamento_comum(
            emprestimo_id=str(emp.id), valor=Decimal('400'), data_pagamento=HOJE, usuario=u,
        )
        emp.refresh_from_db()
        assert emp.capital_atual == Decimal('320.00')  # 600 - (400-120)

        # Corrige o pagamento para 719,99 → saldo deve virar 0,01
        EmprestimoService.editar_pagamento(
            pagamento_id=str(pag.id), valor=Decimal('719.99'),
            data_pagamento=HOJE, observacoes='corrigido', usuario=u,
        )
        emp.refresh_from_db()
        assert emp.capital_atual == Decimal('0.01')
        assert emp.juros_acumulados == Decimal('0.00')

    def test_editar_parcela_recalcula(self):
        from loans.application.services import EmprestimoService
        u = _user('ep2'); c = _cliente('C', '30303030302', owner=u)
        emp = EmprestimoService.criar_emprestimo_parcelado(
            cliente_id=str(c.id), capital=Decimal('1000'), taxa_mensal=Decimal('0'),
            n_parcelas=5, subtipo='fixo', data_inicio=HOJE,
            data_primeira_parcela=HOJE, usuario=u,
        )
        p1 = emp.parcelas.order_by('numero').first()
        res = EmprestimoService.registrar_pagamento_parcelas(
            emprestimo_id=str(emp.id), parcela_ids=[str(p1.id)],
            valor=Decimal('200'), data_pagamento=HOJE, usuario=u,
        )
        from payments.infrastructure.models import Pagamento
        pag = Pagamento.objects.filter(parcela=p1).first()
        # Corrige para pagamento parcial de 120
        EmprestimoService.editar_pagamento(
            pagamento_id=str(pag.id), valor=Decimal('120'),
            data_pagamento=HOJE, observacoes='', usuario=u,
        )
        p1.refresh_from_db(); emp.refresh_from_db()
        assert p1.valor_pago == Decimal('120.00')
        assert p1.status == 'parcialmente_pago'
        assert emp.capital_atual == Decimal('880.00')  # 1000 - 120


# ── P2 — Cura de saldos (recalcular_saldos) ─────────────────────────────────

class TestRecalcularSaldos:

    def test_reconstruir_corrige_capital_inflado(self):
        """Simula um saldo inflado por capitalização antiga e verifica que a
        reconstrução devolve o saldo correto sem juros sobre juros."""
        from loans.application.services import EmprestimoService
        from loans.management.commands.recalcular_saldos import Command

        u = _user('op5')
        cli = _cliente('C', '12121212121', owner=u)
        emp = EmprestimoService.criar_emprestimo_comum(
            cliente_id=str(cli.id), capital=Decimal('600'), taxa_mensal=Decimal('0.20'),
            data_inicio=HOJE, data_vencimento=HOJE + timedelta(days=30), usuario=u,
        )
        # Registra um pagamento correto de 719,99 (deixa 0,01)
        EmprestimoService.registrar_pagamento_comum(
            emprestimo_id=str(emp.id), valor=Decimal('719.99'), data_pagamento=HOJE, usuario=u,
        )
        # Corrompe o saldo como se a capitalização antiga tivesse inflado
        emp.refresh_from_db()
        emp.capital_atual = Decimal('18.01')
        emp.juros_acumulados = Decimal('0')
        emp.save(update_fields=['capital_atual', 'juros_acumulados'])

        capital, juros = Command._reconstruir(emp, HOJE)
        assert capital == Decimal('0.01')
        assert juros == Decimal('0.00')
