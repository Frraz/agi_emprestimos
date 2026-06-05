"""
Fixtures compartilhadas para os testes que tocam o banco (pytest-django).
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest


@pytest.fixture
def usuario(db):
    from django.contrib.auth.models import User
    return User.objects.create_user(username='operador', password='x')


@pytest.fixture
def cliente(db):
    from customers.infrastructure.models import Cliente
    return Cliente.objects.create(
        nome='Fulano de Tal',
        cpf='12345678901',
        telefone_principal='(11) 99999-0000',
    )


@pytest.fixture
def criar_cliente(db):
    from customers.infrastructure.models import Cliente
    contador = {'n': 0}

    def _make(nome='Cliente', prioridade='preferencial', classificacao='verde'):
        contador['n'] += 1
        return Cliente.objects.create(
            nome=nome,
            cpf=f'{contador["n"]:011d}',  # 00000000001, 00000000002, ...
            telefone_principal='(11) 90000-0000',
            prioridade_cobranca=prioridade,
            classificacao=classificacao,
        )

    return _make


@pytest.fixture
def criar_emprestimo(db, usuario, cliente):
    from loans.infrastructure.models import Emprestimo

    def _make(tipo='comum', status='ativo', cli=None, data_inicio=None,
              data_vencimento=None, capital=Decimal('1000'),
              taxa=Decimal('0.10')):
        # Espelha o service: empréstimo comum lança o 1º ciclo de juros
        # em juros_acumulados na criação (sem capitalização).
        juros_acum = Decimal('0')
        if tipo == 'comum':
            from loans.domain.calculators import CalculadoraEmprestimoComum
            juros_acum = CalculadoraEmprestimoComum.calcular_juros_mes(capital, taxa)
        return Emprestimo.objects.create(
            cliente=cli or cliente,
            tipo=tipo,
            status=status,
            capital_inicial=capital,
            capital_atual=capital,
            taxa_juros_mensal=taxa,
            juros_acumulados=juros_acum,
            data_ultimo_acumulo=data_vencimento,
            data_inicio=data_inicio or date.today() - timedelta(days=60),
            data_vencimento=data_vencimento,
            registrado_por=usuario,
        )

    return _make


@pytest.fixture
def criar_parcela(db):
    from loans.infrastructure.models import ParcelaEmprestimo

    def _make(emprestimo, numero=1, data_vencimento=None, status='pendente',
              valor=Decimal('200'), valor_pago=Decimal('0')):
        return ParcelaEmprestimo.objects.create(
            emprestimo=emprestimo,
            numero=numero,
            valor_parcela=valor,
            valor_principal=valor,
            valor_juros=Decimal('0'),
            saldo_devedor_antes=valor,
            saldo_devedor_depois=Decimal('0'),
            valor_pago=valor_pago,
            data_vencimento=data_vencimento or date.today(),
            status=status,
        )

    return _make
