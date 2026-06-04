"""
Testes do EmprestimoService — foco no bug corrigido: empréstimo COMUM
agora grava data_vencimento e passa a ser detectável como vencido.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

pytestmark = pytest.mark.django_db


class TestCriarEmprestimoComum:

    def test_grava_data_vencimento(self, usuario, cliente):
        from loans.application.services import EmprestimoService
        venc = date.today() + timedelta(days=30)
        emp = EmprestimoService.criar_emprestimo_comum(
            cliente_id=str(cliente.id),
            capital=Decimal('1000'),
            taxa_mensal=Decimal('0.10'),
            data_inicio=date.today(),
            data_vencimento=venc,
            usuario=usuario,
        )
        assert emp.data_vencimento == venc

    def test_comum_vencido_detectado_sem_cron(self, usuario, cliente):
        from loans.application.services import EmprestimoService
        from loans.infrastructure.models import Emprestimo
        emp = EmprestimoService.criar_emprestimo_comum(
            cliente_id=str(cliente.id),
            capital=Decimal('1000'),
            taxa_mensal=Decimal('0.10'),
            data_inicio=date.today() - timedelta(days=40),
            data_vencimento=date.today() - timedelta(days=5),
            usuario=usuario,
        )
        # status continua 'ativo' (cron não rodou), mas é detectado por data
        assert emp.status == 'ativo'
        assert emp in Emprestimo.objects.vencidos()
